"""Интеграция с Zabbix: активные проблемы (события с ошибками) по магазинам.

Два провайдера с одинаковым интерфейсом:

* :class:`ZabbixClient` — реальный Zabbix API (JSON-RPC ``problem.get``).
  Включается переменными окружения::

      ZABBIX_URL=https://zabbix.example.com   # без /api_jsonrpc.php
      ZABBIX_TOKEN=<api-token>                # API-токен (Zabbix ≥ 5.4)
      ZABBIX_HOSTS=st17=store-17.local,st03=store-03.local,...
      # соответствие id магазина → имя хоста; по умолчанию хост = id

* :class:`ZabbixEmulator` — правдоподобная эмуляция торгового
  мониторинга (кассы, холодильники, эквайринг, ИБП...), когда реального
  сервера нет. Используется автоматически, если ``ZABBIX_URL`` не задан.

Метод ``problems()`` возвращает словарь::

    {store_id: {"active": int,          # всего активных проблем
                "worst": int,           # максимальная severity (0-5)
                "problems": [{"name", "severity", "age_sec"}, ...]}}

Severity — шкала Zabbix: 0 не классифицировано, 1 информация,
2 предупреждение, 3 средняя, 4 высокая, 5 чрезвычайная.
"""

import json
import os
import random
import time
import urllib.request
from typing import Dict, List, Optional

from .i18n import DEFAULT_LANG, t

#: имена уровней важности переведены через каталог i18n (ru/ro/en) —
#: сюда складываются уже готовые строки для языка по умолчанию, чтобы не
#: ломать код, который импортирует SEVERITY_NAMES напрямую (без lang);
#: для конкретного языка запроса используйте `severity_name(sev, lang)`.
SEVERITY_NAMES = {sev: t(DEFAULT_LANG, f"zabbix.severity.{sev}")
                  for sev in range(6)}


def severity_name(severity: int, lang: str = DEFAULT_LANG) -> str:
    """Название уровня важности на нужном языке (0-5, см. докстринг модуля)."""
    return t(lang, f"zabbix.severity.{severity}")


