"""Дорожный граф города и маршрутизация по нему.

Граф строится из того же ``static/data/tver_map.geojson`` (выгрузка
OSM), которым рисуется карта: узлы — точки улиц, рёбра — сегменты
между соседними точками (OSM-линии разных улиц пересекаются в общих
узлах, поэтому перекрёстки связываются сами). Для маршрутизации
используется крупнейшая компонента связности; произвольные точки
(магазин, адрес клиента, РЦ) привязываются к ближайшему узлу.

API::

    net = get_roadnet()
    path, dist_m = net.route(lon1, lat1, lon2, lat2)
    # path — полилиния [(lon, lat), ...] по улицам, dist_m — метры

    pos = point_along(path, cum, метров)   # позиция вдоль пути
"""

import heapq
import itertools
import json
import math
import threading
from pathlib import Path
from typing import List, Optional, Tuple

_KX = 111320 * math.cos(math.radians(56.86))   # метров в градусе долготы
_KY = 110540                                   # метров в градусе широты

Node = Tuple[float, float]                     # (lon, lat)


def _dist(a: Node, b: Node) -> float:
    return math.hypot((a[0] - b[0]) * _KX, (a[1] - b[1]) * _KY)


class RoadNet:
    def __init__(self, geojson_path: Path):
        data = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
        self.adj: dict = {}
        for f in data["features"]:
            if f["properties"].get("kind") not in ("road", "road_major"):
                continue
            coords = f["geometry"]["coordinates"]
            for a, b in zip(coords, coords[1:]):
                a, b = tuple(a), tuple(b)
                d = _dist(a, b)
                if d < 0.1:
                    continue
                self.adj.setdefault(a, []).append((b, d))
                self.adj.setdefault(b, []).append((a, d))
        self.main = self._largest_component()
        self.nodes: List[Node] = list(self.main)

    def _largest_component(self) -> set:
        seen, best = set(), set()
        for start in self.adj:
            if start in seen:
                continue
            comp, stack = set(), [start]
            while stack:
                n = stack.pop()
                if n in comp:
                    continue
                comp.add(n)
                stack.extend(m for m, _ in self.adj[n] if m not in comp)
            seen |= comp
            if len(comp) > len(best):
                best = comp
        return best

    def snap(self, lon: float, lat: float) -> Node:
        p = (lon, lat)
        return min(self.nodes, key=lambda n: _dist(n, p))

    def route(self, lon1: float, lat1: float,
              lon2: float, lat2: float):
        """Кратчайший путь по улицам (A*). Возвращает (path, метры)."""
        src, dst = (lon1, lat1), (lon2, lat2)
        start, goal = self.snap(*src), self.snap(*dst)
        counter = itertools.count()
        openq = [(0.0, next(counter), 0.0, start, None)]
        came, gscore = {}, {start: 0.0}
        while openq:
            _f, _c, g, cur, parent = heapq.heappop(openq)
            if cur in came:
                continue
            came[cur] = parent
            if cur == goal:
                break
            for nxt, d in self.adj[cur]:
                if nxt not in self.main:
                    continue
                ng = g + d
                if ng < gscore.get(nxt, float("inf")):
                    gscore[nxt] = ng
                    heapq.heappush(openq, (ng + _dist(nxt, goal),
                                           next(counter), ng, nxt, cur))
        if goal not in came:                       # изолированная точка
            path = [src, dst]
        else:
            chain: List[Node] = []
            n: Optional[Node] = goal
            while n is not None:
                chain.append(n)
                n = came[n]
            chain.reverse()
            path = [src] + chain + [dst]
        # убрать дубли подряд
        cleaned = [path[0]]
        for p in path[1:]:
            if _dist(cleaned[-1], p) > 0.5:
                cleaned.append(p)
        if len(cleaned) < 2:
            cleaned = [src, dst]
        length = sum(_dist(a, b) for a, b in zip(cleaned, cleaned[1:]))
        return cleaned, max(length, 1.0)


def cumulative(path: List[Node]) -> List[float]:
    """Накопленные длины (м) для точек полилинии."""
    cum = [0.0]
    for a, b in zip(path, path[1:]):
        cum.append(cum[-1] + _dist(a, b))
    return cum


def point_along(path: List[Node], cum: List[float],
                meters: float) -> Node:
    """Точка на полилинии на расстоянии ``meters`` от начала."""
    if meters <= 0:
        return path[0]
    if meters >= cum[-1]:
        return path[-1]
    for i in range(1, len(cum)):
        if cum[i] >= meters:
            seg = cum[i] - cum[i - 1]
            k = (meters - cum[i - 1]) / seg if seg > 0 else 0
            a, b = path[i - 1], path[i]
            return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
    return path[-1]


_net: Optional[RoadNet] = None
_lock = threading.Lock()


def get_roadnet() -> RoadNet:
    global _net
    with _lock:
        if _net is None:
            _net = RoadNet(Path(__file__).parent / "static" / "data"
                           / "tver_map.geojson")
        return _net
