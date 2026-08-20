"""Эмулятор топливного контура: сеть АЗС Молдовы, нефтебаза, автозаказ
и рейсы бензовозов по дорожному графу.

Родственник :class:`network.StoreNetwork`/:class:`network.DistributionCenter`
(та же идея: склад с точкой перезаказа, отгрузки едут по реальным
дорогам, ИИ учится на телеметрии завершённых плеч), но — в отличие от
``network`` — **evolve-on-poll**, без фонового потока: весь мир
доигрывается внутри :meth:`FuelNetwork.state`, как это сделано в
``delivery.DeliveryHub``. Тикер ``network`` — единственное исключение
в проекте (см. ``docs/HANDOFF.md`` §3.3), новых заводить нельзя.

Станции и нефтебаза — реальные данные Artgranit (сняты 20.08.2026 с
``GET /api/plg/fuel/stations?lang=ru`` и ``/api/plg/fuel/trips``,
см. ``docs/PLAN_FUEL_AUTOORDER.md``), зашитые как стартовый набор:
контур обязан оставаться автономным (карта и данные — в репозитории),
Задача 3 добавит поверх них живой опрос Artgranit, глушащий эмуляцию
по таймауту тем же приёмом, что уже применён к Zabbix и GPS доставки.

Маршруты рейсов строятся вторым экземпляром :class:`roadnet.RoadNet` —
по молдавской карте (``static/data/moldova_map.geojson``) и с масштабом
долготы под широту Молдовы (~47°), а не тверским синглтоном
``get_roadnet()``.

API::

    net = FuelNetwork()
    st = net.state()
    # st["source"] == "emulation"; st["stations"], st["trips"], ...
"""

import email.utils
import json
import os
import random
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

from .eta_ai import _PRIOR_SPEED, get_predictor
from .i18n import DEFAULT_LANG, PluralRef, render_event, t
from .roadnet import RoadNet, _dist, cumulative, point_along

MOLDOVA_MAP = (Path(__file__).parent / "static" / "data"
              / "moldova_map.geojson")
#: средняя широта Молдовы — масштаб долготы roadnet считается под неё
#: (тверская модульная константа занижала бы расстояния на ~20%,
#: см. Задачу 2 «Шаг 0» плана и правку ``roadnet.RoadNet.__init__``)
MOLDOVA_REF_LAT = 47.0

#: скорость бензовоза в эмуляции, м/с — общий прогнозист ``eta_ai``
#: (класс ``tanker``, обоснование константы — там же, рядом с ней)
TANKER_SPEED = _PRIOR_SPEED["tanker"]

#: 1 секунда реального опроса = TIME_SCALE секунд «топливного» времени
#: расхода станций (по аналогии с ``network.TIME_SCALE``): без сжатия
#: суточный расход в 4-9 тыс. л был бы незаметен за время демо-прогона.
TIME_SCALE = 2400          # 1 с = 40 мин

MAX_DT = 5.0                # с: верхняя граница шага эволюции (evolve-on-poll)
REORDER_FRACTION = 0.42     # ниже этой доли ёмкости — станция уходит в заявку
FULL_FRACTION = 0.95        # бензовоз доливает станцию досюда
MAX_STOPS_PER_TRIP = 4
TRIP_CHECK_INTERVAL = 8.0   # с: не чаще одной проверки автозаказа
DISPATCH_DELAY = 3.0        # с: сборы бензовоза перед выездом
UNLOAD_S = 18.0             # с: слив на одной станции
TANKER_CAPACITY_L = 30000.0

#: допущение: ни один просмотренный эндпоинт Artgranit
#: (stations/trips/runs) не отдаёт координаты нефтебазы — реальные
#: координаты пос. Сынжера под Кишинёвом (сверено по открытым картам).
DEPOT_ID = 1
DEPOT_NAME = "Нефтебаза Сынжера"
DEPOT_LAT = 46.9503
DEPOT_LON = 28.8189
DEPOT_CAPACITY_L = 400_000.0
DEPOT_START_L = 248_000.0

DRIVERS = [
    "Андрей Чобану", "Виктор Ротару", "Сергей Морарь", "Ион Гуцу",
    "Дмитрий Раду", "Николае Плешка",
]

