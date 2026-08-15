"""Игровая симуляция торгового зала: поток событий касс, весов, СКО, CCTV.

Для каждого магазина создаётся :class:`InstoreSim` — «живой» торговый зал
в духе игровых симуляторов магазинов:

* покупатели-агенты входят в зал (событие видеонаблюдения), ходят к
  реальным стеллажам планограммы, берут товар, взвешивают на весах,
  оплачивают на обычной кассе или в зоне касс самообслуживания (СКО)
  и выходят;
* каждый шаг порождает событие того же вида, что шлют реальные системы:
  ``cam_in``/``cam_out`` (видеоаналитика входа/выхода), ``pick`` (снятие
  с полки), ``scale`` (взвешивание), ``sco_in``/``sco_out`` (проход через
  ворота зоны СКО), ``pos`` (чек кассы/СКО).

Источники потока:

* **тестовый** — встроенный эмулятор (по умолчанию);
* **реальный** — те же события принимаются по
  ``POST /api/instore/<store_id>/ingest`` от интеграций с кассовым ПО и
  видеоаналитикой; пока реальный поток активен (события приходили в
  последние 60 с), эмулятор перестаёт порождать новых покупателей.

Схема события: ``{"type": ..., "data": {...}, "x": м, "y": м}`` —
координаты в метрах в системе зала (опциональны, нужны для эффектов).
"""

import math
import random
import threading
import time
from collections import deque
from typing import Dict, List, Optional

from ..core import Store
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
        self.counters = {"visitors_today": 0, "in_store": 0, "receipts": 0,
                         "revenue": 0.0, "sco_receipts": 0, "weighings": 0}

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
        if picked:
            total = round(sum(price_for(self.store.product(s).category, s)
                              for s in picked))
            if rng.random() < 0.45:      # касса самообслуживания
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
                            "cart": bool(picked)}

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
        elif etype == "scale":
            c["weighings"] += 1

    def ingest(self, events: List[dict]) -> int:
        """Приём реального потока (кассовое ПО, видеоаналитика, СКО)."""
        now = time.time()
        accepted = 0
        with self._lock:
            for e in events:
                etype = e.get("type")
                if etype not in ("cam_in", "cam_out", "pick", "scale",
                                 "sco_in", "sco_out", "pos"):
                    continue
                self._emit(float(e.get("ts", now)), etype,
                           dict(e.get("data", {})),
                           e.get("x"), e.get("y"), source="real")
                accepted += 1
            if accepted:
                self.last_real_ts = now
        return accepted

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

    def _layout(self) -> dict:
        gondolas = []
        for g in self.store.gondolas:
            skus = [p.sku for p in
                    self.store.current_planogram.by_gondola(g.gondola_id)]
            fills = [self.store.sales[s].fill_ratio for s in skus
                     if s in self.store.sales]
            gondolas.append({"x": g.x, "y": g.y, "w": g.width,
                             "d": g.depth, "name": g.name,
                             "fill": round(sum(fills) / len(fills), 2)
                             if fills else 1.0})
        return {"gondolas": gondolas, "entrance": ENTRANCE, "exit": EXIT,
                "scales": SCALES, "sco": SCO_RECT, "sco_gate": SCO_GATE,
                "pos": [{"name": n, "x": x, "y": y}
                        for n, x, y in POS_DESKS]}

    def state(self, after_id: int = 0) -> dict:
        now = time.time()
        with self._lock:
            real_active = now - self.last_real_ts < REAL_FEED_TIMEOUT
            if (not real_active and now >= self._next_spawn
                    and len(self.agents) < 14):
                self._spawn(now)
                self._next_spawn = now + self.rng.uniform(2.5, 7.0)

            finished = []
            for aid, agent in self.agents.items():
                q = agent["queue"]
                while q and q[0][0] <= now:
                    t, etype, data, x, y = q.pop(0)
                    self._emit(t, etype, data, x, y, source="test")
                if now > agent["end"]:
                    finished.append(aid)
            for aid in finished:
                del self.agents[aid]

            agents_out = []
            for aid, agent in self.agents.items():
                pos = self._agent_pos(agent, now)
                if pos:
                    agents_out.append({"id": aid, "x": round(pos[0], 2),
                                       "y": round(pos[1], 2),
                                       "state": pos[2],
                                       "cart": agent["cart"]})

            new_events = [e for e in self.events if e["id"] > after_id][-40:]
            counters = dict(self.counters)
            counters["revenue"] = round(counters["revenue"])
        return {"mode": "real" if real_active else "test",
                "agents": agents_out, "events": new_events,
                "counters": counters, "layout": self._layout()}


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