class ZabbixClient:
    """Клиент реального Zabbix API (аутентификация API-токеном)."""

    def __init__(self, url: str, token: str,
                 host_map: Dict[str, str], timeout: float = 5.0):
        self.api_url = url.rstrip("/") + "/api_jsonrpc.php"
        self.token = token
        self.host_map = host_map            # store_id -> имя хоста в Zabbix
        self.timeout = timeout
        self._hostids: Optional[Dict[str, str]] = None  # hostid -> store_id

    def _call(self, method: str, params: dict):
        payload = json.dumps({"jsonrpc": "2.0", "id": 1,
                              "method": method, "params": params}).encode()
        req = urllib.request.Request(
            self.api_url, data=payload,
            headers={"Content-Type": "application/json-rpc",
                     "Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())
        if "error" in data:
            raise RuntimeError(f"Zabbix API: {data['error']}")
        return data["result"]

    def _resolve_hosts(self) -> Dict[str, str]:
        if self._hostids is None:
            hosts = self._call("host.get", {
                "output": ["hostid", "host"],
                "filter": {"host": list(self.host_map.values())}})
            by_name = {h["host"]: h["hostid"] for h in hosts}
            self._hostids = {by_name[name]: store_id
                             for store_id, name in self.host_map.items()
                             if name in by_name}
        return self._hostids

    def problems(self, lang: str = DEFAULT_LANG) -> Dict[str, dict]:
        # ``lang`` не используется: имена проблем реального Zabbix — живые
        # данные из мониторинга, а не текст интерфейса, переводу не
        # подлежат (см. правило проекта — не переводить данные владельца).
        hostids = self._resolve_hosts()
        rows = self._call("problem.get", {
            "output": ["eventid", "name", "severity", "clock"],
            "hostids": list(hostids.keys()),
            "selectHosts": ["hostid"],
            "recent": False, "sortfield": "eventid", "sortorder": "DESC"})
        now = time.time()
        out = {sid: {"active": 0, "worst": 0, "problems": []}
               for sid in self.host_map}
        for row in rows:
            for h in row.get("hosts", []):
                store_id = hostids.get(h["hostid"])
                if store_id is None:
                    continue
                entry = out[store_id]
                sev = int(row["severity"])
                entry["active"] += 1
                entry["worst"] = max(entry["worst"], sev)
                if len(entry["problems"]) < 5:
                    entry["problems"].append({
                        "name": row["name"], "severity": sev,
                        "age_sec": int(now - int(row["clock"]))})
        return out


class ZabbixEmulator:
    """Эмуляция мониторинга торгового оборудования сети.

    Проблемы появляются и закрываются случайно, но правдоподобно:
    у каждого магазина свой генератор, состояние живёт между опросами.
    """

    #: ключ каталога i18n (не готовый текст — язык известен только в
    #: момент отдачи `problems()`, см. `render_event` в webapp/i18n.py
    #: для того же приёма) + severity
    CATALOG = [
        ("zabbix.problem.pos_offline", 4),
        ("zabbix.problem.acquiring_timeout", 4),
        ("zabbix.problem.fridge_temp", 3),
        ("zabbix.problem.ups_battery", 3),
        ("zabbix.problem.disk_full", 2),
        ("zabbix.problem.scales_unresponsive", 2),
        ("zabbix.problem.scanner_errors", 1),
        ("zabbix.problem.camera_offline", 1),
    ]

    def __init__(self, store_ids: List[str], update_every: float = 6.0):
        self.update_every = update_every
        self._last_update = 0.0
        self._state: Dict[str, List[dict]] = {}
        self._rng: Dict[str, random.Random] = {}
        for i, sid in enumerate(store_ids):
            rng = random.Random(hash(sid) & 0xFFFF)
            self._rng[sid] = rng
            # стартовое состояние: у части магазинов уже есть проблемы
            self._state[sid] = []
            for key, sev in self.CATALOG:
                if rng.random() < 0.12:
                    self._state[sid].append({
                        "key": key, "severity": sev,
                        "since": time.time() - rng.uniform(60, 3600)})

    def _evolve(self) -> None:
        now = time.time()
        if now - self._last_update < self.update_every:
            return
        self._last_update = now
        for sid, active in self._state.items():
            rng = self._rng[sid]
            # закрытие существующих проблем
            self._state[sid] = [p for p in active if rng.random() > 0.10]
            # появление новых
            current = {p["key"] for p in self._state[sid]}
            for key, sev in self.CATALOG:
                if key not in current and rng.random() < 0.035:
                    self._state[sid].append(
                        {"key": key, "severity": sev, "since": now})

    def problems(self, lang: str = DEFAULT_LANG) -> Dict[str, dict]:
        self._evolve()
        now = time.time()
        out = {}
        for sid, active in self._state.items():
            ordered = sorted(active, key=lambda p: -p["severity"])
            out[sid] = {
                "active": len(active),
                "worst": max((p["severity"] for p in active), default=0),
                "problems": [{"name": t(lang, p["key"]),
                              "severity": p["severity"],
                              "age_sec": int(now - p["since"])}
                             for p in ordered[:5]]}
        return out


def create_provider(store_ids: List[str]):
    """Zabbix из окружения, иначе эмулятор. Возвращает (провайдер, режим)."""
    url = os.environ.get("ZABBIX_URL")
    token = os.environ.get("ZABBIX_TOKEN")
    if url and token:
        host_map = {sid: sid for sid in store_ids}
        for pair in os.environ.get("ZABBIX_HOSTS", "").split(","):
            if "=" in pair:
                sid, host = pair.split("=", 1)
                host_map[sid.strip()] = host.strip()
        return ZabbixClient(url, token, host_map), "zabbix"
    return ZabbixEmulator(store_ids), "emulation"