#: станции PECO: снято с живого Artgranit `GET /api/plg/fuel/stations`
#: (station_id, station_code, station_name, lat, lon, region,
#:  capacity_l, current_l, daily_rate_l, tank_count)
STATIONS: List[Tuple[int, str, str, float, float, str, int, int,
                     float, int]] = [
    (1, "AZS-001", "АЗС №1 Кишинёв", 46.972069, 28.902846, "Кишинёв",
     95000, 51909, 8621.3, 4),
    (2, "AZS-002", "АЗС №2 Кишинёв", 47.041620, 28.877657, "Кишинёв",
     90500, 49891, 8765.4, 4),
    (3, "AZS-003", "АЗС №3 Кишинёв", 46.983379, 28.879662, "Кишинёв",
     105500, 42689, 8447.8, 4),
    (4, "AZS-004", "АЗС №4 Кишинёв", 47.043423, 28.818922, "Кишинёв",
     100500, 48302, 9206.8, 4),
    (5, "AZS-005", "АЗС №5 Кишинёв", 47.038987, 28.840212, "Кишинёв",
     105000, 67828, 8036.2, 4),
    (6, "AZS-006", "АЗС №6 Кишинёв", 46.966366, 28.827270, "Кишинёв",
     100000, 50861, 7960.0, 4),
    (7, "AZS-007", "АЗС №7 Кишинёв", 46.996978, 28.899228, "Кишинёв",
     99000, 52702, 8188.7, 4),
    (8, "AZS-008", "АЗС №8 Кишинёв", 46.991205, 28.851815, "Кишинёв",
     103500, 58169, 8957.5, 4),
    (9, "AZS-009", "АЗС №9 Кишинёв", 47.032808, 28.863414, "Кишинёв",
     98500, 63949, 8124.9, 4),
    (10, "AZS-010", "АЗС №10 Кишинёв", 47.000902, 28.893250, "Кишинёв",
     98500, 60349, 8251.4, 4),
    (11, "AZS-011", "АЗС №1 Бэлць", 47.740081, 27.937269, "Бэлць",
     106000, 82452, 6153.0, 4),
    (12, "AZS-012", "АЗС №2 Бэлць", 47.775271, 27.898285, "Бэлць",
     92000, 42411, 5124.1, 4),
    (13, "AZS-013", "АЗС №3 Бэлць", 47.740819, 27.915681, "Бэлць",
     101500, 63046, 6336.3, 4),
    (14, "AZS-014", "АЗС №4 Бэлць", 47.760883, 27.959195, "Бэлць",
     91500, 55363, 6436.2, 4),
    (15, "AZS-015", "АЗС №5 Бэлць", 47.746795, 27.924214, "Бэлць",
     103500, 61721, 6335.7, 4),
    (16, "AZS-016", "АЗС №1 Кагул", 45.919225, 28.189746, "Кагул",
     109000, 64955, 5635.8, 4),
    (17, "AZS-017", "АЗС №2 Кагул", 45.893960, 28.177608, "Кагул",
     108000, 48672, 5733.2, 4),
    (18, "AZS-018", "АЗС №3 Кагул", 45.918741, 28.165732, "Кагул",
     101500, 60962, 5744.8, 4),
    (19, "AZS-019", "АЗС №1 Орхей", 47.371492, 28.815086, "Орхей",
     98500, 68756, 4664.9, 4),
    (20, "AZS-020", "АЗС №2 Орхей", 47.375187, 28.822245, "Орхей",
     101000, 52804, 5167.4, 4),
    (21, "AZS-021", "АЗС №3 Орхей", 47.388671, 28.837678, "Орхей",
     97000, 36613, 3755.3, 4),
    (22, "AZS-022", "АЗС №1 Унгень", 47.192107, 27.773435, "Унгень",
     93000, 51886, 4043.3, 4),
    (23, "AZS-023", "АЗС №2 Унгень", 47.211081, 27.817633, "Унгень",
     99000, 76113, 4526.3, 4),
    (24, "AZS-024", "АЗС №3 Унгень", 47.214852, 27.803489, "Унгень",
     98000, 62315, 4176.2, 4),
    (25, "AZS-025", "АЗС №1 Сорока", 48.167718, 28.295026, "Сорока",
     95500, 55516, 4351.9, 4),
    (26, "AZS-026", "АЗС №2 Сорока", 48.144565, 28.311716, "Сорока",
     104000, 51029, 4715.3, 4),
    (27, "AZS-027", "АЗС №3 Сорока", 48.153573, 28.290411, "Сорока",
     98500, 49068, 4154.3, 4),
    (28, "AZS-028", "АЗС №1 Комрат", 46.315067, 28.668115, "Комрат",
     94000, 56898, 3873.1, 4),
    (29, "AZS-029", "АЗС №2 Комрат", 46.281691, 28.660801, "Комрат",
     101500, 57350, 4268.3, 4),
    (30, "AZS-030", "АЗС №3 Комрат", 46.288415, 28.674821, "Комрат",
     101000, 51321, 4817.1, 4),
    (31, "AZS-031", "АЗС №1 Единец", 48.171254, 27.300511, "Единец",
     99500, 48845, 3811.0, 4),
    (32, "AZS-032", "АЗС №2 Единец", 48.154833, 27.305504, "Единец",
     99000, 68776, 4789.1, 4),
    (33, "AZS-033", "АЗС №1 Хынчешть", 46.840818, 28.568366, "Хынчешть",
     95000, 36819, 4505.5, 4),
    (34, "AZS-034", "АЗС №2 Хынчешть", 46.838784, 28.573093, "Хынчешть",
     95000, 66488, 4562.1, 4),
    (35, "AZS-035", "АЗС №1 Кэушень", 46.638095, 29.397684, "Кэушень",
     107500, 50874, 4834.7, 4),
    (36, "AZS-036", "АЗС №2 Кэушень", 46.632735, 29.421021, "Кэушень",
     98500, 53338, 4261.6, 4),
    (37, "AZS-037", "АЗС №1 Стрэшень", 47.135124, 28.593190, "Стрэшень",
     91000, 44403, 4255.9, 4),
    (38, "AZS-038", "АЗС №2 Стрэшень", 47.156226, 28.618052, "Стрэшень",
     100500, 58287, 4666.0, 4),
    (39, "AZS-039", "АЗС №1 Яловень", 46.952646, 28.791960, "Яловень",
     102000, 60509, 4008.1, 4),
    (40, "AZS-040", "АЗС №2 Яловень", 46.954707, 28.799132, "Яловень",
     108500, 51264, 4627.5, 4),
    (41, "AZS-041", "АЗС №1 Анений Ной", 46.866136, 29.235595,
     "Анений Ной", 102500, 56154, 4576.5, 4),
    (42, "AZS-042", "АЗС №2 Анений Ной", 46.891926, 29.222743,
     "Анений Ной", 106000, 59095, 4577.8, 4),
    (43, "AZS-043", "АЗС №1 Фэлешть", 47.572483, 27.726505, "Фэлешть",
     96000, 49254, 4493.0, 4),
    (44, "AZS-044", "АЗС №2 Фэлешть", 47.576906, 27.729727, "Фэлешть",
     100500, 38485, 4124.8, 4),
    (45, "AZS-045", "АЗС №1 Ниспорень", 47.087572, 28.177674,
     "Ниспорень", 99500, 54341, 4385.5, 4),
    (46, "AZS-046", "АЗС №2 Ниспорень", 47.066342, 28.167377,
     "Ниспорень", 101000, 51460, 3858.7, 4),
]

