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
from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template,
                   request, send_file)

from ..core import build_report_page, check_compliance
from .delivery import DeliveryHub
from .instore import InstoreHub
from .multigame import MultiHub
from .network import StoreNetwork
from .roblox import TeamHub
from .zabbix import create_provider

app = Flask(__name__)
network = StoreNetwork()
zabbix, zabbix_mode = create_provider(list(network.stores))
instore = InstoreHub()
team = TeamHub()
delivery = DeliveryHub(network)
mgames = MultiHub(network)


@app.get("/delivery")
def delivery_page():
    return render_template("delivery.html")


@app.get("/api/delivery/state")
def delivery_state():
    return jsonify(delivery.state())


@app.post("/api/delivery/gps")
def delivery_gps():
    """Телеметрия курьерского приложения: GPS-координаты, батарея."""
    d = request.get_json(silent=True) or {}
    ok = delivery.ingest_gps(d.get("courier", ""),
                             d.get("lat"), d.get("lon"),
                             d.get("battery"))
    return jsonify({"accepted": bool(ok)})


@app.get("/receipt/<receipt_id>")
def receipt_page(receipt_id):
    r = delivery.receipt(receipt_id)
    if r is None:
        abort(404)
    return render_template("receipt.html", r=r)


@app.post("/api/roblox/register")
def roblox_register():
    """Регистрация члена команды: имя + ник в Roblox + магазин."""
    d = request.get_json(silent=True) or {}
    if not d.get("roblox_user"):
        abort(400)
    return jsonify(team.register(d.get("name", ""), d["roblox_user"],
                                 d.get("store_id", "")))


@app.get("/api/roblox/team")
def roblox_team():
    """Команда: лидерборд по баллам и лента поощрений."""
    return jsonify(team.team())


@app.post("/api/roblox/progress")
def roblox_progress():
    """Результат смены тренажёра → бонусы, бейджи, объявление в Roblox."""
    d = request.get_json(silent=True) or {}
    if not d.get("roblox_user"):
        abort(400)
    return jsonify(team.progress(
        d.get("name", ""), d["roblox_user"], d.get("store_id", ""),
        int(d.get("level", 1)), int(d.get("stars", 0)),
        int(d.get("revenue", 0)), d.get("stats", {})))


@app.get("/")
def index():
    return render_template("map.html")


# ----- презентация, документация, команда -------------------------------
_PKG_ROOT = Path(__file__).resolve().parent.parent
_DOCS = {
    "readme": ("README.md", "О модуле"),
    "erp3d": ("docs/ARTICLE_3D_ERP.md", "3D для ERP"),
    "library": ("docs/LIBRARY.md", "Справочник API"),
    "integration": ("docs/INTEGRATION.md", "Интеграция"),
    "article": ("docs/ARTICLE_TEAM_TRAINING.md", "Методичка"),
    "roadmap": ("docs/ROADMAP_AI_WORKFORCE.md", "Роадмап ИИ"),
    "plan": ("docs/PRESENTATION_PLAN.md", "План презентации"),
    "handoff": ("docs/HANDOFF.md", "База знаний"),
}
#: ссылки по имени файла (из markdown-документов) → ключ страницы
_DOC_FILES = {path.split("/")[-1]: key
              for key, (path, _) in _DOCS.items()}


@app.get("/presentation")
def presentation():
    """HTML-презентация модуля с живыми ссылками в демо-систему."""
    return render_template("presentation.html")


@app.get("/docs/")
def docs_index():
    return redirect("/docs/readme")


@app.get("/docs/presentation.pptx")
def docs_pptx():
    return send_file(_PKG_ROOT / "docs" / "presentation.pptx",
                     as_attachment=True,
                     download_name="planogram3d_presentation.pptx")


@app.get("/docs/article.html")
def docs_article_html():
    """HTML-версия статьи о методике (со встроенным Markdown-исходником)."""
    return send_file(_PKG_ROOT / "docs" / "ARTICLE_TEAM_TRAINING.html")


@app.get("/docs/img/<name>")
def docs_img(name):
    """Иллюстрации документации (скриншоты системы)."""
    path = (_PKG_ROOT / "docs" / "img" / name).resolve()
    if (path.parent != (_PKG_ROOT / "docs" / "img").resolve()
            or not path.exists()):
        abort(404)
    return send_file(path)


@app.get("/docs/<name>")
def docs_page(name):
    from .mdview import md_to_html
    if name in _DOC_FILES:           # ссылка по имени .md-файла
        name = _DOC_FILES[name]
    if name not in _DOCS:
        abort(404)
    path, title = _DOCS[name]
    md = (_PKG_ROOT / path).read_text(encoding="utf-8")
    return render_template(
        "docs.html", title=title, current=name,
        nav=[(k, t) for k, (_, t) in _DOCS.items()],
        content=md_to_html(md))


@app.get("/team")
def team_page():
    data = team.team()
    return render_template("team.html", mode=data["mode"],
                           members=data["members"], feed=data["feed"])


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


@app.get("/store/<store_id>/game/multi")
def store_game_multi(store_id):
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    return render_template("game_multi.html", store_id=store_id,
                           store_name=store.name)


@app.post("/api/mgame/<store_id>/<code>/join")
def mgame_join(store_id, code):
    """Подключение игрока (человек / внешний ИИ) к командной смене."""
    d = request.get_json(silent=True) or {}
    try:
        game = mgames.get(store_id, code)
    except KeyError:
        abort(404)
    return jsonify(game.join(d.get("name", ""), d.get("role", ""),
                             d.get("kind", "human"),
                             d.get("roblox_user", "")))


@app.post("/api/mgame/<store_id>/<code>/bot")
def mgame_bot(store_id, code):
    """Добавить встроенного ИИ-бота указанной роли."""
    d = request.get_json(silent=True) or {}
    game = mgames.get(store_id, code)
    role = d.get("role", "merch")
    names = {"cashier": "ИИ-Кассир", "merch": "ИИ-Мерч",
             "cleaner": "ИИ-Клинер", "tech": "ИИ-Техник",
             "supervisor": "ИИ-Супервайзер"}
    return jsonify(game.join(names.get(role, "ИИ-Бот"), role, "bot"))


@app.post("/api/mgame/<store_id>/<code>/start")
def mgame_start(store_id, code):
    game = mgames.get(store_id, code)
    game.start()
    return jsonify({"ok": True})


@app.post("/api/mgame/<store_id>/<code>/action")
def mgame_action(store_id, code):
    """Действие игрока: люди из браузера и внешние ИИ по API."""
    d = request.get_json(silent=True) or {}
    game = mgames.get(store_id, code)
    return jsonify(game.action(d.get("player", ""), d.get("action", ""),
                               d.get("x"), d.get("y"), d.get("target")))


@app.get("/api/mgame/<store_id>/<code>/state")
def mgame_state(store_id, code):
    game = mgames.get(store_id, code)
    return jsonify(game.state(request.args.get("player", ""),
                              request.args.get("after", 0, type=int)))


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
