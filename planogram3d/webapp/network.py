"""Эмуляция работающей сети магазинов.

Каждый магазин сети — полноценный :class:`planogram3d.core.Store`
(со своей планограммой и продажами), привязанный к реальным координатам
в городе. Фоновый «тикер» ускоренно проигрывает торговый день: списывает
остатки по скорости продаж, начисляет выручку, устраивает out-of-stock
и пополнения, ведёт ленту событий — в духе игровых симуляторов магазинов.
"""

import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from ..core import Store, check_compliance
from ..sample_data import build_demo_store
from .i18n import DEFAULT_LANG, render_event, t

#: 1 секунда реального времени = TIME_SCALE секунд «магазинного» времени.
TIME_SCALE = 600  # 1 с = 10 мин: торговый день пролетает за ~2.5 минуты

#: Базовые цены по категориям для начисления выручки, лей
CATEGORY_PRICES = {
    "Бакалея": 240.0,
    "Напитки": 110.0,
    "Молочные продукты": 95.0,
    "Снеки": 130.0,
}

#: Магазины сети: (id, название, широта, долгота, seed демо-данных)
NETWORK_LAYOUT: List[Tuple[str, str, float, float, int]] = [
    ("st17", "«Гурман» №17 · Штефан чел Маре", 47.0245, 28.8320, 42),
    ("st03", "«Гурман» №3 · Измаил", 47.0170, 28.8380, 3),
    ("st08", "«Гурман» №8 · Рышкановка", 47.0450, 28.8600, 8),
    ("st21", "«Гурман» №21 · Ботаника", 46.9950, 28.8600, 21),
    ("st12", "«Гурман» №12 · Чеканы", 47.0400, 28.8850, 12),
    ("st05", "«Гурман» №5 · Буюканы", 47.0400, 28.8050, 5),
]


def price_for(category: str, sku: str) -> float:
    base = CATEGORY_PRICES.get(category, 150.0)
    return round(base * (0.8 + (hash(sku) % 41) / 100.0), 2)


def _ev(now: float, store_label: str, icon: str, key: str, count=None,
        **params) -> dict:
    """Запись ленты событий: ключ+параметры вместо готовой строки — язык
    выбирается при отдаче (см. `i18n.render_event`), а не в момент записи.

    ``store_label`` — источник события для колонки «магазин» в ленте
    (см. `state()`); имя параметра отличается от возможного params["store"]
    (у log.dc_shipment есть свой параметр {store} — магазин-получатель),
    чтобы вызовы с обоими не сталкивались по имени аргумента.
    """
    return {"t": now, "store": store_label, "icon": icon, "key": key,
           "params": params, "count": count}


