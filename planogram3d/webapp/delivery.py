"""Интернет-заказы: сборка, маршруты, доставка, GPS-мониторинг, чеки.

Полный сценарий работы магазина с онлайн-заказами:

1. **Заказы** поступают (эмулятор или интеграция интернет-магазина),
   привязываются к ближайшему магазину сети; сборщик собирает позиции
   по планограмме (new → picking → packed).
2. **Группировка по маршрутам**: собранные заказы объединяются в
   маршрут (2–4 адреса, ближайший-сосед от магазина), маршрут получает
   курьера и плановый график — из него строится **диаграмма Ганта**
   (план/факт по каждому плечу: дорога и вручение).
3. **Мониторинг в реальном времени**: положение курьера на карте города
   ведётся по GPS-координатам из курьерского приложения — эмулятор
   движется по маршруту с шумом координат, а реальное приложение шлёт
   телеметрию на ``POST /api/delivery/gps`` (тогда эмуляция координат
   этого курьера отключается).
4. **Чек в момент вручения** — по 54-ФЗ, двумя способами в зависимости
   от типа приложения курьера:

   * ``android`` — обычный Android-смартфон: чек фискализируется через
     облачную кассу магазина и отправляется покупателю (СМС/e-mail),
     курьеру доступна печать на мобильном Bluetooth-принтере;
   * ``smartpos`` — смарт-терминал «SmartOne» с фискальным накопителем
     (ФН) на борту: бумажный чек печатается на месте вручения, работает
     и офлайн.

Печатная форма чека — ``GET /receipt/<id>``.
"""

import math
import random
import threading
import time
from collections import deque
from typing import Dict, List, Optional

from .network import StoreNetwork, price_for
from .roadnet import cumulative, get_roadnet, point_along

REAL_GPS_TIMEOUT = 45.0     # с: реальная телеметрия активна

CUSTOMERS = ["Иванова А.", "Петров С.", "Сидорова М.", "Кузнецов Д.",
             "Волкова Е.", "Смирнов И.", "Козлова О.", "Новиков П.",
             "Морозова Т.", "Фёдоров К."]
STREETS = ["ул. Советская", "ул. Трёхсвятская", "наб. Степана Разина",
           "Тверской пр-т", "ул. Новоторжская", "ул. Желябова",
           "б-р Радищева", "ул. Вольного Новгорода"]

#: курьеры сети: (id, имя, тип приложения)
COURIERS = [
    ("c1", "Курьер Алексей", "android"),
    ("c2", "Курьер Мария", "smartpos"),
    ("c3", "Курьер Тимур", "android"),
    ("c4", "Курьер Ольга", "smartpos"),
]
APP_TITLES = {"android": "📱 Android (облачная касса)",
              "smartpos": "🖨 SmartOne (ФН на борту)"}

#: скорость курьера в эмуляции, м/с (ускорено для наглядности)
COURIER_SPEED = 22.0
HANDOVER_PLAN = 25.0        # плановое вручение + чек, с


def _dist_m(lat1, lon1, lat2, lon2) -> float:
    kx = 111320 * math.cos(math.radians(56.86))
    return math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * 110540)


