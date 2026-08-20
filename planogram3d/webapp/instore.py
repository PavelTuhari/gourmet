"""Игровая симуляция торгового зала: события касс, весов, СКО, CCTV,
позиционирование ТСД, телеметрия холодильников и учёт расходников.

Для каждого магазина создаётся :class:`InstoreSim` — «живой» торговый зал
в духе игровых симуляторов магазинов:

* покупатели-агенты входят в зал (событие видеонаблюдения), ходят к
  реальным стеллажам планограммы, берут товар, взвешивают на весах,
  оплачивают на кассе или в зоне касс самообслуживания (СКО) и выходят;
* **очереди у касс** измеряются в реальном времени (по позициям агентов
  либо по событиям видеоаналитики) и выводятся на схему зала;
* по датчикам входа/выхода оценивается **число покупателей в зале**;
  за вычетом стоящих в очередях остальные равномерно случайно
  распределяются по залу («призраки»-оценки);
* **ТСД** (терминалы сбора данных) позиционируются по маякам
  Bluetooth LE в торговой зоне и датчикам LoRa на остальной площади —
  с реалистичной точностью и шумом измерений;
* **холодильные витрины** отдают телеметрию: температура, дверца,
  компрессор; выход за уставку порождает тревогу;
* ведётся **учёт расходников**: чековая лента фискальников (каждая
  касса и СКО), лента этикеток весов, кульки для овощей; низкий остаток
  порождает событие и заявку на замену;
* зоны выкладки **скоропортящихся продуктов** (молочная группа,
  холодильники) особо выделяются на схеме.

Источники потока:

* **тестовый** — встроенный эмулятор (по умолчанию);
* **реальный** — те же события принимаются по
  ``POST /api/instore/<store_id>/ingest``; пока реальный поток активен,
  эмулятор перестаёт порождать новых покупателей. Дополнительно к
  событиям покупателей принимаются ``queue`` (длина очереди от
  видеоаналитики: ``{"register": "Касса 1", "len": 3}``) и ``fridge``
  (телеметрия холодильника: ``{"id": "ХВ-1", "temp_c": 4.2,
  "door_open": false}``).
"""

import math
import random
import threading
import time
from collections import deque
from typing import Dict, List, Optional

from ..core import Store
from .i18n import DEFAULT_LANG, t
from .network import price_for

WALK_SPEED = 0.85          # м/с
REAL_FEED_TIMEOUT = 60.0   # с: реальный поток считается активным

# ----- геометрия зала (метры) -------------------------------------------
ENTRANCE = (7.0, 5.3)      # вход (датчик видеонаблюдения)
EXIT = (7.35, 0.25)        # выход
SCALES = (4.6, 4.6)        # весы самообслуживания
SCO_RECT = (4.2, 0.2, 1.3, 1.6)   # зона касс самообслуживания (x, y, w, d)
SCO_GATE = (4.85, 2.05)    # ворота зоны СКО
SCO_PAY = (4.85, 0.95)     # терминал СКО
POS_DESKS = [("Касса 1", 6.15, 1.0), ("Касса 2", 7.0, 1.0)]
POS_QUEUE_Y = 1.85         # где стоит покупатель перед кассой
HALL = (-0.5, -0.3, 7.6, 5.9)     # границы зала (x, y, xmax, ymax)

#: категории скоропортящихся товаров (особые зоны на схеме)
PERISHABLE_CATEGORIES = {"Молочные продукты"}

#: холодильные витрины: (id, x, y, w, d)
FRIDGES = [("ХВ-1", 0.25, 5.05, 1.15, 0.55),
           ("ХВ-2", 1.65, 5.05, 1.15, 0.55)]
FRIDGE_SETPOINT = 4.0      # °C
FRIDGE_WARN, FRIDGE_ALARM = 6.0, 8.0

#: ТСД: маяки BLE покрывают торговую зону (x < 4.5), дальше — LoRa
TSD_DEVICES = ["ТСД-1", "ТСД-2", "ТСД-3"]
BLE_ZONE_X = 4.5