#: марки топлива и их цвета — отраслевое соглашение цвета пистолета на
#: колонках Молдовы/Румынии (95 — зелёный, 98 — синий, ДТ — жёлтый,
#: 92 — красный/оранжевый), а не произвольный выбор; используется и
#: 3D-планограммой станции (fuelviz.py), и легендой сцены.
#: Доля (3-е значение) — типовая структура продаж АЗС по маркам,
#: нужна только чтобы разложить ЕДИНЫЙ агрегированный остаток станции
#: (Artgranit отдаёт только суммарные capacity_l/current_l, без разбивки
#: по цистернам) на правдоподобные отдельные цистерны для сцены — см.
#: `station_tanks()`.
FUEL_GRADES: List[Tuple[str, str, float]] = [
    ("A95", "#2e7d32", 0.34),
    ("A92", "#c62828", 0.20),
    ("DT", "#f9a825", 0.36),
    ("A98", "#1565c0", 0.10),
]
FUEL_GRADE_COLOR: Dict[str, str] = {g: c for g, c, _ in FUEL_GRADES}


def station_tanks(station: dict) -> List[dict]:
    """Раскладка агрегированного остатка станции по 4 цистернам/маркам.

    ERP Artgranit (и наш эмулятор вслед за ней) отдаёт по станции только
    суммарные ``capacity_l``/``current_l`` — без разбивки по маркам, хотя
    физически на станции 4 отдельные подземные цистерны с разным
    топливом. Для 3D-планограммы (где ключевая деталь — «в какой
    цистерне сколько») эта разбивка обязана быть, поэтому раскладываем
    сами: ёмкость делится по типовой структуре продаж (`FUEL_GRADES`),
    заполненность каждой цистерны — среднее по станции ± небольшой
    детерминированный (seed = id станции) разброс, иначе все 4 цистерны
    выглядели бы залитыми ровно на одинаковый процент — нечитаемо на
    сцене. Это визуальная реконструкция, а не факт ERP: суммарные литры
    станции остаются те, что пришли от Artgranit/эмулятора, разбивка по
    цистернам — наше допущение, явно описанное в отчёте задачи."""
    cap_total = float(station.get("capacity_l") or 0.0)
    cur_total = float(station.get("current_l") or 0.0)
    base_fill = (cur_total / cap_total) if cap_total else 0.0
    tanks = []
    for i, (grade, color, weight) in enumerate(FUEL_GRADES):
        cap = cap_total * weight
        rnd = random.Random(int(station.get("id", 0)) * 97 + i)
        fill = max(0.03, min(0.98, base_fill + rnd.uniform(-0.12, 0.12)))
        tanks.append({"grade": grade, "color": color,
                      "capacity_l": round(cap), "current_l": round(cap * fill),
                      "fill_ratio": round(fill, 3)})
    return tanks


Node = Tuple[float, float]                      # (lon, lat)


def _geo_dist(net: RoadNet, a: Node, b: Node) -> float:
    """Расстояние (м) между координатами с масштабом конкретного графа."""
    return _dist(a, b, net.kx)


# ---------------------------------------------------------------------------
# Задача 3: живой поток из Artgranit — тот же приём, что REAL_GPS_TIMEOUT
# в delivery.py и create_provider в zabbix.py: реальные данные глушат
# эмулятор по таймауту, а не заменяют его насовсем.
# ---------------------------------------------------------------------------

#: адрес ERP Artgranit; без переменной окружения контур остаётся
#: полностью автономным (клиент не создаётся, опросов нет) — так и
#: должно быть по умолчанию (инвариант «карта автономна», HANDOFF §3.5)
ARTGRANIT_URL = os.environ.get("ARTGRANIT_URL", "").rstrip("/") or None
#: таймаут одного HTTP-запроса к Artgranit, с
ARTGRANIT_TIMEOUT = float(os.environ.get("ARTGRANIT_TIMEOUT", "3.0"))
#: не опрашивать Artgranit чаще этого интервала (evolve-on-poll: опрос
#: вписан в state(), отдельного потока нет — см. Задачу 3 плана)
ARTGRANIT_POLL_INTERVAL = float(
    os.environ.get("ARTGRANIT_POLL_INTERVAL", "5.0"))
