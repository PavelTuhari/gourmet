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
4. **Фискальный чек (bon fiscal) в момент вручения** — по требованиям SFS
   Молдовы, двумя способами в зависимости
   от типа приложения курьера:

   * ``android`` — обычный Android-смартфон: чек фискализируется через
     облачную кассу магазина и отправляется покупателю (СМС/e-mail),
     курьеру доступна печать на мобильном Bluetooth-принтере;
   * ``smartpos`` — смарт-терминал «SmartOne» с фискальным накопителем
     (ECC) на борту: бумажный чек печатается на месте вручения, работает
     и офлайн.

Печатная форма чека — ``GET /receipt/<id>``.
"""

import math
import random
import threading
import time
from collections import deque
from typing import Dict, List, Optional

from .eta_ai import get_predictor
from .i18n import DEFAULT_LANG, PluralRef, render_event
from .i18n import t as i18n_t
from .network import DistributionCenter, StoreNetwork, price_for
from .roadnet import cumulative, get_roadnet, point_along

REAL_GPS_TIMEOUT = 45.0     # с: реальная телеметрия активна

# ----- реквизиты фискального чека (bon fiscal), молдавское законодательство -
#
# HG 141/2019 требует: наименование и IDNO налогоплательщика, адрес
# подразделения, заводской и регистрационный (SFS) номера ECC, номер чека,
# наименование/стоимость/код ставки TVA по каждой позиции, итоги TVA по
# каждой ставке отдельно. Реквизиты 54-ФЗ (ФН/ФД/ФП, QR t=&s=&fn=...) сюда
# не переносим — это другой правовой режим.
COMPANY_NAME = 'SRL "Gurman Retail"'          # официальное имя — латиницей,
                                               # как в регистрации, не переводим
COMPANY_IDNO = "1003600123456"                # фискальный код, 13 цифр (демо)

#: ставки TVA Молдовы: 20% стандартная, 8% льготная (хлеб, молоко и
#: молочные продукты — HG 141/2019). В демо-каталоге проекта только одна
#: льготная категория, остальные — по стандартной ставке.
VAT_STANDARD = 20
VAT_REDUCED = 8
VAT_REDUCED_CATEGORIES = {"Молочные продукты"}


def vat_rate_for(category: str) -> int:
    return VAT_REDUCED if category in VAT_REDUCED_CATEGORIES else VAT_STANDARD


#: ECC (Echipament de casă și de control) — молдавский аналог ККМ. Два типа
#: регистрации по типу приложения курьера, как и раньше для ФН: облачная
#: касса (android) и терминал со встроенным ECC (smartpos).
_ECC_BY_APP = {
    "android": {"serial_prefix": "ECC-CLD", "reg_prefix": "SFS-00417"},
    "smartpos": {"serial_prefix": "ECC-SPT", "reg_prefix": "SFS-00512"},
}

CUSTOMERS = ["Попеску А.", "Чобану С.", "Русу М.", "Морару Д.",
             "Лунгу Е.", "Балан И.", "Врабие О.", "Цуркану П.",
             "Ротару Т.", "Плешка К."]
STREETS = ["бул. Штефан чел Маре", "ул. Измаил", "ул. Албишоара",
           "ул. Пушкина", "ул. Когэлничану", "бул. Дачия",
           "ул. Каля Ешилор", "ул. Мирча чел Бэтрын"]

#: курьеры сети: (id, имя, тип приложения)
COURIERS = [
    ("c1", "Курьер Алексей", "android"),
    ("c2", "Курьер Мария", "smartpos"),
    ("c3", "Курьер Тимур", "android"),
    ("c4", "Курьер Ольга", "smartpos"),
]
#: эмодзи типа кассы курьера — подпись в приложении, а не переводимый текст;
#: сам текст берётся из каталога (receipt.app.*), общего с чеком
_APP_ICONS = {"android": "📱", "smartpos": "🖨"}


def app_title(lang: str, app: str) -> str:
    return f"{_APP_ICONS.get(app, '')} {i18n_t(lang, f'receipt.app.{app}')}"

#: скорость курьера в эмуляции, м/с (ускорено для наглядности)
COURIER_SPEED = 22.0
HANDOVER_PLAN = 25.0        # плановое вручение + чек, с


def _dist_m(lat1, lon1, lat2, lon2) -> float:
    kx = 111320 * math.cos(math.radians(47.02))   # широта Кишинёва
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
    def _log(self, icon: str, key: str, count=None, **params) -> None:
        """Запись ленты: ключ+параметры, а не готовый текст — язык
        выбирается при отдаче (`state(lang)`), см. `i18n.render_event`."""
        self.events.appendleft({"t": time.time(), "icon": icon, "key": key,
                                "params": params, "count": count})

    # ----- заказы -------------------------------------------------------
    def _spawn_order(self, now: float) -> None:
        rng = self.rng
        lat = rng.uniform(46.985, 47.055)
        lon = rng.uniform(28.790, 28.900)
        stores = list(self.network.stores.values())
        store = min(stores, key=lambda s: _dist_m(lat, lon, s.lat, s.lon))
        items = []
        skus = rng.sample(list(store.store.products), rng.randint(2, 5))
        total = 0.0
        for sku in skus:
            product = store.store.product(sku)
            qty = rng.randint(1, 3)
            price = round(price_for(product.category, sku))
            # категория несём в заказ — нужна на чеке для кода ставки TVA
            items.append({"sku": sku, "name": product.name, "qty": qty,
                          "price": price, "category": product.category})
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
        self._log("🛒", "log.new_order", count=len(items),
                  oid=oid, store=store.title, total=round(total),
                  items_word=PluralRef("log.new_order.items_word"))

    def _evolve_picking(self, now: float) -> None:
        for o in self.orders.values():
            if o["status"] == "new":
                o["status"] = "picking"
                o["pick_done"] = now + self.rng.uniform(12, 26)
                self._log("🧺", "log.picking_started",
                          oid=o["id"], store=o["store_name"])
            elif o["status"] == "picking" and now >= o["pick_done"]:
                o["status"] = "packed"
                self._log("📦", "log.packed", oid=o["id"])

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
            hour = self.network.sim_hour(now)
            for o in ordered:
                # путь строго по дорогам города (граф OSM)
                path, road_m = net.route(prev[1], prev[0],
                                         o["lon"], o["lat"])
                travel = max(15.0, road_m / COURIER_SPEED)
                # фактическая скорость плеча: трафик часа + случайность;
                # план оптимистичен, ИИ-табло учится на факте
                actual_v = (COURIER_SPEED
                            * DistributionCenter._traffic(hour)
                            * self.rng.uniform(0.8, 1.15))
                stops.append({
                    "_v": actual_v,
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
            # событие хранит ключ+параметры — форма "заказ(а)" и язык
            # подписи кассы выбираются при отдаче ленты (`state(lang)`),
            # а не здесь, поэтому переключение языка перерисовывает и
            # уже накопленные записи, а не только новые
            self._log(
                "🗺", "log.route_built", count=len(stops),
                route=rid,
                orders_word=PluralRef("log.route_built.orders_word"),
                store=emu.title, courier=courier["name"],
                app_title=PluralRef(f"receipt.app.{courier['app']}"))

    # ----- чек в момент вручения ---------------------------------------
    def _fiscal_receipt(self, route: dict, stop: dict, now: float) -> str:
        courier = self.couriers[route["courier"]]
        order = self.orders[stop["order"]]
        rng = self.rng
        rid = f"FD-{self._receipt_seq:05d}"
        self._receipt_seq += 1
        ecc = _ECC_BY_APP[courier["app"]]
        # серийный/регистрационный номер ECC — стабильны для типа кассы,
        # но с демо-хвостом, чтобы у разных чеков не совпадали буквально
        ecc_serial = f"{ecc['serial_prefix']}-{100000 + rng.randint(0, 899999)}"
        ecc_reg = f"{ecc['reg_prefix']}-{1000 + self._receipt_seq}"
        # TVA считаем от цены с включённым налогом (розничная цена в
        # каталоге — конечная), по каждой ставке — отдельная сумма
        vat_totals: Dict[int, Dict[str, float]] = {}
        for it in order["items"]:
            rate = vat_rate_for(it.get("category", ""))
            it["vat_rate"] = rate
            line_total = it["qty"] * it["price"]
            line_base = line_total / (1 + rate / 100)
            bucket = vat_totals.setdefault(rate, {"base": 0.0, "vat": 0.0})
            bucket["base"] += line_base
            bucket["vat"] += line_total - line_base
        vat_breakdown = [
            {"rate": rate, "base": round(v["base"]), "vat": round(v["vat"])}
            for rate, v in sorted(vat_totals.items())]
        receipt = {
            "id": rid, "order": order["id"], "route": route["id"],
            "customer": order["customer"], "address": order["address"],
            "store_name": order["store_name"], "items": order["items"],
            "total": order["total"], "vat_breakdown": vat_breakdown,
            "courier": courier["name"], "app": courier["app"],
            "company_name": COMPANY_NAME, "idno": COMPANY_IDNO,
            "ecc_serial": ecc_serial, "ecc_reg": ecc_reg,
            "printed_at": now,
            # готового текста print_way здесь больше нет: ключ
            # receipt.print_way.<app> резолвится на языке запроса — и на
            # /receipt/<id> (server.py), и в панели чеков /delivery, и в
            # ленте событий ниже (см. `_render_receipt` / `render_event`)
        }
        self.receipts.appendleft(receipt)
        order["receipt"] = rid
        self._log("🧾", "log.receipt_issued", rid=rid, oid=order["id"],
                  total=order["total"],
                  print_way=PluralRef(f"receipt.print_way.{courier['app']}"))
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
                self._log("✅", "log.route_done",
                          route=route["id"], courier=courier["name"])
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
                    route["leg_pos"] += stop.get("_v", COURIER_SPEED) * dt
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
                    # телеметрия плеча → обучение ИИ-модели прибытия
                    get_predictor().observe(
                        "courier", stop.get("road_m", 0.0),
                        now - stop["actual_start"],
                        hour=self.network.sim_hour(stop["actual_start"]))
                    self._log("🏠", "log.arrived", route=route["id"],
                              customer=stop["customer"],
                              address=stop["address"])
            elif route["phase"] == "handover" and now >= route["phase_t"]:
                stop["actual_done"] = now
                stop["status"] = "done"
                get_predictor().observe_duration(
                    "handover", now - stop["actual_arrive"])
                self.orders[stop["order"]]["status"] = "delivered"
                self._fiscal_receipt(route, stop, now)
                route["stop_idx"] += 1
                route["phase"] = "to_stop"
                route["phase_t"] = now
                route["leg_pos"] = 0.0
            courier["battery"] = max(3, courier["battery"] - 0.006 * dt)

    # ----- ИИ-прогноз прибытия (онлайн-табло пунктов доставки) ----------
    def _ai_stop_predictions(self, route: dict, now: float,
                             lang: str = DEFAULT_LANG) -> Dict[str, dict]:
        """Прогноз прибытия курьера на каждую оставшуюся остановку.

        Модель — общий :mod:`eta_ai`-прогнозист (скорости учатся на
        телеметрии завершённых плеч, вручение — на фактических
        длительностях). Неопределённость копится по плечам (σ²).
        """
        out: Dict[str, dict] = {}
        if route["status"] != "active":
            return out
        predictor = get_predictor()
        hour = self.network.sim_hour(now)
        hand_s, hand_sig, _ = predictor.predict_duration("handover")
        courier = self.couriers[route["courier"]]
        t, var = now, 0.0
        for i in range(route["stop_idx"], len(route["stops"])):
            stop = route["stops"][i]
            current = i == route["stop_idx"]
            if current and stop["status"] == "handover":
                out[stop["order"]] = {
                    "ai_arrive": stop["actual_arrive"], "ai_sigma": 0,
                    "ai_note": i18n_t(lang, "ai.handover_in_progress")}
                t = max(now, route["phase_t"])
                var += hand_sig * hand_sig
                continue
            if current and stop["status"] == "en_route":
                cum = stop.get("_cum")
                if cum is not None:
                    remaining = max(0.0, cum[-1] - route["leg_pos"])
                elif courier["lat"] is not None:   # реальный GPS без плеча
                    remaining = 1.25 * _dist_m(courier["lat"],
                                               courier["lon"],
                                               stop["lat"], stop["lon"])
                else:
                    remaining = stop.get("road_m", 0.0)
            else:
                remaining = stop.get("road_m", 0.0)
            travel_s, sig, n_obs = predictor.predict("courier", remaining,
                                                     hour=hour)
            if current and stop["actual_start"] is None:
                travel_s += max(0.0, route["phase_t"] - now)  # ещё не выехал
            arrive = t + travel_s
            var += sig * sig
            out[stop["order"]] = {
                "ai_arrive": arrive,
                "ai_sigma": round(max(2.0, math.sqrt(var))),
                "ai_note": (i18n_t(lang, "ai.model_trained", n=n_obs,
                                   legs_word=i18n_t(
                                       lang, "ai.model_trained.legs_word",
                                       count=n_obs))
                            if n_obs else i18n_t(lang, "ai.model_prior"))}
            t = arrive + hand_s
            var += hand_sig * hand_sig
        return out

    def arrival_board(self, order_id: str,
                      lang: str = DEFAULT_LANG) -> Optional[dict]:
        """Онлайн-табло пункта доставки (адреса покупателя)."""
        now = time.time()
        with self._lock:
            order = self.orders.get(order_id)
            if order is None:
                return None
            rows = []
            route = self.routes.get(order["route"] or "")
            if route is not None and route["status"] == "active":
                ai = self._ai_stop_predictions(route, now, lang)
                courier = self.couriers[route["courier"]]
                queue = [s["order"] for s in
                         route["stops"][route["stop_idx"]:]]
                for pos, s in enumerate(route["stops"]):
                    if s["order"] not in ai:
                        continue
                    p = ai[s["order"]]
                    rows.append({
                        "type": "courier",
                        "icon": "🛵",
                        "order": s["order"],
                        "this_point": s["order"] == order_id,
                        "label": (f"{courier['name']} · "
                                  f"{app_title(lang, courier['app'])}"),
                        "queue_pos": (queue.index(s["order"]) + 1
                                      if s["order"] in queue else None),
                        "eta_ts": p["ai_arrive"],
                        "eta_sec": max(0, round(p["ai_arrive"] - now)),
                        "sigma_sec": p["ai_sigma"],
                        "plan_ts": s["plan_arrive"],
                        "status": s["status"],
                        "source": i18n_t(lang, "ai.forecast_prefix",
                                         note=p["ai_note"]),
                        "gps_source": (i18n_t(lang, "gps.real")
                                       if now - courier["last_real"]
                                       < REAL_GPS_TIMEOUT else
                                       i18n_t(lang, "gps.emulated")),
                    })
            return {"now": now, "order": order_id,
                    "point": f"{order['customer']} · {order['address']}",
                    "status": order["status"], "rows": rows,
                    "model": get_predictor().summary()}

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

    def state(self, lang: str = DEFAULT_LANG) -> dict:
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

            orders = [{**o, "status_label": i18n_t(lang,
                                                    f"status.{o['status']}")}
                     for o in sorted(self.orders.values(),
                                    key=lambda o: -o["created"])[:30]]
            routes = []
            for r in self.routes.values():
                if (r["status"] == "done"
                        and now - r["stops"][-1]["plan_done"] > 120):
                    continue
                courier = self.couriers[r["courier"]]
                ai = self._ai_stop_predictions(r, now, lang)
                stops_out = [{**{k: v for k, v in s.items()
                                 if not k.startswith("_")},
                              **ai.get(s["order"], {})}
                             for s in r["stops"]]
                routes.append({
                    **{k: r[k] for k in ("id", "store_id", "store_name",
                                         "store_lat", "store_lon",
                                         "status")},
                    "stops": stops_out,
                    "courier": {
                        "id": courier["id"], "name": courier["name"],
                        "app": courier["app"],
                        "app_title": app_title(lang, courier["app"]),
                        "lat": courier["lat"], "lon": courier["lon"],
                        "battery": round(courier["battery"]),
                        "gps_source": (i18n_t(lang, "gps.real")
                                       if now - courier["last_real"]
                                       < REAL_GPS_TIMEOUT
                                       else i18n_t(lang, "gps.emulated")),
                    }})
            receipts = [{**r, "print_way": i18n_t(
                            lang, f"receipt.print_way.{r['app']}")}
                       for r in list(self.receipts)[:12]]
            events = [{"t": ev["t"], "text": render_event(lang, ev)}
                     for ev in list(self.events)[:18]]
            return {
                "now": now,
                "orders": orders,
                "routes": routes,
                "receipts": receipts,
                "events": events,
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