def _display_label(lang: str, canonical: str) -> str:
    """Переводит внутренний (русский) идентификатор устройства/точки зала
    в подпись на языке запроса — только для отдачи клиенту.

    Идентификаторы («Касса 1», «ХВ-1», «ТСД-1», ...) остаются русскими
    во внутреннем состоянии и в реальном потоке `ingest()` (это стабильные
    ключи для сопоставления с очередями/расходниками/холодильниками —
    их переименование по языку сломало бы это сопоставление), поэтому
    перевод — только косметический слой поверх них, применяемый в
    `state()` перед отдачей в JSON, как и лента событий (см. `network.py`).
    """
    if canonical.startswith("Касса "):
        return t(lang, "instore.label.pos_n", n=canonical.split(" ")[1])
    if canonical.startswith("ХВ-"):
        return t(lang, "instore.label.fridge_n", n=canonical.split("-")[1])
    if canonical.startswith("ТСД-"):
        return t(lang, "instore.label.tsd_n", n=canonical.split("-")[1])
    mapping = {"Весы": "instore.label.scales", "СКО": "instore.label.sco",
              "Вход": "instore.label.entrance", "Выход": "instore.label.exit"}
    key = mapping.get(canonical)
    return t(lang, key) if key else canonical


class InstoreSim:
    """Симуляция торгового зала одного магазина."""

    def __init__(self, store: Store, seed: int = 1):
        self.store = store
        self.rng = random.Random(seed * 7919)
        self.events: deque = deque(maxlen=300)
        self._next_event_id = 1
        self.agents: Dict[int, dict] = {}
        self._next_agent_id = 1
        self._next_spawn = time.time() + self.rng.uniform(0.5, 2.0)
        self.last_real_ts = 0.0
        self._lock = threading.Lock()
        self._last_evolve = time.time()
        self.counters = {"visitors_today": 0, "in_store": 0, "receipts": 0,
                         "revenue": 0.0, "sco_receipts": 0, "weighings": 0}

        # холодильники
        self.fridges = [{"id": fid, "x": x, "y": y, "w": w, "d": d,
                         "temp": FRIDGE_SETPOINT + self.rng.uniform(-.5, .5),
                         "door_open": False, "door_until": 0.0,
                         "compressor": False, "alarmed": False}
                        for fid, x, y, w, d in FRIDGES]

        # ТСД (терминалы сбора данных)
        self.tsd = [{"id": tid,
                     "x": self.rng.uniform(0.5, 6.5),
                     "y": self.rng.uniform(0.5, 5.0),
                     "tx": 0.0, "ty": 0.0, "retarget": 0.0,
                     "battery": self.rng.uniform(55, 100)}
                    for tid in TSD_DEVICES]

        # расходники: % ленты по устройствам и кульки, шт.
        self.consumables = {"Касса 1": self.rng.uniform(40, 100),
                            "Касса 2": self.rng.uniform(40, 100),
                            "СКО": self.rng.uniform(40, 100),
                            "Весы": self.rng.uniform(40, 100)}
        self.veg_bags = self.rng.randint(180, 480)
        self._replacements: Dict[str, float] = {}   # устройство -> время замены
        self._bags_order: Optional[float] = None

        # очереди, сообщённые реальной видеоаналитикой (событие queue)
        self.reported_queues: Dict[str, int] = {}

        # «призраки» — равномерная оценка покупателей вне очередей
        self._ghosts: List[dict] = []

    # ----- маршрут покупателя -------------------------------------------
    def _spawn(self, now: float) -> None:
        rng = self.rng
        aid = self._next_agent_id
        self._next_agent_id += 1
        segs: List[dict] = []
        queue: List[tuple] = [(now, "cam_in", {"sensor": "Вход"},
                               ENTRANCE[0], ENTRANCE[1])]
        t = now
        cur = ENTRANCE

        def go(p, tag="walk", dwell=0.0, dwell_tag=None):
            nonlocal t, cur
            dist = math.hypot(p[0] - cur[0], p[1] - cur[1])
            if dist > 1e-6:
                segs.append({"x0": cur[0], "y0": cur[1], "x1": p[0],
                             "y1": p[1], "t0": t, "t1": t + dist / WALK_SPEED,
                             "tag": tag})
                t += dist / WALK_SPEED
            if dwell > 0:
                segs.append({"x0": p[0], "y0": p[1], "x1": p[0], "y1": p[1],
                             "t0": t, "t1": t + dwell,
                             "tag": dwell_tag or tag})
                t += dwell
            cur = p

        # обход стеллажей — по реальной планограмме магазина
        planogram = self.store.current_planogram
        picked: List[str] = []
        gondolas = rng.sample(self.store.gondolas,
                              rng.randint(1, len(self.store.gondolas)))
        for g in gondolas:
            u = rng.uniform(0.25, g.width - 0.25)
            front = (g.x + u, g.y + g.depth + 0.45)
            go(front, dwell=rng.uniform(2.5, 6.0), dwell_tag="browse")
            placements = planogram.by_gondola(g.gondola_id)
            if placements and rng.random() < 0.85:
                sku = rng.choice(placements).sku
                product = self.store.product(sku)
                picked.append(sku)
                queue.append((t - 0.5, "pick",
                              {"sku": sku, "name": product.name,
                               "gondola": g.name}, front[0], front[1]))

        # взвешивание (бакалея/развесное)
        if picked and rng.random() < 0.45:
            go(SCALES, dwell=3.0, dwell_tag="weigh")
            weigh_sku = rng.choice(picked)
            weight = round(rng.uniform(0.15, 1.8), 2)
            queue.append((t - 0.5, "scale",
                          {"name": self.store.product(weigh_sku).name,
                           "weight_kg": weight}, SCALES[0], SCALES[1]))

        # оплата: СКО или обычная касса
        register = None
        if picked:
            total = round(sum(price_for(self.store.product(s).category, s)
                              for s in picked))
            if rng.random() < 0.45:      # касса самообслуживания
                register = "СКО"
                go(SCO_GATE)
                queue.append((t, "sco_in", {}, SCO_GATE[0], SCO_GATE[1]))
                go(SCO_PAY, dwell=rng.uniform(6, 12), dwell_tag="pay")
                queue.append((t - 0.5, "pos",
                              {"register": "СКО", "total": total,
                               "items": len(picked), "sco": True},
                              SCO_PAY[0], SCO_PAY[1]))
                go(SCO_GATE)
                queue.append((t, "sco_out", {}, SCO_GATE[0], SCO_GATE[1]))
            else:
                name, px, py = POS_DESKS[rng.randrange(len(POS_DESKS))]
                register = name
                go((px, POS_QUEUE_Y), dwell=rng.uniform(3, 8),
                   dwell_tag="queue")
                go((px, py + 0.55), dwell=rng.uniform(5, 10),
                   dwell_tag="pay")
                queue.append((t - 0.5, "pos",
                              {"register": name, "total": total,
                               "items": len(picked), "sco": False},
                              px, py))

        go(EXIT)
        queue.append((t, "cam_out", {"sensor": "Выход"}, EXIT[0], EXIT[1]))
        self.agents[aid] = {"segs": segs, "queue": queue, "end": t + 0.5,
                            "cart": bool(picked), "register": register}

    # ----- события ------------------------------------------------------
    def _emit(self, t: float, etype: str, data: dict,
              x: Optional[float], y: Optional[float], source: str) -> None:
        self.events.append({"id": self._next_event_id, "t": t,
                            "type": etype, "data": data, "x": x, "y": y,
                            "source": source})
        self._next_event_id += 1
        c = self.counters
        if etype == "cam_in":
            c["visitors_today"] += 1
            c["in_store"] += 1
        elif etype == "cam_out":
            c["in_store"] = max(0, c["in_store"] - 1)
        elif etype == "pos":
            c["receipts"] += 1
            c["revenue"] += float(data.get("total", 0))
            if data.get("sco"):
                c["sco_receipts"] += 1
            self._consume_paper(t, str(data.get("register", "Касса 1")),
                                self.rng.uniform(0.6, 1.4))
        elif etype == "scale":
            c["weighings"] += 1
            self._consume_paper(t, "Весы", self.rng.uniform(0.4, 0.9))
            self._consume_bags(t, self.rng.randint(1, 2))

    def ingest(self, events: List[dict]) -> int:
        """Приём реального потока (кассы, весы, СКО, видеоаналитика)."""
        now = time.time()
        accepted = 0
        with self._lock:
            for e in events:
                etype = e.get("type")
                data = dict(e.get("data", {}))
                if etype == "queue":            # видеоаналитика очередей
                    self.reported_queues[str(data.get("register", "?"))] = \
                        max(0, int(data.get("len", 0)))
                    accepted += 1
                    continue
                if etype == "fridge":           # телеметрия холодильника
                    for f in self.fridges:
                        if f["id"] == data.get("id"):
                            f["temp"] = float(data.get("temp_c", f["temp"]))
                            f["door_open"] = bool(data.get("door_open",
                                                           f["door_open"]))
                            accepted += 1
                    continue
                if etype not in ("cam_in", "cam_out", "pick", "scale",
                                 "sco_in", "sco_out", "pos"):
                    continue
                self._emit(float(e.get("ts", now)), etype, data,
                           e.get("x"), e.get("y"), source="real")
                accepted += 1
            if accepted:
                self.last_real_ts = now
        return accepted

    # ----- расходники ---------------------------------------------------
    def _consume_paper(self, now: float, device: str, amount: float) -> None:
        if device not in self.consumables:
            return
        level = self.consumables[device] = max(
            0.0, self.consumables[device] - amount)
        if level < 10 and device not in self._replacements:
            self._replacements[device] = now + self.rng.uniform(20, 45)
            self._emit(now, "consumable",
                       {"device": device, "kind": "paper",
                        "level": round(level),
                        "msg_key": "instore.log.paper_low",
                        "msg_params": {"level": round(level)}},
                       None, None, "test")

    def _consume_bags(self, now: float, n: int) -> None:
        self.veg_bags = max(0, self.veg_bags - n)
        if self.veg_bags < 40 and self._bags_order is None:
            self._bags_order = now + self.rng.uniform(25, 60)
            self._emit(now, "consumable",
                       {"device": "Весы", "kind": "bags",
                        "level": self.veg_bags,
                        "msg_key": "instore.log.bags_low",
                        "msg_params": {"n": self.veg_bags}},
                       None, None, "test")

    def _service_consumables(self, now: float) -> None:
        for device, due in list(self._replacements.items()):
            if now >= due:
                self.consumables[device] = 100.0
                del self._replacements[device]
                self._emit(now, "consumable",
                           {"device": device, "kind": "paper", "level": 100,
                            "msg_key": "instore.log.paper_replaced",
                            "msg_params": {}},
                           None, None, "test")
        if self._bags_order is not None and now >= self._bags_order:
            self.veg_bags += 300
            self._bags_order = None
            self._emit(now, "consumable",
                       {"device": "Весы", "kind": "bags",
                        "level": self.veg_bags,
                        "msg_key": "instore.log.bags_replenished",
                        "msg_params": {"n": self.veg_bags}},
                       None, None, "test")

    # ----- холодильники -------------------------------------------------
    def _evolve_fridges(self, now: float, dt: float,
                        real_active: bool = False) -> None:
        for f in self.fridges:
            if real_active:
                # реальная телеметрия из ingest — только проверяем тревогу
                if f["temp"] >= FRIDGE_ALARM and not f["alarmed"]:
                    f["alarmed"] = True
                    self._emit(now, "fridge_alarm",
                               {"id": f["id"],
                                "temp_c": round(f["temp"], 1)},
                               f["x"] + f["w"] / 2, f["y"], "real")
                elif f["temp"] < FRIDGE_WARN:
                    f["alarmed"] = False
                continue
            if not f["door_open"] and self.rng.random() < 0.006 * dt * 10:
                f["door_open"] = True
                f["door_until"] = now + self.rng.uniform(6, 18)
            if f["door_open"] and now >= f["door_until"]:
                f["door_open"] = False
            if f["door_open"]:
                f["temp"] += 0.28 * dt
            f["compressor"] = f["temp"] > FRIDGE_SETPOINT + 0.7
            if f["compressor"]:
                f["temp"] -= 0.22 * dt
            f["temp"] += self.rng.gauss(0, 0.03)
            f["temp"] = max(1.0, min(12.0, f["temp"]))

            if f["temp"] >= FRIDGE_ALARM and not f["alarmed"]:
                f["alarmed"] = True
                self._emit(now, "fridge_alarm",
                           {"id": f["id"], "temp_c": round(f["temp"], 1)},
                           f["x"] + f["w"] / 2, f["y"], "test")
            elif f["temp"] < FRIDGE_WARN:
                f["alarmed"] = False

    # ----- ТСД (BLE/LoRa позиционирование) ------------------------------
    def _evolve_tsd(self, now: float, dt: float) -> None:
        for d in self.tsd:
            if now >= d["retarget"]:
                d["tx"] = self.rng.uniform(HALL[0] + 0.4, HALL[2] - 0.3)
                d["ty"] = self.rng.uniform(HALL[1] + 0.4, HALL[3] - 0.3)
                d["retarget"] = now + self.rng.uniform(8, 22)
            dx, dy = d["tx"] - d["x"], d["ty"] - d["y"]
            dist = math.hypot(dx, dy)
            if dist > 0.05:
                step = min(dist, 0.6 * dt)
                d["x"] += dx / dist * step
                d["y"] += dy / dist * step
            d["battery"] = max(0.0, d["battery"] - 0.01 * dt)

    def _tsd_out(self, lang: str = DEFAULT_LANG) -> List[dict]:
        out = []
        for d in self.tsd:
            ble = d["x"] < BLE_ZONE_X          # зона покрытия BLE-маяков
            acc = (self.rng.uniform(0.5, 1.0) if ble
                   else self.rng.uniform(1.8, 3.5))
            out.append({"id": _display_label(lang, d["id"]),
                        "x": round(d["x"] + self.rng.gauss(0, acc / 3), 2),
                        "y": round(d["y"] + self.rng.gauss(0, acc / 3), 2),
                        "acc": round(acc, 1),
                        "src": "BLE" if ble else "LoRa",
                        "battery": round(d["battery"])})
        return out

    # ----- очереди ------------------------------------------------------
    def _queues(self, now: float, real_active: bool,
               lang: str = DEFAULT_LANG) -> List[dict]:
        # "name" остаётся каноническим (русским) — по нему клиент сверяет
        # очередь с кассой на схеме (`layout.pos[].name`); "label" — то,
        # что показывается покупателю, переводится отдельно, чтобы
        # перевод не ломал сопоставление ключей на клиенте
        names = [n for n, _, _ in POS_DESKS] + ["СКО"]
        if real_active and self.reported_queues:
            counts = {n: self.reported_queues.get(n, 0) for n in names}
        else:
            counts = {n: 0 for n in names}
            for agent in self.agents.values():
                pos = self._agent_pos(agent, now)
                if not pos or agent["register"] is None:
                    continue
                if pos[2] in ("queue", "pay"):
                    counts[agent["register"]] += 1
        return [{"name": n, "label": _display_label(lang, n),
                 "len": counts[n]} for n in names]

    # ----- оценка покупателей по датчикам входа/выхода ------------------
    def _evolve_ghosts(self, dt: float, target: int) -> None:
        rng = self.rng
        blocked = ([(g.x - 0.3, g.y - 0.3, g.width + 0.6, g.depth + 0.6)
                    for g in self.store.gondolas]
                   + [SCO_RECT]
                   + [(x - 0.2, y - 0.2, w + 0.4, d + 0.4)
                      for _, x, y, w, d in FRIDGES])

        def free(x, y):
            return not any(bx <= x <= bx + bw and by <= y <= by + bd
                           for bx, by, bw, bd in blocked)

        while len(self._ghosts) < target:      # равномерно по свободному полу
            for _ in range(40):
                x = rng.uniform(HALL[0] + 0.3, HALL[2] - 0.3)
                y = rng.uniform(HALL[1] + 0.3, HALL[3] - 0.3)
                if free(x, y):
                    self._ghosts.append(
                        {"x": x, "y": y, "a": rng.uniform(0, 6.28)})
                    break
            else:
                break
        del self._ghosts[max(0, target):]
        for gh in self._ghosts:                # медленный дрейф
            gh["a"] += rng.gauss(0, 0.5) * dt
            nx = gh["x"] + math.cos(gh["a"]) * 0.25 * dt
            ny = gh["y"] + math.sin(gh["a"]) * 0.25 * dt
            if HALL[0] + 0.3 < nx < HALL[2] - 0.3 and free(nx, gh["y"]):
                gh["x"] = nx
            if HALL[1] + 0.3 < ny < HALL[3] - 0.3 and free(gh["x"], ny):
                gh["y"] = ny

    # ----- состояние для клиента ---------------------------------------
    @staticmethod
    def _agent_pos(agent: dict, now: float):
        segs = agent["segs"]
        if not segs:
            return None
        if now <= segs[0]["t0"]:
            s = segs[0]
            return s["x0"], s["y0"], "walk"
        for s in segs:
            if s["t0"] <= now <= s["t1"]:
                k = ((now - s["t0"]) / (s["t1"] - s["t0"])
                     if s["t1"] > s["t0"] else 1.0)
                return (s["x0"] + (s["x1"] - s["x0"]) * k,
                        s["y0"] + (s["y1"] - s["y0"]) * k, s["tag"])
        s = segs[-1]
        return s["x1"], s["y1"], "walk"

    def _layout(self, lang: str = DEFAULT_LANG) -> dict:
        gondolas = []
        perishable_zones = []
        for g in self.store.gondolas:
            placements = self.store.current_planogram.by_gondola(
                g.gondola_id)
            skus = [p.sku for p in placements]
            fills = [self.store.sales[s].fill_ratio for s in skus
                     if s in self.store.sales]
            perishable = any(
                self.store.product(s).category in PERISHABLE_CATEGORIES
                for s in skus)
            gondolas.append({"x": g.x, "y": g.y, "w": g.width,
                             "d": g.depth, "name": g.name,
                             "perishable": perishable,
                             "fill": round(sum(fills) / len(fills), 2)
                             if fills else 1.0})
            if perishable:
                perishable_zones.append(
                    {"x": g.x - 0.25, "y": g.y - 0.25, "w": g.width + 0.5,
                     "d": g.depth + 0.95,
                     "label": t(lang, "instore.perishable.zone")})
        fx0 = min(x for _, x, _, _, _ in FRIDGES) - 0.25
        fx1 = max(x + w for _, x, _, w, _ in FRIDGES) + 0.25
        perishable_zones.append({"x": fx0, "y": FRIDGES[0][2] - 0.55,
                                 "w": fx1 - fx0, "d": FRIDGES[0][4] + 0.85,
                                 "label": t(lang,
                                           "instore.perishable.zone_cold")})
        return {"gondolas": gondolas, "entrance": ENTRANCE, "exit": EXIT,
                "scales": SCALES, "sco": SCO_RECT, "sco_gate": SCO_GATE,
                # "name" — канонический (русский) ключ для сопоставления
                # с `queues[].name`, "label" — переведённая подпись на схеме
                "pos": [{"name": n, "label": _display_label(lang, n),
                         "x": x, "y": y} for n, x, y in POS_DESKS],
                "perishable_zones": perishable_zones}

    def state(self, after_id: int = 0, lang: str = DEFAULT_LANG) -> dict:
        now = time.time()
        with self._lock:
            dt = min(5.0, now - self._last_evolve)
            self._last_evolve = now
            real_active = now - self.last_real_ts < REAL_FEED_TIMEOUT
            if (not real_active and now >= self._next_spawn
                    and len(self.agents) < 14):
                self._spawn(now)
                self._next_spawn = now + self.rng.uniform(2.5, 7.0)

            finished = []
            for aid, agent in self.agents.items():
                q = agent["queue"]
                while q and q[0][0] <= now:
                    # переменная не 't' — это имя занято функцией перевода
                    # i18n.t(), импортированной в модуль
                    ev_t, etype, data, x, y = q.pop(0)
                    self._emit(ev_t, etype, data, x, y, source="test")
                if now > agent["end"]:
                    finished.append(aid)
            for aid in finished:
                del self.agents[aid]

            self._evolve_fridges(now, dt, real_active)
            self._evolve_tsd(now, dt)
            self._service_consumables(now)

            queues = self._queues(now, real_active, lang)
            queue_total = sum(q["len"] for q in queues)
            # покупатели по датчикам минус очереди → равномерно по залу
            est_free = max(0, self.counters["in_store"] - queue_total)
            self._evolve_ghosts(dt, est_free)

            agents_out = []
            for aid, agent in self.agents.items():
                pos = self._agent_pos(agent, now)
                if pos:
                    agents_out.append({"id": aid, "x": round(pos[0], 2),
                                       "y": round(pos[1], 2),
                                       "state": pos[2],
                                       "cart": agent["cart"]})

            raw_events = [e for e in self.events if e["id"] > after_id][-40:]
            # текст события и переводимые поля данных (имя кассы/устройства)
            # собираются здесь, на языке запроса — само событие хранит
            # только канонический (русский) идентификатор, см. `_emit`
            # и `_display_label`
            new_events = [self._translate_event(lang, e) for e in raw_events]
            counters = dict(self.counters)
            counters["revenue"] = round(counters["revenue"])
            fridges_out = [{"id": _display_label(lang, f["id"]),
                            "x": f["x"], "y": f["y"],
                            "w": f["w"], "d": f["d"],
                            "temp": round(f["temp"], 1),
                            "door_open": f["door_open"],
                            "compressor": f["compressor"],
                            "state": ("alarm" if f["temp"] >= FRIDGE_ALARM
                                      else "warn" if f["temp"] >= FRIDGE_WARN
                                      else "ok")}
                           for f in self.fridges]
            consumables = {_display_label(lang, k): round(v)
                          for k, v in self.consumables.items()}
        return {"mode": "real" if real_active else "test",
                "agents": agents_out, "events": new_events,
                "counters": counters, "layout": self._layout(lang),
                "queues": queues,
                "estimate": {"in_store": self.counters["in_store"],
                             "in_queues": queue_total,
                             "on_floor": est_free,
                             "ghosts": [{"x": round(g["x"], 2),
                                         "y": round(g["y"], 2)}
                                        for g in self._ghosts]},
                "fridges": fridges_out,
                "tsd": self._tsd_out(lang),
                "consumables": {"paper": consumables,
                                "veg_bags": self.veg_bags}}

    @staticmethod
    def _translate_event(lang: str, e: dict) -> dict:
        """Копия события с переведёнными полями `data` — сам `e` в очереди
        `self.events` не меняется (его могут отдать другому запросу с
        другим языком, см. комментарий в `state()`)."""
        etype, data = e["type"], e["data"]
        if etype == "pos" and "register" in data:
            data = {**data, "register": _display_label(lang,
                                                        data["register"])}
        elif etype == "fridge_alarm" and "id" in data:
            data = {**data, "id": _display_label(lang, data["id"])}
        elif etype == "consumable" and "msg_key" in data:
            data = {**data, "device": _display_label(lang, data["device"]),
                    "text": t(lang, data["msg_key"], **data["msg_params"])}
        return {**e, "data": data}


class InstoreHub:
    """Реестр симуляций залов: по одной на магазин, создаются лениво."""

    def __init__(self):
        self._sims: Dict[str, InstoreSim] = {}
        self._lock = threading.Lock()

    def get(self, store_id: str, store: Store) -> InstoreSim:
        with self._lock:
            if store_id not in self._sims:
                self._sims[store_id] = InstoreSim(
                    store, seed=abs(hash(store_id)) % 10000 + 1)
            return self._sims[store_id]