class DistributionCenter:
    """Логистический центр (РЦ) — буфер между поставщиками и магазинами.

    Магазины при out-of-stock заказывают товар не напрямую у поставщика,
    а в РЦ: отгрузка едет «грузовиком» (видна на карте города), склад РЦ
    списывается, а при падении ниже точки перезаказа РЦ сам заказывает
    партию у поставщика (более долгое плечо). Если товара на РЦ нет,
    магазин получает прямую поставку от поставщика с большим сроком.
    """

    LOCATION = (46.9900, 28.8000)   # промзона на юго-западе Кишинёва
    REORDER_POINT = 45
    REORDER_QTY = 140
    TRUCK_SPEED = 45.0              # м/с в эмуляции (ускоренное время)

    def __init__(self, skus, rng: random.Random):
        self.name = "РЦ «Гурман» Кишинёв"
        self.lat, self.lon = self.LOCATION
        self.rng = rng
        self.stock: Dict[str, int] = {sku: rng.randint(70, 160)
                                      for sku in skus}
        self.outbound: List[dict] = []   # отгрузки в магазины (грузовики)
        self.inbound: List[dict] = []    # поставки от поставщиков в РЦ
        #: час симуляционных суток — ставится сетью (для модели трафика)
        self.hour_fn = None

    def _sim_hour(self, now: float) -> int:
        return self.hour_fn(now) if self.hour_fn is not None else 12

    @staticmethod
    def _traffic(hour: int) -> float:
        """Замедление трафика по часу суток (часы пик медленнее)."""
        if hour in (8, 9, 17, 18):
            return 0.72
        if hour in (10, 16, 19):
            return 0.85
        return 1.0

    def order(self, store_title: str, store_id: str, lat: float, lon: float,
              sku: str, sku_name: str, qty: int, now: float,
              events: Deque) -> Optional[Tuple[float, int]]:
        """Заказ магазина. Возвращает (eta, отгружено) или None (нет товара)."""
        available = self.stock.get(sku, 0)
        shipped = min(qty, available)
        self._maybe_reorder(sku, sku_name, now, events)
        if shipped <= 0:
            events.appendleft(_ev(now, self.name, "🏭", "log.dc_no_stock",
                                  name=sku_name, store=store_title))
            return None
        self.stock[sku] = available - shipped
        depart = now + 3.0
        # маршрут грузовика строго по дорогам города
        from .roadnet import get_roadnet
        path, road_m = get_roadnet().route(self.lon, self.lat, lon, lat)
        # фактическая скорость рейса: трафик часа + случайность водителя;
        # план (и наивное eta) считается по паспортной скорости, а
        # ИИ-табло учится на фактических рейсах и прогнозирует точнее
        hour = self._sim_hour(depart)
        speed = (self.TRUCK_SPEED * self._traffic(hour)
                 * self.rng.uniform(0.85, 1.12))
        eta = depart + max(20.0, road_m / speed)
        self.outbound.append({"store_id": store_id, "sku": sku,
                              "sku_name": sku_name, "qty": shipped,
                              "depart": depart, "eta": eta,
                              "road_m": road_m,
                              "plan_eta": depart + max(
                                  20.0, road_m / self.TRUCK_SPEED),
                              "to": [lat, lon],
                              "path": [[round(p[0], 5), round(p[1], 5)]
                                       for p in path]})
        events.appendleft(_ev(now, self.name, "🚚", "log.dc_shipment",
                              name=sku_name, store=store_title, qty=shipped))
        return eta, shipped

    def _maybe_reorder(self, sku: str, sku_name: str, now: float,
                       events: Deque) -> None:
        if (self.stock.get(sku, 0) < self.REORDER_POINT
                and not any(o["sku"] == sku for o in self.inbound)):
            self.inbound.append({"sku": sku, "sku_name": sku_name,
                                 "qty": self.REORDER_QTY,
                                 "eta": now + self.rng.uniform(70, 140)})
            events.appendleft(_ev(now, self.name, "📦", "log.dc_reorder",
                                  name=sku_name, qty=self.REORDER_QTY))

    def tick(self, now: float, events: Deque) -> None:
        for o in [o for o in self.inbound if now >= o["eta"]]:
            self.inbound.remove(o)
            self.stock[o["sku"]] = self.stock.get(o["sku"], 0) + o["qty"]
            events.appendleft(_ev(now, self.name, "🏭",
                                  "log.dc_supply_arrived",
                                  name=o["sku_name"], qty=o["qty"]))
        # завершённые рейсы — телеметрия в ИИ-модель прогноза прибытия
        from .eta_ai import get_predictor
        for o in self.outbound:
            if now >= o["eta"] and not o.get("_observed"):
                o["_observed"] = True
                get_predictor().observe(
                    "truck", o.get("road_m", 0.0),
                    o["eta"] - o["depart"],
                    hour=self._sim_hour(o["depart"]))
        self.outbound = [o for o in self.outbound if now <= o["eta"] + 3]

    def snapshot(self, now: float) -> dict:
        return {
            "name": self.name, "lat": self.lat, "lon": self.lon,
            "stock_total": sum(self.stock.values()),
            "sku_low": sum(1 for v in self.stock.values()
                           if v < self.REORDER_POINT),
            "outbound": [{"store_id": o["store_id"], "sku": o["sku_name"],
                          "qty": o["qty"], "depart": o["depart"],
                          "eta": o["eta"], "to": o["to"],
                          "path": o.get("path")}
                         for o in self.outbound],
            "inbound": [{"sku": o["sku_name"], "qty": o["qty"],
                         "eta_sec": max(0, round(o["eta"] - now))}
                        for o in self.inbound],
        }


