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

from flask import Flask, abort, jsonify, render_template

from ..core import build_report_page, check_compliance
from .network import StoreNetwork
from .zabbix import create_provider

app = Flask(__name__)
network = StoreNetwork()
zabbix, zabbix_mode = create_provider(list(network.stores))


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
