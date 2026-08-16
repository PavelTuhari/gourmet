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

#: 1 секунда реального времени = TIME_SCALE секунд «магазинного» времени.
TIME_SCALE = 600  # 1 с = 10 мин: торговый день пролетает за ~2.5 минуты

#: Базовые цены по категориям для начисления выручки, руб.
CATEGORY_PRICES = {
    "Бакалея": 240.0,
    "Напитки": 110.0,
    "Молочные продукты": 95.0,
    "Снеки": 130.0,
}

#: Магазины сети: (id, название, широта, долгота, seed демо-данных)
NETWORK_LAYOUT: List[Tuple[str, str, float, float, int]] = [
    ("st17", "«Гурман» №17 · Трёхсвятская", 56.8570, 35.9045, 42),
    ("st03", "«Гурман» №3 · пл. Ленина", 56.8594, 35.9075, 3),
    ("st08", "«Гурман» №8 · Набережная", 56.8618, 35.9120, 8),
    ("st21", "«Гурман» №21 · Заволжье", 56.8655, 35.9030, 21),
    ("st12", "«Гурман» №12 · Тверской пр-т", 56.8535, 35.9100, 12),
    ("st05", "«Гурман» №5 · Пролетарка", 56.8555, 35.8880, 5),
]


def price_for(category: str, sku: str) -> float:
    base = CATEGORY_PRICES.get(category, 150.0)
    return round(base * (0.8 + (hash(sku) % 41) / 100.0), 2)


class DistributionCenter:
    """Логистический центр (РЦ) — буфер между поставщиками и магазинами.

    Магазины при out-of-stock заказывают товар не напрямую у поставщика,
    а в РЦ: отгрузка едет «грузовиком» (видна на карте города), склад РЦ
    списывается, а при падении ниже точки перезаказа РЦ сам заказывает
    партию у поставщика (более долгое плечо). Если товара на РЦ нет,
    магазин получает прямую поставку от поставщика с большим сроком.
    """

    LOCATION = (56.8478, 35.8842)   # промзона на юго-западе Твери
    REORDER_POINT = 45
    REORDER_QTY = 140
    TRUCK_SPEED = 45.0              # м/с в эмуляции (ускоренное время)

    def __init__(self, skus, rng: random.Random):
        self.name = "РЦ «Гурман» Тверь"
        self.lat, self.lon = self.LOCATION
        self.rng = rng
        self.stock: Dict[str, int] = {sku: rng.randint(70, 160)
                                      for sku in skus}
        self.outbound: List[dict] = []   # отгрузки в магазины (грузовики)
        self.inbound: List[dict] = []    # поставки от поставщиков в РЦ

    def order(self, store_title: str, store_id: str, lat: float, lon: float,
              sku: str, sku_name: str, qty: int, now: float,
              events: Deque) -> Optional[Tuple[float, int]]:
        """Заказ магазина. Возвращает (eta, отгружено) или None (нет товара)."""
        available = self.stock.get(sku, 0)
        shipped = min(qty, available)
        self._maybe_reorder(sku, sku_name, now, events)
        if shipped <= 0:
            events.appendleft((now, self.name,
                               f"🏭 Нет остатка «{sku_name}» — {store_title} "
                               f"получит прямую поставку от поставщика"))
            return None
        self.stock[sku] = available - shipped
        depart = now + 3.0
        # маршрут грузовика строго по дорогам города
        from .roadnet import get_roadnet
        path, road_m = get_roadnet().route(self.lon, self.lat, lon, lat)
        eta = depart + max(20.0, road_m / self.TRUCK_SPEED)
        self.outbound.append({"store_id": store_id, "sku": sku,
                              "sku_name": sku_name, "qty": shipped,
                              "depart": depart, "eta": eta,
                              "to": [lat, lon],
                              "path": [[round(p[0], 5), round(p[1], 5)]
                                       for p in path]})
        events.appendleft((now, self.name,
                           f"🚚 Отгрузка в {store_title}: {sku_name} "
                           f"× {shipped}"))
        return eta, shipped

    def _maybe_reorder(self, sku: str, sku_name: str, now: float,
                       events: Deque) -> None:
        if (self.stock.get(sku, 0) < self.REORDER_POINT
                and not any(o["sku"] == sku for o in self.inbound)):
            self.inbound.append({"sku": sku, "sku_name": sku_name,
                                 "qty": self.REORDER_QTY,
                                 "eta": now + self.rng.uniform(70, 140)})
            events.appendleft((now, self.name,
                               f"📦 Заказ поставщику: {sku_name} "
                               f"× {self.REORDER_QTY}"))

    def tick(self, now: float, events: Deque) -> None:
        for o in [o for o in self.inbound if now >= o["eta"]]:
            self.inbound.remove(o)
            self.stock[o["sku"]] = self.stock.get(o["sku"], 0) + o["qty"]
            events.appendleft((now, self.name,
                               f"🏭 Приход от поставщика: {o['sku_name']} "
                               f"× {o['qty']}"))
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
        events.appendleft((now, self.title,
                           f"⛔ {product.name}: полка пуста, заказано "
                           f"пополнение"))

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
                events.appendleft((now, self.title,
                                   f"⛔ {product.name}: OUT-OF-STOCK"))
                self._order_restock(sku, now, events)

        # приезд пополнений
        for sku, order in list(self.restock_at.items()):
            if now >= order["due"]:
                info = self.store.sales[sku]
                info.stock = min(info.capacity, info.stock + order["qty"])
                del self.restock_at[sku]
                events.appendleft((now, self.title,
                                   f"📦 {self.store.product(sku).name}: "
                                   f"полка пополнена "
                                   f"(+{order['qty']} шт.)"))

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
            for emu in self.stores.values():
                emu.dc = self.dc

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
    def state(self) -> dict:
        now = time.time()
        with self._lock:
            stores = [e.snapshot() for e in self.stores.values()]
            events = [{"t": round(t - self.started_at), "store": s,
                       "text": txt} for t, s, txt in list(self.events)[:20]]
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