#: реальные данные считаются «свежими» и глушат эмуляцию это время после
#: последнего успешного опроса; истёк — контур сам возвращается к
#: эмуляции (образец — REAL_GPS_TIMEOUT в delivery.py: там 45 с при
#: телеметрии courier-приложения раз в несколько секунд; здесь опрос
#: реже, поэтому окно шире — переживает 3-4 подряд неудачных опроса)
REAL_ARTGRANIT_TIMEOUT = float(
    os.environ.get("REAL_ARTGRANIT_TIMEOUT", "20.0"))

#: адрес ERP для кнопки-перехода «в учётную систему» в шапке /fuel.
#: Это НЕ то же самое, что автономность ARTGRANIT_URL выше (там пусто по
#: умолчанию — контур не опрашивает ERP): кнопка ведёт человека мышкой,
#: а не открывает сетевой канал, поэтому у неё есть рабочий дефолт из
#: коробки. Если ARTGRANIT_URL задан (живой опрос включён) — берём тот
#: же адрес, чтобы не держать два разных адреса одного ERP.
ARTGRANIT_BASE_URL = (
    os.environ.get("ARTGRANIT_URL", "").rstrip("/")
    or "http://127.0.0.1:3003")

#: сколько секунд после act_return показывать завершённый реальный рейс
#: на карте (то же окно, что у эмулятора, см. FuelNetwork._evolve_trips)
DONE_TRIP_RETENTION_S = 90.0


