"""Эмуляция работающей сети магазинов.

Каждый магазин сети — полноценный :class:`planogram3d.core.Store`
(со своей планограммой и продажами), привязанный к реальным координатам
в городе. Фоновый «тикер» ускоренно проигрывает торговый день: списывает
остатки по скорости продаж, начисляет выручку, устраивает out-of-stock
и пополнения, ведёт ленту событий — в духе игровых симуляторов магазинов.
"""

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
    restock_at: Dict[str, float] = field(default_factory=dict)
    last_tick_revenue: float = 0.0
    critical_violations: int = 0

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
                    self.restock_at[sku] = now + self.rng.uniform(25, 80)
                    events.appendleft((now, self.title,
                                       f"⛔ {product.name}: полка пуста, "
                                       f"заказано пополнение"))
                continue
            n = min(n, info.stock)
            info.stock -= n
            info.sold_today += n
            self.transactions += n
            sold_value += n * price_for(product.category, sku)
            if info.stock == 0:
                self.restock_at[sku] = now + self.rng.uniform(25, 80)
                events.appendleft((now, self.title,
                                   f"⛔ {product.name}: OUT-OF-STOCK"))

        # приезд пополнений
        for sku, due in list(self.restock_at.items()):
            if now >= due:
                info = self.store.sales[sku]
                info.stock = info.capacity
                del self.restock_at[sku]
                events.appendleft((now, self.title,
                                   f"📦 {self.store.product(sku).name}: "
                                   f"полка пополнена"))

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

    def __init__(self, tick_seconds: float = 2.0):
        self.tick_seconds = tick_seconds
        self.events: Deque = deque(maxlen=40)
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

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
            last = now

    # ----- API ------------------------------------------------------------
    def state(self) -> dict:
        with self._lock:
            stores = [e.snapshot() for e in self.stores.values()]
            events = [{"t": round(t - self.started_at), "store": s,
                       "text": txt} for t, s, txt in list(self.events)[:20]]
        sim_seconds = (time.time() - self.started_at) * TIME_SCALE
        return {
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