@dataclass
class EmulatedStore:
    """Один магазин сети с «живым» торговым состоянием."""
    store_id: str
    title: str
    lat: float
    lon: float
    store: Store
    rng: random.Random
    revenue: float = 0.0
    transactions: int = 0
    visitors: int = 15
    restock_at: Dict[str, dict] = field(default_factory=dict)
    last_tick_revenue: float = 0.0
    critical_violations: int = 0
    dc: Optional["DistributionCenter"] = None

    def _order_restock(self, sku: str, now: float, events: Deque) -> None:
        """Заказ пополнения: через РЦ (если подключён) или напрямую."""
        product = self.store.product(sku)
        capacity = self.store.sales[sku].capacity
        if self.dc is not None:
            shipped = self.dc.order(self.title, self.store_id,
                                    self.lat, self.lon, sku, product.name,
                                    capacity, now, events)
            if shipped is not None:
                eta, qty = shipped
                self.restock_at[sku] = {"due": eta, "qty": qty}
                return
            # на РЦ пусто — прямая поставка от поставщика, дольше
            self.restock_at[sku] = {"due": now + self.rng.uniform(90, 150),
                                    "qty": capacity}
            return
        self.restock_at[sku] = {"due": now + self.rng.uniform(25, 80),
                                "qty": capacity}
        events.appendleft(_ev(now, self.title, "⛔", "log.shelf_empty",
                              name=product.name))

    def tick(self, dt: float, now: float, events: Deque) -> None:
        """Один шаг эмуляции: продажи, OOS, пополнения, посетители."""
        sold_value = 0.0
        day_fraction = dt * TIME_SCALE / 86400.0
        for sku, info in self.store.sales.items():
            product = self.store.product(sku)
            # пуассоновское число продаж за шаг
            lam = info.sales_rate * day_fraction
            n = self._poisson(lam)
            if n <= 0 or info.stock <= 0:
                # магазин с пустой полкой теряет продажи
                if info.stock <= 0 and sku not in self.restock_at:
                    self._order_restock(sku, now, events)
                continue
            n = min(n, info.stock)
            info.stock -= n
            info.sold_today += n
            self.transactions += n
            sold_value += n * price_for(product.category, sku)
            if info.stock == 0:
                events.appendleft(_ev(now, self.title, "⛔",
                                      "log.out_of_stock", name=product.name))
                self._order_restock(sku, now, events)

        # приезд пополнений
        for sku, order in list(self.restock_at.items()):
            if now >= order["due"]:
                info = self.store.sales[sku]
                info.stock = min(info.capacity, info.stock + order["qty"])
                del self.restock_at[sku]
                events.appendleft(_ev(
                    now, self.title, "📦", "log.shelf_restocked",
                    name=self.store.product(sku).name, qty=order["qty"]))

        self.revenue += sold_value
        self.last_tick_revenue = sold_value
        self.visitors = max(3, min(70, self.visitors
                                   + self.rng.randint(-4, 4)))

    def _poisson(self, lam: float) -> int:
        if lam <= 0:
            return 0
        # метод Кнута — λ здесь всегда мал
        L, k, p = pow(2.718281828, -lam), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= L:
                return k
            k += 1

    # ----- метрики для API ------------------------------------------------
    @property
    def fill_avg(self) -> float:
        infos = self.store.sales.values()
        return sum(i.fill_ratio for i in infos) / max(1, len(infos))

    @property
    def oos_count(self) -> int:
        return sum(1 for i in self.store.sales.values() if i.stock == 0)

    @property
    def level(self) -> int:
        """«Уровень магазина» 1–5 звёзд по накопленной выручке."""
        for stars, threshold in ((5, 60000), (4, 30000), (3, 12000),
                                 (2, 4000)):
            if self.revenue >= threshold:
                return stars
        return 1

    @property
    def status(self) -> str:
        if self.oos_count >= 2:
            return "critical"
        if self.oos_count == 1 or self.fill_avg < 0.45:
            return "warning"
        return "ok"

    def snapshot(self) -> dict:
        return {
            "id": self.store_id,
            "name": self.title,
            "lat": self.lat,
            "lon": self.lon,
            "revenue": round(self.revenue),
            "revenue_delta": round(self.last_tick_revenue),
            "transactions": self.transactions,
            "visitors": self.visitors,
            "fill_avg": round(self.fill_avg, 2),
            "oos": self.oos_count,
            "oos_skus": [self.store.product(s).name
                         for s, i in self.store.sales.items()
                         if i.stock == 0],
            "violations_critical": self.critical_violations,
            "level": self.level,
            "status": self.status,
        }


