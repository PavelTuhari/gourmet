"""Сборка карты города из выгрузок Overpass API (OSM) в один GeoJSON.

Использование::

    python build_map_data.py roads.json buildings.json nature.json out.geojson

Каждый входной файл — ответ Overpass ``out geom;`` (элементы ``way`` с
геометрией). На выходе — FeatureCollection, где каждой фиче проставлен
``properties.kind``:

* ``road`` / ``road_major`` — улицы (LineString);
* ``building`` — здания (Polygon, с высотой ``h`` в метрах);
* ``water`` — вода (Polygon);
* ``park`` — парки и сады (Polygon).
"""

import json
import sys

MAJOR_ROADS = {"primary", "secondary", "trunk", "tertiary"}


def _coords(way):
    return [[round(p["lon"], 6), round(p["lat"], 6)]
            for p in way.get("geometry", [])]


def _building_height(tags):
    """Высота здания: явные теги, этажность × 3 м или типовые значения."""
    try:
        return float(str(tags["height"]).replace("m", "").strip())
    except (KeyError, ValueError):
        pass
    try:
        return max(3.0, float(tags["building:levels"]) * 3.0)
    except (KeyError, ValueError):
        pass
    kind = tags.get("building", "yes")
    return {"apartments": 15.0, "house": 6.0, "detached": 6.0,
            "garage": 3.0, "garages": 3.0, "shed": 3.0,
            "church": 20.0, "cathedral": 25.0}.get(kind, 9.0)


def convert(roads_path, buildings_path, nature_path, out_path):
    features = []

    for el in json.load(open(roads_path))["elements"]:
        pts = _coords(el)
        if len(pts) < 2:
            continue
        highway = el.get("tags", {}).get("highway", "")
        features.append({
            "type": "Feature",
            "properties": {"kind": "road_major" if highway in MAJOR_ROADS
                           else "road"},
            "geometry": {"type": "LineString", "coordinates": pts}})

    for el in json.load(open(buildings_path))["elements"]:
        pts = _coords(el)
        if len(pts) < 4 or pts[0] != pts[-1]:
            continue
        features.append({
            "type": "Feature",
            "properties": {"kind": "building",
                           "h": _building_height(el.get("tags", {}))},
            "geometry": {"type": "Polygon", "coordinates": [pts]}})

    for el in json.load(open(nature_path))["elements"]:
        pts = _coords(el)
        if len(pts) < 4 or pts[0] != pts[-1]:
            continue
        tags = el.get("tags", {})
        kind = ("water" if tags.get("natural") == "water"
                or tags.get("waterway") == "riverbank" else "park")
        features.append({
            "type": "Feature",
            "properties": {"kind": kind},
            "geometry": {"type": "Polygon", "coordinates": [pts]}})

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f,
                  separators=(",", ":"), ensure_ascii=False)
    print(f"{out_path}: {len(features)} объектов")


if __name__ == "__main__":
    convert(*sys.argv[1:5])