class DeliveryHub:
    """Диспетчер интернет-заказов и доставки по сети магазинов."""

    def __init__(self, network: StoreNetwork, seed: int = 314):
        self.network = network
        self.rng = random.Random(seed)
        self._lock = threading.Lock()
        self._last = time.time()
        self.orders: Dict[str, dict] = {}
        self.routes: Dict[str, dict] = {}
        self.receipts: deque = deque(maxlen=60)
        self.events: deque = deque(maxlen=40)
        self._order_seq = 1
        self._route_seq = 1
        self._receipt_seq = 1
        self._next_order = time.time() + 2.0
        self.couriers = {cid: {"id": cid, "name": name, "app": app,
                               "route": None, "lat": None, "lon": None,
                               "last_real": 0.0, "battery":
                               self.rng.randint(45, 100)}
                         for cid, name, app in COURIERS}

    # ----- события ------------------------------------------------------
    def _log(self, text: str) -> None:
        self.events.appendleft({"t": time.time(), "text": text})

    # ----- заказы -------------------------------------------------------
    def _spawn_order(self, now: float) -> None:
        rng = self.rng
        lat = rng.uniform(56.850, 56.871)
        lon = rng.uniform(35.878, 35.923)
        stores = list(self.network.stores.values())
        store = min(stores, key=lambda s: _dist_m(lat, lon, s.lat, s.lon))
        items = []
        skus = rng.sample(list(store.store.products), rng.randint(2, 5))
        total = 0.0
        for sku in skus:
            product = store.store.product(sku)
            qty = rng.randint(1, 3)
            price = round(price_for(product.category, sku))
            items.append({"sku": sku, "name": product.name, "qty": qty,
                          "price": price})
            total += qty * price
        oid = f"WEB-{self._order_seq:04d}"
        self._order_seq += 1
        self.orders[oid] = {
            "id": oid, "store_id": store.store_id,
            "store_name": store.title,
            "customer": rng.choice(CUSTOMERS),
            "address": f"{rng.choice(STREETS)}, {rng.randint(1, 60)}",
            "lat": round(lat, 5), "lon": round(lon, 5),
            "items": items, "total": round(total),
            "status": "new", "created": now, "pick_done": 0.0,
            "route": None, "receipt": None,
        }
        self._log(f"🛒 Новый интернет-заказ {oid} → {store.title} "
                  f"({len(items)} поз., {round(total)} ₽)")

    def _evolve_picking(self, now: float) -> None:
        for o in self.orders.values():
            if o["status"] == "new":
                o["status"] = "picking"
                o["pick_done"] = now + self.rng.uniform(12, 26)
                self._log(f"🧺 {o['id']}: сборщик приступил "
                          f"({o['store_name']})")
            elif o["status"] == "picking" and now >= o["pick_done"]:
                o["status"] = "packed"
                self._log(f"📦 {o['id']}: собран и упакован")

    # ----- маршруты -----------------------------------------------------
    def _free_courier(self) -> Optional[dict]:
        for c in self.couriers.values():
            if c["route"] is None:
                return c
        return None

    def _build_routes(self, now: float) -> None:
        by_store: Dict[str, List[dict]] = {}
        for o in self.orders.values():
            if o["status"] == "packed":
                by_store.setdefault(o["store_id"], []).append(o)
        for store_id, packed in by_store.items():
            oldest = min(o["pick_done"] for o in packed)
            if len(packed) < 2 and now - oldest < 20:
                continue
            courier = self._free_courier()
            if courier is None:
                return
            emu = self.network.stores[store_id]
            batch = packed[:4]
            # ближайший сосед от магазина — порядок объезда
            ordered, cur = [], (emu.lat, emu.lon)
            pool = list(batch)
            while pool:
                nxt = min(pool, key=lambda o: _dist_m(cur[0], cur[1],
                                                      o["lat"], o["lon"]))
                pool.remove(nxt)
                ordered.append(nxt)
                cur = (nxt["lat"], nxt["lon"])
            rid = f"R-{self._route_seq:03d}"
            self._route_seq += 1
            t = now + 4.0
            net = get_roadnet()
            stops, prev = [], (emu.lat, emu.lon)
            for o in ordered:
                # путь строго по дорогам города (граф OSM)
                path, road_m = net.route(prev[1], prev[0],
                                         o["lon"], o["lat"])
                travel = max(15.0, road_m / COURIER_SPEED)
                stops.append({
                    "order": o["id"], "customer": o["customer"],
                    "address": o["address"], "lat": o["lat"],
                    "lon": o["lon"], "total": o["total"],
                    "path": [[round(p[0], 5), round(p[1], 5)]
                             for p in path],
                    "road_m": round(road_m),
                    "plan_start": t, "plan_arrive": t + travel,
                    "plan_done": t + travel + HANDOVER_PLAN,
                    "actual_start": None, "actual_arrive": None,
                    "actual_done": None, "status": "pending",
                })
                t += travel + HANDOVER_PLAN
                prev = (o["lat"], o["lon"])
                o["status"] = "routed"
                o["route"] = rid
            self.routes[rid] = {
                "id": rid, "store_id": store_id,
                "store_name": emu.title,
                "store_lat": emu.lat, "store_lon": emu.lon,
                "courier": courier["id"], "status": "active",
                "created": now, "stops": stops, "stop_idx": 0,
                "phase": "to_stop", "phase_t": now + 4.0,
                "leg_pos": 0.0,
            }
            courier["route"] = rid
            courier["lat"], courier["lon"] = emu.lat, emu.lon
            self._log(f"🗺 Маршрут {rid}: {len(stops)} заказ(а) из "
                      f"{emu.title} → {courier['name']} "
                      f"({APP_TITLES[courier['app']]})")

    # ----- чек в момент вручения ---------------------------------------
    def _fiscal_receipt(self, route: dict, stop: dict, now: float) -> str:
        courier = self.couriers[route["courier"]]
        order = self.orders[stop["order"]]
        rng = self.rng
        rid = f"FD-{self._receipt_seq:05d}"
        self._receipt_seq += 1
        fn = ("9960440300" + str(100000 + rng.randint(0, 899999))
              if courier["app"] == "smartpos" else
              "7280440700" + str(100000 + rng.randint(0, 899999)))
        fp = rng.randint(10 ** 9, 10 ** 10 - 1)
        stamp = time.strftime("%Y%m%dT%H%M", time.localtime(now))
        receipt = {
            "id": rid, "order": order["id"], "route": route["id"],
            "customer": order["customer"], "address": order["address"],
            "items": order["items"], "total": order["total"],
            "courier": courier["name"], "app": courier["app"],
            "app_title": APP_TITLES[courier["app"]],
            "fn": fn, "fd": self._receipt_seq + 4200, "fp": fp,
            "qr": (f"t={stamp}&s={order['total']}.00&fn={fn}"
                   f"&i={self._receipt_seq + 4200}&fp={fp}&n=1"),
            "printed_at": now,
            "print_way": ("напечатан на терминале SmartOne (ФН на борту)"
                          if courier["app"] == "smartpos" else
                          "фискализирован облачной кассой, электронный "
                          "чек отправлен покупателю"),
        }
        self.receipts.appendleft(receipt)
        order["receipt"] = rid
        self._log(f"🧾 Чек {rid} ({order['id']}, {order['total']} ₽) — "
                  f"{receipt['print_way']}")
        return rid

    # ----- движение курьеров -------------------------------------------
    def _evolve_routes(self, now: float, dt: float) -> None:
        for route in list(self.routes.values()):
            if route["status"] != "active":
                continue
            courier = self.couriers[route["courier"]]
            real_gps = now - courier["last_real"] < REAL_GPS_TIMEOUT
            idx = route["stop_idx"]
            if idx >= len(route["stops"]):
                route["status"] = "done"
                courier["route"] = None
                self._log(f"✅ Маршрут {route['id']} завершён "
                          f"({courier['name']})")
                continue
            stop = route["stops"][idx]

            if route["phase"] == "to_stop":
                if stop["actual_start"] is None and now >= route["phase_t"]:
                    stop["actual_start"] = now
                    stop["status"] = "en_route"
                if stop["actual_start"] is None:
                    continue
                if not real_gps:
                    # едем строго по дорожной полилинии
                    path = [tuple(p) for p in stop["path"]]
                    cum = stop.get("_cum")
                    if cum is None:
                        cum = stop["_cum"] = cumulative(path)
                    route["leg_pos"] += COURIER_SPEED * dt
                    lon, lat = point_along(path, cum, route["leg_pos"])
                    # лёгкий GPS-шум, не уводящий с дороги
                    courier["lon"] = lon + self.rng.gauss(0, 4e-6)
                    courier["lat"] = lat + self.rng.gauss(0, 3e-6)
                    arrived = route["leg_pos"] >= cum[-1] - 1.0
                else:
                    arrived = _dist_m(courier["lat"], courier["lon"],
                                      stop["lat"], stop["lon"]) < 25
                if arrived:
                    stop["actual_arrive"] = now
                    stop["status"] = "handover"
                    route["phase"] = "handover"
                    route["phase_t"] = now + self.rng.uniform(14, 32)
                    self._log(f"🏠 {route['id']}: прибытие к "
                              f"{stop['customer']} ({stop['address']})")
            elif route["phase"] == "handover" and now >= route["phase_t"]:
                stop["actual_done"] = now
                stop["status"] = "done"
                self.orders[stop["order"]]["status"] = "delivered"
                self._fiscal_receipt(route, stop, now)
                route["stop_idx"] += 1
                route["phase"] = "to_stop"
                route["phase_t"] = now
                route["leg_pos"] = 0.0
            courier["battery"] = max(3, courier["battery"] - 0.006 * dt)

    # ----- API ----------------------------------------------------------
    def ingest_gps(self, courier_id: str, lat: float, lon: float,
                   battery: Optional[float] = None) -> bool:
        with self._lock:
            c = self.couriers.get(courier_id)
            if c is None:
                return False
            c["lat"], c["lon"] = float(lat), float(lon)
            c["last_real"] = time.time()
            if battery is not None:
                c["battery"] = float(battery)
            return True

    def state(self) -> dict:
        now = time.time()
        with self._lock:
            dt = min(5.0, now - self._last)
            self._last = now
            active_orders = sum(1 for o in self.orders.values()
                                if o["status"] != "delivered")
            if now >= self._next_order and active_orders < 14:
                self._spawn_order(now)
                self._next_order = now + self.rng.uniform(6, 14)
            self._evolve_picking(now)
            self._build_routes(now)
            self._evolve_routes(now, dt)

            orders = sorted(self.orders.values(),
                            key=lambda o: -o["created"])[:30]
            routes = []
            for r in self.routes.values():
                if (r["status"] == "done"
                        and now - r["stops"][-1]["plan_done"] > 120):
                    continue
                courier = self.couriers[r["courier"]]
                stops_out = [{k: v for k, v in s.items()
                              if not k.startswith("_")}
                             for s in r["stops"]]
                routes.append({
                    **{k: r[k] for k in ("id", "store_id", "store_name",
                                         "store_lat", "store_lon",
                                         "status")},
                    "stops": stops_out,
                    "courier": {
                        "id": courier["id"], "name": courier["name"],
                        "app": courier["app"],
                        "app_title": APP_TITLES[courier["app"]],
                        "lat": courier["lat"], "lon": courier["lon"],
                        "battery": round(courier["battery"]),
                        "gps_source": ("приложение (реальный GPS)"
                                       if now - courier["last_real"]
                                       < REAL_GPS_TIMEOUT
                                       else "эмуляция"),
                    }})
            return {
                "now": now,
                "orders": orders,
                "routes": routes,
                "receipts": list(self.receipts)[:12],
                "events": list(self.events)[:18],
                "counters": {
                    "new": sum(1 for o in self.orders.values()
                               if o["status"] in ("new", "picking")),
                    "packed": sum(1 for o in self.orders.values()
                                  if o["status"] == "packed"),
                    "delivering": sum(1 for o in self.orders.values()
                                      if o["status"] == "routed"),
                    "delivered": sum(1 for o in self.orders.values()
                                     if o["status"] == "delivered"),
                    "receipts": len(self.receipts),
                },
            }

    def receipt(self, receipt_id: str) -> Optional[dict]:
        with self._lock:
            for r in self.receipts:
                if r["id"] == receipt_id:
                    return dict(r)
        return None
