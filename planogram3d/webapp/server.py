"""Локальный сервер сети магазинов: карта города + 3D-планограммы.

Запуск::

    pip install flask
    python -m planogram3d.webapp            # http://127.0.0.1:8050

Маршруты:

* ``/``               — карта сети магазинов (2D/3D, живая эмуляция);
* ``/store/<id>``     — интерактивная 3D-планограмма магазина;
* ``/api/state``      — JSON с текущим состоянием сети (для карты);
* ``/static/...``     — MapLibre, данные карты города.
"""

import argparse

from flask import Flask, abort, jsonify, render_template, request

from ..core import build_report_page, check_compliance
from .instore import InstoreHub
from .network import StoreNetwork
from .zabbix import create_provider

app = Flask(__name__)
network = StoreNetwork()
zabbix, zabbix_mode = create_provider(list(network.stores))
instore = InstoreHub()


@app.get("/")
def index():
    return render_template("map.html")


@app.get("/api/state")
def api_state():
    state = network.state()
    state["zabbix_mode"] = zabbix_mode
    try:
        problems = zabbix.problems()
    except Exception as exc:            # Zabbix недоступен — карта живёт
        app.logger.warning("Zabbix недоступен: %s", exc)
        problems = {}
    for s in state["stores"]:
        s["zabbix"] = problems.get(
            s["id"], {"active": 0, "worst": 0, "problems": []})
    state["totals"]["zabbix_active"] = sum(
        s["zabbix"]["active"] for s in state["stores"])
    return jsonify(state)


@app.get("/store/<store_id>")
def store_page(store_id):
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    violations = check_compliance(store)
    return build_report_page(store, violations)


@app.get("/store/<store_id>/live")
def store_live(store_id):
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    return render_template("instore.html", store_id=store_id,
                           store_name=store.name)


@app.get("/store/<store_id>/game")
def store_game(store_id):
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    return render_template("game.html", store_id=store_id,
                           store_name=store.name)


@app.get("/api/game/<store_id>/config")
def game_config(store_id):
    """Конфигурация игры-тренажёра: реальный зал и товары магазина."""
    from .instore import ENTRANCE, EXIT, FRIDGES, POS_DESKS, SCO_RECT
    from .network import price_for
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    gondolas = []
    for g in store.gondolas:
        products = []
        for p in store.current_planogram.by_gondola(g.gondola_id):
            product = store.product(p.sku)
            products.append({"sku": p.sku, "name": product.name,
                             "price": round(price_for(product.category,
                                                      p.sku))})
        gondolas.append({"x": g.x, "y": g.y, "w": g.width, "d": g.depth,
                         "name": g.name.split("(")[0].strip(),
                         "products": products})
    return jsonify({
        "store_name": store.name,
        "gondolas": gondolas,
        "fridges": [{"id": fid, "x": x, "y": y, "w": w, "d": d}
                    for fid, x, y, w, d in FRIDGES],
        "register": {"name": POS_DESKS[0][0], "x": POS_DESKS[0][1],
                     "y": POS_DESKS[0][2]},
        "sco": SCO_RECT,
        "entrance": ENTRANCE, "exit": EXIT,
        "storeroom": {"x": 6.6, "y": -0.15},
    })


@app.get("/api/instore/<store_id>/state")
def instore_state(store_id):
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    after = request.args.get("after", 0, type=int)
    return jsonify(instore.get(store_id, store).state(after_id=after))


@app.post("/api/instore/<store_id>/ingest")
def instore_ingest(store_id):
    """Приём реального потока событий: кассы, весы, СКО, видеоаналитика."""
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    payload = request.get_json(silent=True) or {}
    accepted = instore.get(store_id, store).ingest(
        payload.get("events", []))
    return jsonify({"accepted": accepted})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="planogram3d.webapp",
        description="Локальный сервер: карта сети магазинов (2D/3D) "
                    "с эмуляцией продаж и 3D-планограммами.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args(argv)

    network.start()
    print(f"Сеть магазинов: {len(network.stores)} точек, эмуляция запущена")
    print("Мониторинг Zabbix: "
          + ("реальный сервер " + str(getattr(zabbix, 'api_url', ''))
             if zabbix_mode == "zabbix" else
             "эмуляция (задайте ZABBIX_URL и ZABBIX_TOKEN для реального)"))
    print(f"Карта: http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