class ArtgranitClient:
    """HTTP-клиент внешней ERP Artgranit — только чтение (GET).

    Никаких записей: инициацию автозаказа выполняет оператор в самой
    Artgranit (POST /api/plg/fuel/autoorder), planogram3d — витрина.
    """

    def __init__(self, base_url: str, timeout: float = ARTGRANIT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> list:
        req = urllib.request.Request(
            self.base_url + path, method="GET",
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Artgranit {path}: HTTP {resp.status}")
            body = resp.read().decode("utf-8")
        payload = json.loads(body)
        if not payload.get("success"):
            raise RuntimeError(f"Artgranit {path}: success=false в ответе")
        return payload.get("data", [])

    def get_stations(self) -> list:
        return self._get("/api/plg/fuel/stations")

    def get_trips(self) -> list:
        return self._get("/api/plg/fuel/trips")


def _parse_rfc1123(value: Optional[str]) -> Optional[float]:
    """RFC 1123 → unix-время; Artgranit отдаёт даты только так."""
    if not value:
        return None
    try:
        return email.utils.parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        return None


class FuelNetwork:
    """Эмулятор сети АЗС, нефтебазы и рейсов бензовозов (evolve-on-poll)."""

    def __init__(self, map_path: Optional[Path] = None,
                ref_lat: float = MOLDOVA_REF_LAT, seed: int = 20260820):
        self.rng = random.Random(seed)
        self.net = RoadNet(Path(map_path) if map_path else MOLDOVA_MAP,
                           ref_lat=ref_lat)
        self.stations: Dict[int, dict] = {
            sid: {"id": sid, "code": code, "name": name, "lat": lat,
                  "lon": lon, "region": region, "capacity_l": float(cap),
                  "current_l": float(cur), "daily_rate_l": float(rate),
                  "tank_count": tanks}
            for sid, code, name, lat, lon, region, cap, cur, rate, tanks
            in STATIONS
        }
        self.depot = {"id": DEPOT_ID, "name": DEPOT_NAME,
                      "lat": DEPOT_LAT, "lon": DEPOT_LON,
                      "capacity_l": DEPOT_CAPACITY_L,
                      "current_l": DEPOT_START_L}
        self.trips: Dict[str, dict] = {}
        self.runs: Deque[dict] = deque(maxlen=10)
        self.events: Deque[dict] = deque(maxlen=40)
        self._trip_seq = 1
        self._run_seq = 1
        self._driver_pool = list(DRIVERS)
        self.rng.shuffle(self._driver_pool)
        self._driver_idx = 0
        self._last = time.time()
        self._next_trip_check = time.time() + 2.0

        # Задача 3: клиент Artgranit создаётся только если задан адрес —
        # иначе контур не делает ни одного сетевого вызова (автономность
        # по умолчанию сохраняется)
        self._client = (ArtgranitClient(ARTGRANIT_URL)
                        if ARTGRANIT_URL else None)
        self._next_poll = 0.0          # evolve-on-poll: время следующего опроса
        self._last_real = 0.0          # время последнего успешного опроса
        self._real_cache: Optional[dict] = None   # {"stations":…, "trips":…}
        self._real_mode = False        # для лога переходов эмуляция↔реал

    # ----- события --------------------------------------------------------
    def _log(self, icon: str, key: str, count=None, **params) -> None:
        """Запись ленты событий: ключ+параметры вместо готовой строки —
        язык выбирается при отдаче в `state()` (см. `i18n.render_event`),
        тем же приёмом, что и в `network._ev`."""
        self.events.appendleft({"t": time.time(), "icon": icon, "key": key,
                                "params": params, "count": count})

    def _next_driver(self) -> str:
        d = self._driver_pool[self._driver_idx % len(self._driver_pool)]
        self._driver_idx += 1
        return d

    # ----- расход топлива на станциях --------------------------------------
    def _consume(self, dt: float) -> None:
        """Списание запаса станций по суточной норме (сжатое время)."""
        for st in self.stations.values():
            rate_s = st["daily_rate_l"] / 86400.0
            st["current_l"] = max(0.0, st["current_l"]
                                  - rate_s * dt * TIME_SCALE)

    # ----- автозаказ и диспетчеризация рейсов ------------------------------
    def _pending_station_ids(self) -> set:
        return {stop["station_id"] for t in self.trips.values()
               if t["status"] == "en_route" for stop in t["stops"]}

    def _low_stations(self) -> List[dict]:
        pending = self._pending_station_ids()
        return [s for s in self.stations.values()
               if s["current_l"] < s["capacity_l"] * REORDER_FRACTION
               and s["id"] not in pending]

    def _maybe_dispatch(self, now: float) -> None:
        if now < self._next_trip_check:
            return
        self._next_trip_check = now + TRIP_CHECK_INTERVAL
        low = self._low_stations()
        if not low:
            return
        low.sort(key=lambda s: s["current_l"] / s["capacity_l"])
        batch = low[:MAX_STOPS_PER_TRIP]

        # ближайший сосед от нефтебазы — порядок объезда (как в
        # delivery.DeliveryHub._build_routes для курьерских маршрутов)
        ordered: List[dict] = []
        cur = (self.depot["lon"], self.depot["lat"])
        pool = list(batch)
        while pool:
            nxt = min(pool, key=lambda s: _geo_dist(
                self.net, cur, (s["lon"], s["lat"])))
            pool.remove(nxt)
            ordered.append(nxt)
            cur = (nxt["lon"], nxt["lat"])

        # бензовоз возит несколько секций (как реальный: tank_count=4 у
        # станций, comp_count у рейсов Artgranit) — на станцию достаётся
        # не больше объёма одной секции, а не полный бак насухо
        max_per_stop = TANKER_CAPACITY_L / MAX_STOPS_PER_TRIP

        full_path: List[Node] = []
        stops: List[dict] = []
        prev = (self.depot["lon"], self.depot["lat"])
        cum_dist = 0.0
        liters_total = 0.0
        for st in ordered:
            leg_path, leg_m = self.net.route(prev[0], prev[1],
                                             st["lon"], st["lat"])
            if full_path and leg_path and full_path[-1] == leg_path[0]:
                leg_path = leg_path[1:]
            full_path.extend(leg_path)
            cum_dist += leg_m
            needed = max(0.0, st["capacity_l"] * FULL_FRACTION
                        - st["current_l"])
            liters = max(500.0, min(needed, max_per_stop))
            liters_total += liters
            stops.append({"station_id": st["id"], "name": st["name"],
                          "liters": round(liters), "cum_dist": cum_dist,
                          "status": "pending"})
            prev = (st["lon"], st["lat"])
        if len(full_path) < 2:
            return                                # маршрут не построился

        cum = cumulative(full_path, self.net.kx)
        total_len = cum[-1]
        depart = now + DISPATCH_DELAY
        # плановое время прохождения каждой остановки (для eta_ts/⏱)
        t_cursor = depart
        prev_cum = 0.0
        for stop in stops:
            leg_m = stop["cum_dist"] - prev_cum
            t_cursor += max(3.0, leg_m / TANKER_SPEED) + UNLOAD_S
            stop["eta_ts"] = t_cursor
            prev_cum = stop["cum_dist"]

        trip_id = f"FT-{self._trip_seq:04d}"
        self._trip_seq += 1
        driver = self._next_driver()
        self.trips[trip_id] = {
            "id": trip_id, "driver": driver,
            "liters": round(liters_total),
            "load_pct": round(100 * min(
                1.0, liters_total / TANKER_CAPACITY_L)),
            "depart": depart, "eta": t_cursor,
            "path": [[round(p[0], 5), round(p[1], 5)] for p in full_path],
            "_cum": cum, "leg_pos": 0.0, "_leg_start_ts": depart,
            "_prev_cum": 0.0, "stops": stops, "status": "en_route",
        }
        run_id = f"RUN-{self._run_seq:04d}"
        self._run_seq += 1
        self.runs.appendleft({
            "id": run_id, "status": "done", "order_count": len(stops),
            "station_count": len(stops), "liters_total": round(liters_total),
            "started_at": now, "finished_at": now,
            # текст прогона тоже ключ+параметры — переводится в state(),
            # см. комментарий у _log
            "msg_key": "fuel.run.message",
            "msg_params": {"n": len(stops), "qty": round(liters_total),
                          "trip": trip_id},
        })
        names = ", ".join(s["name"] for s in stops)
        self._log("🛢", "fuel.log.autoorder_dispatch", trip=trip_id,
                  driver=driver, names=names)

    # ----- движение бензовозов ----------------------------------------------
    def _evolve_trips(self, now: float, dt: float) -> None:
        """Движение бензовоза + видимый слив на остановке.

        Раньше остановка мгновенно переключалась pending → done в момент
        проезда точки — «разгрузка» была нулевой длительности и её
        нечем было бы показать на 3D-планограмме станции (владелец
        прямо просил: слив должен быть виден как процесс). Теперь между
        ними есть стадия ``unloading`` длиной ``UNLOAD_S``: грузовик
        стоит у горловины (leg_pos не растёт, пока активна разгрузка),
        а уровень в цистерне станции растёт линейно от базового значения
        к базовому+liters — 3D-сцена станции читает именно эту стадию.
        """
        predictor = get_predictor()
        for trip in list(self.trips.values()):
            if trip["status"] != "en_route" or now < trip["depart"]:
                continue
            total_len = trip["_cum"][-1]
            active = next((s for s in trip["stops"]
                          if s["status"] == "unloading"), None)
            if active is None:
                trip["leg_pos"] = min(total_len, trip["leg_pos"]
                                      + TANKER_SPEED * dt)
            for stop in trip["stops"]:
                if (stop["status"] == "pending"
                        and trip["leg_pos"] >= stop["cum_dist"] - 1.0):
                    stop["status"] = "unloading"
                    stop["_unload_start"] = now
                    stop["_unload_base_l"] = \
                        self.stations[stop["station_id"]]["current_l"]
                    trip["leg_pos"] = stop["cum_dist"]   # стоим у горловины
                elif stop["status"] == "unloading":
                    frac = min(1.0, (now - stop["_unload_start"]) / UNLOAD_S)
                    station = self.stations[stop["station_id"]]
                    station["current_l"] = min(
                        station["capacity_l"],
                        stop["_unload_base_l"] + stop["liters"] * frac)
                    if frac >= 1.0:
                        stop["status"] = "done"
                        leg_m = stop["cum_dist"] - trip["_prev_cum"]
                        elapsed = max(1.0, now - trip["_leg_start_ts"])
                        predictor.observe("tanker", leg_m, elapsed)
                        trip["_prev_cum"] = stop["cum_dist"]
                        trip["_leg_start_ts"] = now
                        self._log("⛽", "fuel.log.tanker_fill",
                                  trip=trip["id"], name=stop["name"],
                                  qty=stop["liters"])
            if (trip["leg_pos"] >= total_len - 1.0
                    and all(s["status"] == "done" for s in trip["stops"])):
                trip["status"] = "done"
                trip["_done_at"] = now
                self._log("✅", "fuel.log.trip_done", trip=trip["id"],
                          driver=trip["driver"])
        # завершённые рейсы держим на экране ещё немного, потом чистим
        self.trips = {k: v for k, v in self.trips.items()
                      if v["status"] == "en_route"
                      or now - v.get("_done_at", now) < 90}

    # ----- Artgranit: опрос и преобразование форм ---------------------------
    def _station_from_artgranit(self, s: dict) -> dict:
        """Форма Artgranit → форма станции контура (та же, что у эмулятора)."""
        capacity = float(s["capacity_l"])
        current = float(s["current_l"])
        fill = current / capacity if capacity else 0.0
        daily_rate = float(s.get("daily_rate_l") or 0.0)
        days_to_dry = current / daily_rate if daily_rate > 0 else 999.0
        return {
            "id": s["station_id"], "code": s["station_code"],
            "name": s["station_name"], "lat": s["lat"], "lon": s["lon"],
            "region": s.get("region") or "", "capacity_l": round(capacity),
            "current_l": round(current), "fill_pct": round(100 * fill, 1),
            "days_to_dry": round(days_to_dry, 2),
            "is_low": fill < REORDER_FRACTION,
        }

    def _trip_from_artgranit(self, t: dict, now: float) -> Optional[dict]:
        """Форма Artgranit → форма рейса контура, или None, если рейс не
        интересен экрану (ещё не выехал, либо завершился давно)."""
        status = t.get("status")
        act_return = _parse_rfc1123(t.get("act_return"))
        if status == "en_route":
            pass
        elif (status == "done" and act_return is not None
              and now - act_return < DONE_TRIP_RETENTION_S):
            pass
        else:
            return None                     # planned/cancelled/старый done

        depart = (_parse_rfc1123(t.get("act_depart"))
                 or _parse_rfc1123(t.get("plan_depart")) or now)

        # компоненты (секции цистерны) группируются в станции-остановки —
        # у Artgranit несколько строк stops с одинаковым station_id это
        # разные отсеки одной физической остановки, а не разные заезды
        by_station: "Dict[int, dict]" = {}
        order: List[int] = []
        for raw in t.get("stops") or []:
            sid = raw.get("station_id")
            if sid is None:
                continue
            if sid not in by_station:
                by_station[sid] = {
                    "station_id": sid, "name": raw.get("station_name", ""),
                    "lat": raw.get("lat"), "lon": raw.get("lon"),
                    "liters": 0.0,
                    "eta_ts": _parse_rfc1123(raw.get("plan_arrive")),
                }
                order.append(sid)
            liters = raw.get("liters_fact")
            if liters is None:
                liters = raw.get("liters_plan") or 0.0
            by_station[sid]["liters"] += float(liters)

        # маршрут строится нашим RoadNet по молдавской карте — своей
        # полилинии у рейса Artgranit нет (см. Задачу 3 плана)
        prev = (self.depot["lon"], self.depot["lat"])
        full_path: List[Node] = []
        cum_dist = 0.0
        for sid in order:
            stop = by_station[sid]
            if stop["lat"] is None or stop["lon"] is None:
                continue                    # без координат остановку не проложить
            leg_path, leg_m = self.net.route(prev[0], prev[1],
                                             stop["lon"], stop["lat"])
            if full_path and leg_path and full_path[-1] == leg_path[0]:
                leg_path = leg_path[1:]
            full_path.extend(leg_path)
            cum_dist += leg_m
            stop["cum_dist"] = cum_dist
            stop["status"] = "done" if status == "done" else "pending"
            prev = (stop["lon"], stop["lat"])
        if len(full_path) < 2:
            return None                     # ни одной остановки с координатами

        cum = cumulative(full_path, self.net.kx)
        total_len = cum[-1]
        stops_out = [{"station_id": by_station[sid]["station_id"],
                      "name": by_station[sid]["name"],
                      "liters": round(by_station[sid]["liters"]),
                      "eta_ts": by_station[sid]["eta_ts"],
                      "status": by_station[sid]["status"]}
                     for sid in order if "cum_dist" in by_station[sid]]
        eta = max((s["eta_ts"] for s in stops_out if s["eta_ts"]),
                 default=depart + total_len / TANKER_SPEED)

        # позиция: реальный GPS, если Artgranit его отдаёт (last_lat/lon);
        # почти всегда null (провайдер GPS не подключён, см. план) —
        # тогда считаем позицию по маршруту и плановому времени, как в
        # эмуляции, а не показываем рейс неподвижным у нефтебазы
        if t.get("last_lat") is not None and t.get("last_lon") is not None:
            lat, lon = float(t["last_lat"]), float(t["last_lon"])
            progress = 0.0 if total_len <= 0 else min(
                1.0, _geo_dist(self.net, (self.depot["lon"],
                                          self.depot["lat"]),
                               (lon, lat)) / total_len)
        else:
            span = max(1.0, eta - depart)
            progress = 0.0 if status == "done" else max(
                0.0, min(1.0, (now - depart) / span))
            path_pts = [tuple(p) for p in full_path]
            lon, lat = point_along(path_pts, cum, progress * total_len)

        return {
            "id": f"AG-{t['id']}", "driver": t.get("driver_name") or "—",
            "liters": round(float(t.get("liters_total") or 0.0)),
            "load_pct": round(float(t.get("load_pct") or 0.0)),
            "depart": depart, "eta": eta,
            "progress": round(1.0 if status == "done" else progress, 3),
            "lat": round(lat, 5), "lon": round(lon, 5),
            "status": status,
            "path": [[round(p[0], 5), round(p[1], 5)] for p in full_path],
            "stops": stops_out,
        }

    def _poll_artgranit(self, now: float) -> None:
        """Опрос Artgranit — не чаще ARTGRANIT_POLL_INTERVAL, без потока:
        вызывается изнутри state(), как и весь остальной evolve-on-poll."""
        if self._client is None or now < self._next_poll:
            return
        self._next_poll = now + ARTGRANIT_POLL_INTERVAL
        try:
            stations_raw = self._client.get_stations()
            if not stations_raw:
                raise ValueError("пустой список станций")
            trips_raw = self._client.get_trips()
            stations_out = [self._station_from_artgranit(s)
                            for s in stations_raw]
            trips_out = [trip for trip in
                        (self._trip_from_artgranit(t, now)
                         for t in trips_raw) if trip is not None]
        except Exception as exc:
            # сеть, таймаут, не-200, битый JSON — контур остаётся на
            # последних свежих данных до истечения REAL_ARTGRANIT_TIMEOUT,
            # а не падает и не показывает пустой экран (инвариант плана)
            if self._real_mode:
                self._log("⚠", "fuel.log.artgranit_down", error=str(exc))
            return
        self._real_cache = {"stations": stations_out, "trips": trips_out}
        self._last_real = now
        if not self._real_mode:
            n_trips = len(trips_out)
            self._log("🔌", "fuel.log.artgranit_up",
                      n=len(stations_out), n2=n_trips,
                      trips_word=PluralRef(
                          "ai.forecast_trained_trips.trips_word",
                          count=n_trips))
        self._real_mode = True

    # ----- табло прибытия (ИИ) ----------------------------------------------
    def arrival_board(self, station_id, lang: str = DEFAULT_LANG
                      ) -> Optional[dict]:
        """Онлайн-табло прибытия АЗС: бензовозы в пути к ней, с ИИ-прогнозом
        (±σ) — та же форма ответа, что у ``network.arrival_board`` и
        ``delivery.arrival_board`` (``{"now", "point", "rows", "model"}``),
        чтобы фронтенд табло с ``/delivery`` переиспользовался как есть."""
        try:
            sid = int(station_id)
        except (TypeError, ValueError):
            return None
        predictor = get_predictor()
        now = time.time()
        st = self.state(lang)               # тот же снимок, что видит карта
        station = next((s for s in st["stations"] if s["id"] == sid), None)
        if station is None:
            return None
        rows = []
        for trip in st["trips"]:
            if trip["status"] != "en_route":
                continue
            stop = next((sp for sp in trip["stops"]
                        if sp["station_id"] == sid and sp["status"] != "done"),
                       None)
            if stop is None:
                continue
            # остаток пути до станции — по прямой с запасом на извилистость
            # дороги (тот же приём, что в delivery._ai_stop_predictions для
            # плеча без точного дорожного остатка)
            remaining_m = 1.25 * _geo_dist(
                self.net, (trip["lon"], trip["lat"]),
                (station["lon"], station["lat"]))
            eta_s, sigma_s, n_obs = predictor.predict("tanker", remaining_m)
            rows.append({
                "type": "tanker", "icon": "🚛",
                "label": t(lang, "fuel.eta.tanker_row", trip=trip["id"],
                          driver=trip["driver"], liters=stop["liters"]),
                "eta_sec": round(eta_s),
                "sigma_sec": round(max(3.0, sigma_s)),
                "eta_ts": now + eta_s,
                "plan_ts": stop.get("eta_ts") or trip["eta"],
                "progress": trip["progress"],
                "source": (t(lang, "ai.forecast_trained_trips", count=n_obs,
                             n=n_obs, trips_word=t(
                                 lang, "ai.forecast_trained_trips.trips_word",
                                 count=n_obs))
                          if n_obs else t(lang, "ai.forecast_prior")),
            })
        rows.sort(key=lambda r: r["eta_ts"])
        return {"now": now, "point": station["name"], "station_id": sid,
                "source": st["source"], "rows": rows,
                "model": predictor.summary()}

    # ----- снимок состояния (evolve-on-poll) --------------------------------
    def state(self, lang: str = DEFAULT_LANG) -> dict:
        now = time.time()
        dt = min(MAX_DT, now - self._last)
        self._last = now

        self._consume(dt)
        self._maybe_dispatch(now)
        self._evolve_trips(now, dt)
        self._poll_artgranit(now)

        is_real = (self._real_cache is not None
                  and now - self._last_real < REAL_ARTGRANIT_TIMEOUT)
        if self._real_mode and not is_real:
            self._log("↩️", "fuel.log.artgranit_offline",
                      sec=round(REAL_ARTGRANIT_TIMEOUT))
            self._real_mode = False
        # текст ленты и прогонов собирается здесь, на языке запроса — сами
        # записи хранят только ключ+параметры (см. `_log`/`i18n.render_event`)
        runs_out = [{**{k: v for k, v in r.items()
                        if k not in ("msg_key", "msg_params")},
                    "message": t(lang, r["msg_key"], **r["msg_params"])}
                   for r in self.runs]
        events_out = [{"t": ev["t"], "text": render_event(lang, ev)}
                     for ev in list(self.events)[:20]]
        if is_real:
            return {
                "now": now, "source": "artgranit",
                "depot": {**self.depot,
                         "fill_pct": round(100 * self.depot["current_l"]
                                           / self.depot["capacity_l"], 1)},
                "stations": self._real_cache["stations"],
                "trips": self._real_cache["trips"],
                "runs": runs_out,
                "events": events_out,
            }

        stations_out = []
        for st in self.stations.values():
            fill = st["current_l"] / st["capacity_l"]
            days_to_dry = (st["current_l"] / st["daily_rate_l"]
                          if st["daily_rate_l"] > 0 else 999.0)
            stations_out.append({
                "id": st["id"], "code": st["code"], "name": st["name"],
                "lat": st["lat"], "lon": st["lon"], "region": st["region"],
                "capacity_l": round(st["capacity_l"]),
                "current_l": round(st["current_l"]),
                "fill_pct": round(100 * fill, 1),
                "days_to_dry": round(days_to_dry, 2),
                "is_low": fill < REORDER_FRACTION,
            })

        trips_out = []
        for trip in self.trips.values():
            path = [tuple(p) for p in trip["path"]]
            lon, lat = (point_along(path, trip["_cum"], trip["leg_pos"])
                       if now >= trip["depart"] else
                       (self.depot["lon"], self.depot["lat"]))
            progress = (trip["leg_pos"] / trip["_cum"][-1]
                       if trip["_cum"][-1] > 0 else 0.0)
            trips_out.append({
                "id": trip["id"], "driver": trip["driver"],
                "liters": trip["liters"], "load_pct": trip["load_pct"],
                "depart": trip["depart"], "eta": trip["eta"],
                "progress": round(progress, 3),
                "lat": round(lat, 5), "lon": round(lon, 5),
                "status": trip["status"], "path": trip["path"],
                "stops": [{
                    "station_id": s["station_id"], "name": s["name"],
                    "liters": s["liters"], "eta_ts": s["eta_ts"],
                    "status": s["status"],
                    **({"unload_frac": round(
                            min(1.0, (now - s["_unload_start"]) / UNLOAD_S), 3)}
                       if s["status"] == "unloading" else {}),
                } for s in trip["stops"]],
            })

        return {
            "now": now, "source": "emulation",
            "depot": {**self.depot,
                     "fill_pct": round(100 * self.depot["current_l"]
                                       / self.depot["capacity_l"], 1)},
            "stations": stations_out,
            "trips": trips_out,
            "runs": runs_out,
            "events": events_out,
        }
