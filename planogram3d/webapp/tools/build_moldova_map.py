"""Сборка национальной карты Молдовы из выгрузок Overpass API (OSM).

Использование::

    python build_moldova_map.py roads.json water.json places.json out.geojson

Три входных файла — ответы Overpass ``out geom;``: трассы
(``way``, ``highway=motorway|trunk|primary``), вода (``way``,
``natural=water``) и населённые пункты (``node``, ``place=city|town``).
На выходе — FeatureCollection в масштабе всей страны, каждой фиче
проставлен ``properties.kind``:

* ``road_major`` — трассы motorway/trunk (LineString);
* ``road`` — трассы primary (LineString);
* ``water`` — крупные водоёмы, отфильтрованные по площади bbox (Polygon);
* ``place`` — города и посёлки (Point, ``name`` и ``rank``).

Национальный масштаб требует более грубых координат и жёсткой
фильтрации воды, чем городской ``build_map_data.py`` — иначе файл не
укладывается в размерный бюджет (см. ``docs/PLAN_FUEL_AUTOORDER.md``).
"""

import json
import math
import sys
from collections import Counter

MAJOR_ROADS = {"motorway", "trunk"}
ROADS = MAJOR_ROADS | {"primary"}

# Порог площади bbox водоёма в градусах² (≈ порядка десятков км² в
# широтах Молдовы). Подобран так, чтобы остались Днестр, Прут,
# крупные водохранилища (Кучурганское, Костешты-Стынка и т. п.), а
# многочисленные мелкие пруды и ставки — отсеялись.
MIN_WATER_BBOX_DEG2 = 0.0003

# Допуск упрощения линий трасс (алгоритм Дугласа — Пойкера), в
# градусах. ≈0.0008° ≈ 60–70 м в широтах Молдовы — заметно меньше
# расстояния между соседними станциями PECO, поэтому связность графа
# и правдоподобность длины маршрута не страдают, а количество точек
# (главный вклад в размер файла) падает в разы.
ROAD_SIMPLIFY_TOLERANCE_DEG = 0.0008


def _coord(lon, lat):
    return [round(lon, 4), round(lat, 4)]


def _perp_dist(p, a, b):
    """Перпендикулярное расстояние точки p до отрезка a-b (в градусах)."""
    if a == b:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj = (a[0] + t * dx, a[1] + t * dy)
    return math.hypot(p[0] - proj[0], p[1] - proj[1])


def _simplify(points, tolerance, protected):
    """Упрощение полилинии по Дугласу — Пойкеру.

    ``protected`` — множество координат (в виде кортежей), которые
    нельзя выбрасывать: это точки-перекрёстки, где в графе
    (``webapp/roadnet.py``) сходятся разные линии трасс — граф строит
    рёбра по совпадению координат соседних точек, и потеря такой точки
    молча разрывает связность, из-за чего маршрут идёт в объезд по
    другим дорогам вместо прямой.
    """
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    for i, p in enumerate(points):
        if tuple(p) in protected:
            keep[i] = True
    # Дуглас — Пойкер отдельно на каждом отрезке между уже
    # зафиксированными (обязательными) точками.
    forced = [i for i, k in enumerate(keep) if k]
    stack = [(a, b) for a, b in zip(forced, forced[1:])]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        a, b = points[lo], points[hi]
        best_d, best_i = -1.0, -1
        for i in range(lo + 1, hi):
            d = _perp_dist(points[i], a, b)
            if d > best_d:
                best_d, best_i = d, i
        if best_d > tolerance:
            keep[best_i] = True
            stack.append((lo, best_i))
            stack.append((best_i, hi))
    return [p for p, k in zip(points, keep) if k]


def _road_points(way):
    """Точки линии: округление и схлопывание повторов подряд."""
    pts = []
    for p in way.get("geometry", []):
        c = _coord(p["lon"], p["lat"])
        if not pts or pts[-1] != c:
            pts.append(c)
    return pts


def _water_coords(way):
    pts = []
    for p in way.get("geometry", []):
        c = _coord(p["lon"], p["lat"])
        if not pts or pts[-1] != c:
            pts.append(c)
    return pts


def _bbox_area(bounds):
    if not bounds:
        return 0.0
    return ((bounds["maxlon"] - bounds["minlon"])
             * (bounds["maxlat"] - bounds["minlat"]))


def convert(roads_path, water_path, places_path, out_path):
    features = []
    stats = {"road_major": 0, "road": 0, "water": 0, "place": 0}

    road_els = [el for el in json.load(open(roads_path))["elements"]
                if el.get("tags", {}).get("highway", "") in ROADS]
    road_pts = [_road_points(el) for el in road_els]

    # Точки-перекрёстки: там, где линии трасс соприкасаются координатами
    # (общий узел OSM), граф маршрутизации связывает их в одну сеть.
    # Такие точки упрощение не имеет права выбрасывать.
    freq = Counter()
    for pts in road_pts:
        freq.update(tuple(p) for p in set(map(tuple, pts)))
    junctions = {c for c, n in freq.items() if n > 1}

    for el, pts in zip(road_els, road_pts):
        pts = _simplify(pts, ROAD_SIMPLIFY_TOLERANCE_DEG, junctions)
        if len(pts) < 2:
            continue
        highway = el["tags"]["highway"]
        kind = "road_major" if highway in MAJOR_ROADS else "road"
        stats[kind] += 1
        features.append({
            "type": "Feature",
            "properties": {"kind": kind},
            "geometry": {"type": "LineString", "coordinates": pts}})

    for el in json.load(open(water_path))["elements"]:
        if _bbox_area(el.get("bounds")) < MIN_WATER_BBOX_DEG2:
            continue
        pts = _water_coords(el)
        if len(pts) < 4 or pts[0] != pts[-1]:
            continue
        stats["water"] += 1
        features.append({
            "type": "Feature",
            "properties": {"kind": "water"},
            "geometry": {"type": "Polygon", "coordinates": [pts]}})

    for el in json.load(open(places_path))["elements"]:
        tags = el.get("tags", {})
        name = tags.get("name")
        place = tags.get("place")
        if not name or place not in ("city", "town"):
            continue
        stats["place"] += 1
        features.append({
            "type": "Feature",
            "properties": {"kind": "place", "name": name, "rank": place},
            "geometry": {"type": "Point",
                         "coordinates": _coord(el["lon"], el["lat"])}})

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f,
                  separators=(",", ":"), ensure_ascii=False)

    import os
    size_kb = os.path.getsize(out_path) / 1024
    print(f"{out_path}: {len(features)} объектов "
          f"({size_kb:.0f} КБ)")
    for kind, n in stats.items():
        print(f"  {kind}: {n}")


if __name__ == "__main__":
    convert(*sys.argv[1:5])
