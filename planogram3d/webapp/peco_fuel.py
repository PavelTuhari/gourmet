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

import random
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

from .eta_ai import _PRIOR_SPEED, get_predictor
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

Node = Tuple[float, float]                      # (lon, lat)


def _geo_dist(net: RoadNet, a: Node, b: Node) -> float:
    """Расстояние (м) между координатами с масштабом конкретного графа."""
    return _dist(a, b, net.kx)


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

    # ----- события --------------------------------------------------------
    def _log(self, text: str) -> None:
        self.events.appendleft({"t": time.time(), "text": text})

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
            "message": (f"Автозаказ: {len(stops)} АЗС, "
                       f"{round(liters_total)} л, рейс {trip_id}"),
        })
        names = ", ".join(s["name"] for s in stops)
        self._log(f"🛢 Автозаказ → рейс {trip_id} ({driver}): {names}")

    # ----- движение бензовозов ----------------------------------------------
    def _evolve_trips(self, now: float, dt: float) -> None:
        predictor = get_predictor()
        for trip in list(self.trips.values()):
            if trip["status"] != "en_route" or now < trip["depart"]:
                continue
            total_len = trip["_cum"][-1]
            trip["leg_pos"] = min(total_len, trip["leg_pos"]
                                  + TANKER_SPEED * dt)
            for stop in trip["stops"]:
                if (stop["status"] == "pending"
                        and trip["leg_pos"] >= stop["cum_dist"] - 1.0):
                    stop["status"] = "done"
                    station = self.stations[stop["station_id"]]
                    station["current_l"] = min(
                        station["capacity_l"],
                        station["current_l"] + stop["liters"])
                    leg_m = stop["cum_dist"] - trip["_prev_cum"]
                    elapsed = max(1.0, now - trip["_leg_start_ts"])
                    predictor.observe("tanker", leg_m, elapsed)
                    trip["_prev_cum"] = stop["cum_dist"]
                    trip["_leg_start_ts"] = now
                    self._log(f"⛽ {trip['id']}: залив {stop['name']} "
                              f"(+{stop['liters']} л)")
            if (trip["leg_pos"] >= total_len - 1.0
                    and all(s["status"] == "done" for s in trip["stops"])):
                trip["status"] = "done"
                trip["_done_at"] = now
                self._log(f"✅ Рейс {trip['id']} завершён "
                          f"({trip['driver']})")
        # завершённые рейсы держим на экране ещё немного, потом чистим
        self.trips = {k: v for k, v in self.trips.items()
                      if v["status"] == "en_route"
                      or now - v.get("_done_at", now) < 90}

    # ----- снимок состояния (evolve-on-poll) --------------------------------
    def state(self) -> dict:
        now = time.time()
        dt = min(MAX_DT, now - self._last)
        self._last = now

        self._consume(dt)
        self._maybe_dispatch(now)
        self._evolve_trips(now, dt)

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
                "stops": [{"station_id": s["station_id"],
                          "name": s["name"], "liters": s["liters"],
                          "eta_ts": s["eta_ts"], "status": s["status"]}
                         for s in trip["stops"]],
            })

        return {
            "now": now, "source": "emulation",
            "depot": {**self.depot,
                     "fill_pct": round(100 * self.depot["current_l"]
                                       / self.depot["capacity_l"], 1)},
            "stations": stations_out,
            "trips": trips_out,
            "runs": list(self.runs),
            "events": list(self.events)[:20],
        }