class StoreNetwork:
    """Сеть магазинов с фоновым тикером эмуляции."""

    def __init__(self, tick_seconds: float = 2.0,
                 dc_enabled: Optional[bool] = None):
        self.tick_seconds = tick_seconds
        self.events: Deque = deque(maxlen=40)
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # логистический центр опционален: PLANOGRAM_DC=0 отключает его,
        # тогда магазины снабжаются напрямую от поставщиков
        if dc_enabled is None:
            dc_enabled = os.environ.get("PLANOGRAM_DC", "1") != "0"
        self.dc: Optional[DistributionCenter] = None

        self.stores: Dict[str, EmulatedStore] = {}
        for store_id, title, lat, lon, seed in NETWORK_LAYOUT:
            store = build_demo_store(seed=seed)
            store.store_id = store_id
            store.name = title
            emu = EmulatedStore(store_id, title, lat, lon, store,
                                random.Random(seed * 977))
            emu.critical_violations = sum(
                1 for v in check_compliance(store)
                if v.severity == "critical")
            self.stores[store_id] = emu

        if dc_enabled:
            first = next(iter(self.stores.values())).store
            self.dc = DistributionCenter(list(first.products),
                                         random.Random(20260815))
            self.dc.hour_fn = self.sim_hour
            for emu in self.stores.values():
                emu.dc = self.dc

    def sim_hour(self, now: Optional[float] = None) -> int:
        """Час симуляционных суток (та же формула, что sim_clock)."""
        if now is None:
            now = time.time()
        sim_seconds = (now - self.started_at) * TIME_SCALE
        return 8 + int(sim_seconds // 3600) % 14

    # ----- жизненный цикл -------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        last = time.time()
        while not self._stop.is_set():
            time.sleep(self.tick_seconds)
            now = time.time()
            with self._lock:
                for emu in self.stores.values():
                    emu.tick(now - last, now, self.events)
                if self.dc is not None:
                    self.dc.tick(now, self.events)
            last = now

    # ----- API ------------------------------------------------------------
    def state(self, lang: str = DEFAULT_LANG) -> dict:
        now = time.time()
        with self._lock:
            stores = [e.snapshot() for e in self.stores.values()]
            # текст ленты собирается здесь, на языке запроса — само событие
            # хранит только ключ+параметры (см. `_ev`/`render_event`)
            events = [{"t": round(ev["t"] - self.started_at),
                      "store": ev["store"], "text": render_event(lang, ev)}
                     for ev in list(self.events)[:20]]
            dc = self.dc.snapshot(now) if self.dc is not None else None
        sim_seconds = (now - self.started_at) * TIME_SCALE
        return {
            "now": now,
            "dc": dc,
            "sim_clock": "%02d:%02d" % (8 + int(sim_seconds // 3600) % 14,
                                        int(sim_seconds // 60) % 60),
            "time_scale": TIME_SCALE,
            "totals": {
                "revenue": round(sum(e.revenue for e in
                                     self.stores.values())),
                "transactions": sum(e.transactions
                                    for e in self.stores.values()),
                "stores": len(self.stores),
                "critical": sum(1 for e in self.stores.values()
                                if e.status == "critical"),
                "oos": sum(e.oos_count for e in self.stores.values()),
            },
            "stores": stores,
            "events": events,
        }

    def store(self, store_id: str) -> Store:
        return self.stores[store_id].store

    def arrival_board(self, store_id: str, lang: str = DEFAULT_LANG) -> dict:
        """Онлайн-табло пункта доставки (магазина): машины поставщиков.

        Для каждой машины РЦ в пути — ИИ-прогноз прибытия (остаток
        дороги / обученная скорость с учётом часа) с ±σ; прямые
        поставки поставщиков (без машины на карте) — по плану.
        """
        from .eta_ai import get_predictor
        now = time.time()
        emu = self.stores[store_id]           # KeyError → 404 на сервере
        hour = self.sim_hour(now)
        predictor = get_predictor()
        rows = []
        truck_skus = set()
        with self._lock:
            if self.dc is not None:
                for o in self.dc.outbound:
                    if o["store_id"] != store_id:
                        continue
                    truck_skus.add(o["sku"])
                    total = max(1.0, o["eta"] - o["depart"])
                    progress = min(1.0, max(0.0, (now - o["depart"]) / total))
                    remaining_m = o.get("road_m", 0.0) * (1.0 - progress)
                    eta_s, sigma_s, n_obs = predictor.predict(
                        "truck", remaining_m, hour=hour)
                    if now < o["depart"]:              # ещё не выехал
                        eta_s += o["depart"] - now
                    rows.append({
                        "type": "truck",
                        "icon": "🚚",
                        "label": t(lang, "eta.dc_shipment",
                                  name=o["sku_name"], qty=o["qty"]),
                        "eta_sec": round(eta_s),
                        "sigma_sec": round(max(3.0, sigma_s)),
                        "eta_ts": now + eta_s,
                        "plan_ts": o.get("plan_eta", o["eta"]),
                        "progress": round(progress, 2),
                        "source": (t(lang, "ai.forecast_trained_trips",
                                     count=n_obs, n=n_obs,
                                     trips_word=t(
                                         lang,
                                         "ai.forecast_trained_trips."
                                         "trips_word", count=n_obs))
                                  if n_obs
                                  else t(lang, "ai.forecast_prior")),
                    })
            for sku, order in emu.restock_at.items():
                if sku in truck_skus:
                    continue                            # уже едет грузовиком
                name = emu.store.product(sku).name
                rows.append({
                    "type": "supplier",
                    "icon": "📦",
                    "label": t(lang, "eta.supplier_direct",
                              name=name, qty=order["qty"]),
                    "eta_sec": max(0, round(order["due"] - now)),
                    "sigma_sec": None,
                    "eta_ts": order["due"],
                    "plan_ts": order["due"],
                    "progress": None,
                    "source": t(lang, "eta.supply_plan"),
                })
        rows.sort(key=lambda r: r["eta_ts"])
        return {"now": now, "point": emu.title, "store_id": store_id,
                "sim_hour": hour, "rows": rows,
                "model": predictor.summary()}
