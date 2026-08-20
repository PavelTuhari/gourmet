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
from .i18n import client_catalog, client_plural_forms, normalize_lang, t
from .instore import InstoreHub
from .multigame import MultiHub
from .network import StoreNetwork
from .peco_fuel import ARTGRANIT_BASE_URL, FuelNetwork
from .roblox import TeamHub
from .zabbix import create_provider

app = Flask(__name__)
# доступ к переводу прямо из Jinja ({{ t(lang, 'key') }}) — без ручного
# протаскивания словаря подписей в каждый render_template
app.jinja_env.globals["t"] = t
network = StoreNetwork()
zabbix, zabbix_mode = create_provider(list(network.stores))
instore = InstoreHub()
team = TeamHub()
delivery = DeliveryHub(network)
mgames = MultiHub(network)
fuel = FuelNetwork()          # контур топлива — своя карта (Молдова), свой граф


def _lang() -> str:
    """Язык интерфейса из ``?lang=ru|ro|en``.

    Сознательно без чтения ``Accept-Language``: система — демо-стенд
    (см. `docs/HANDOFF.md`), выбор языка явный и повторяемый по ссылке
    (важно для скриншотов/проверок на всех трёх языках), а автоопределение
    добавило бы источник несовпадения между тем, что видит проверяющий,
    и тем, что видит браузер пользователя — без реальной пользы на этом
    этапе. Неизвестный/отсутствующий код молча откатывается на 'ru'.
    """
    return normalize_lang(request.args.get("lang"))


#: ключи каталога для JS страницы /delivery (панели рисуются в браузере
#: по данным опроса /api/delivery/state — событийный текст сервер уже
#: собирает переведённым, здесь только статические подписи-хелперы)
_DELIVERY_JS_KEYS = (
    "delivery.routes.empty", "delivery.routes.addresses",
    "delivery.gantt.empty", "delivery.receipts.empty",
    "delivery.eta.ai_badge", "delivery.stop.tooltip",
    "delivery.ai_arrival", "eta.this_point", "eta.plan_short",
    "eta.courier_assigning", "eta.board_title", "eta.order_status_prefix",
    "unit.sec_short",
)


@app.get("/delivery")
def delivery_page():
    lang = _lang()
    return render_template("delivery.html", lang=lang,
                           i18n_json=client_catalog(lang, _DELIVERY_JS_KEYS))


@app.get("/api/delivery/state")
def delivery_state():
    return jsonify(delivery.state(_lang()))


@app.post("/api/delivery/gps")
def delivery_gps():
    """Телеметрия курьерского приложения: GPS-координаты, батарея."""
    d = request.get_json(silent=True) or {}
    ok = delivery.ingest_gps(d.get("courier", ""),
                             d.get("lat"), d.get("lon"),
                             d.get("battery"))
    return jsonify({"accepted": bool(ok)})


@app.get("/api/eta/store/<store_id>")
def eta_store(store_id):
    """Онлайн-табло пункта доставки (магазина): ИИ-прогноз прибытия
    машин поставщиков и РЦ — по аналогии с «умными остановками»
    городского транспорта (GPS-телеметрия → ИИ-модель → табло)."""
    try:
        return jsonify(network.arrival_board(store_id, _lang()))
    except KeyError:
        abort(404)


@app.get("/api/eta/order/<order_id>")
def eta_order(order_id):
    """Онлайн-табло пункта доставки (адреса покупателя): ИИ-прогноз
    прибытия курьера с неопределённостью ±σ и позицией в очереди."""
    board = delivery.arrival_board(order_id, _lang())
    if board is None:
        abort(404)
    return jsonify(board)


#: ключи каталога для JS страницы /fuel — панель и попап табло рисуются в
#: браузере (см. `_DELIVERY_JS_KEYS`: статику шаблон берёт через Jinja,
#: здесь только то, что собирается динамически в poll())
_FUEL_JS_KEYS = (
    "gps.emulated", "eta.board_title", "delivery.eta.ai_badge",
    "fuel.eta.none", "fuel.eta.source_prefix", "eta.plan_short",
    "unit.sec_short", "unit.liters_short", "fuel.trip.done",
    "fuel.trip.enroute", "fuel.trips.empty", "fuel.runs.empty",
    "fuel.station.tooltip", "fuel.tanker.tooltip",
)


@app.get("/fuel")
def fuel_page():
    """Карта топливной сети Молдовы: нефтебаза, АЗС, рейсы бензовозов."""
    lang = _lang()
    erp_url = f"{ARTGRANIT_BASE_URL}/UNA.md/orasldev/planograms#fuel"
    return render_template("fuel.html", lang=lang, erp_url=erp_url,
                           i18n_json=client_catalog(lang, _FUEL_JS_KEYS))


@app.get("/api/fuel/state")
def api_fuel_state():
    return jsonify(fuel.state(_lang()))


@app.get("/api/eta/fuel/<station_id>")
def eta_fuel(station_id):
    """Онлайн-табло прибытия АЗС: бензовозы в пути к ней, ИИ-прогноз
    (±σ) — тот же контракт, что у /api/eta/store и /api/eta/order, чтобы
    фронтенд табло переиспользовался без переписывания."""
    board = fuel.arrival_board(station_id, _lang())
    if board is None:
        abort(404)
    return jsonify(board)


#: ключи каталога, нужные клиентскому JS чека (кнопка печати) — доказательство
#: механизма из части 1 ТЗ; полный перевод ~270 строк JS других шаблонов —
#: следующий этап, здесь достаточно, что путь "сервер → JSON → JS" работает.
_RECEIPT_JS_KEYS = ("receipt.print_button",)


@app.get("/receipt/<receipt_id>")
def receipt_page(receipt_id):
    r = delivery.receipt(receipt_id)
    if r is None:
        abort(404)
    lang = _lang()
    labels = {key.split(".", 1)[1]: t(lang, key) for key in (
        "receipt.header_title", "receipt.company_line2", "receipt.idno",
        "receipt.subdivision_address", "receipt.ecc_serial",
        "receipt.ecc_reg", "receipt.receipt_no", "receipt.order",
        "receipt.route", "receipt.customer", "receipt.deliver_address",
        "receipt.courier", "receipt.register", "receipt.subtotal_no_vat",
        "receipt.total", "receipt.cashless", "receipt.thanks",
        "receipt.print_button")}
    # печать чека — единственный источник фразы print_way (см. delivery.py:
    # _fiscal_receipt формирует его ключом, а не готовой строкой), поэтому
    # лента событий и чек не могут разойтись в формулировке
    print_way = t(lang, f"receipt.print_way.{r['app']}")
    # тип кассы приходит из модели строкой по-русски; на чеке это подпись,
    # а не данные, поэтому переводим здесь, а не храним три варианта в чеке
    app_title = t(lang, f"receipt.app.{r['app']}")
    vat_lines = [{
        "rate": v["rate"],
        "label": t(lang, "receipt.vat_total_at_rate", rate=v["rate"]),
        "base": v["base"], "vat": v["vat"],
    } for v in r["vat_breakdown"]]
    # адрес подразделения: в модели сети нет отдельного поля "улица" —
    # название магазина уже несёт локацию ("«Гурман» №17 · Штефан чел
    # Маре"), не переводим его (решение владельца — данные как есть),
    # только город перед ним
    subdivision_address = f"{t(lang, 'city.chisinau')}, {r['store_name']}"
    return render_template(
        "receipt.html", r=r, lang=lang, lbl=labels, print_way=print_way,
        app_title=app_title,
        vat_lines=vat_lines, subdivision_address=subdivision_address,
        i18n_json=client_catalog(lang, _RECEIPT_JS_KEYS))


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
    return jsonify(team.team(_lang()))


@app.post("/api/roblox/progress")
def roblox_progress():
    """Результат смены тренажёра → бонусы, бейджи, объявление в Roblox."""
    d = request.get_json(silent=True) or {}
    if not d.get("roblox_user"):
        abort(400)
    return jsonify(team.progress(
        d.get("name", ""), d["roblox_user"], d.get("store_id", ""),
        int(d.get("level", 1)), int(d.get("stars", 0)),
        int(d.get("revenue", 0)), d.get("stats", {}), lang=_lang()))


#: ключи каталога, нужные JS карты (табло прибытия, карточки, счётчики —
#: те части интерфейса, что рисуются в браузере после /api/state, а не
#: на сервере при первом рендере страницы)
_MAP_JS_KEYS = (
    "map.kpi.zabbix_active", "map.kpi.zabbix_emulation",
    "map.card.empty_shelves", "map.zabbix.head", "map.zabbix.none",
    "map.eta.head", "map.eta.none", "map.eta.telemetry_note",
    "map.plan_short", "map.interior.status_line",
    "map.interior.zabbix_active", "map.interior.zabbix_none",
    "map.dc.supplier_line", "unit.sec_short", "unit.min_short",
    "unit.hour_short", "unit.pcs_short",
)
_MAP_JS_PLURAL_KEYS = ("map.zabbix.head.problems_word",)


@app.get("/")
def index():
    lang = _lang()
    return render_template(
        "map.html", lang=lang,
        i18n_json=client_catalog(lang, _MAP_JS_KEYS),
        i18n_plural_json=client_plural_forms(lang, _MAP_JS_PLURAL_KEYS))


# ----- презентация, документация, команда -------------------------------
_PKG_ROOT = Path(__file__).resolve().parent.parent
#: заголовки навигации — ключи каталога i18n, а не готовый текст: сами
#: документы (docs/*.md) не переводятся (решение владельца, см. задачу),
#: но название пункта меню — элемент интерфейса и переводится как обычно.
_DOCS = {
    "readme": ("README.md", "docs.nav.readme"),
    "tz": ("docs/TZ.md", "docs.nav.tz"),
    "erp3d": ("docs/ARTICLE_3D_ERP.md", "docs.nav.erp3d"),
    "library": ("docs/LIBRARY.md", "docs.nav.library"),
    "integration": ("docs/INTEGRATION.md", "docs.nav.integration"),
    "article": ("docs/ARTICLE_TEAM_TRAINING.md", "docs.nav.article"),
    "roadmap": ("docs/ROADMAP_AI_WORKFORCE.md", "docs.nav.roadmap"),
    "plan": ("docs/PRESENTATION_PLAN.md", "docs.nav.plan"),
    "handoff": ("docs/HANDOFF.md", "docs.nav.handoff"),
}
#: ссылки по имени файла (из markdown-документов) → ключ страницы
_DOC_FILES = {path.split("/")[-1]: key
              for key, (path, _) in _DOCS.items()}


@app.get("/presentation")
def presentation():
    """HTML-презентация модуля с живыми ссылками в демо-систему."""
    return render_template("presentation.html")


@app.get("/presentation2")
def presentation2():
    """Новая трёхъязычная презентация (Кишинёв + топливный контур,
    ИИ-табло, bon fiscal) — рядом со старой /presentation, которая не
    трогается (см. docs/HANDOFF.md и задачу владельца)."""
    return render_template("presentation2.html", lang=_lang())


@app.get("/docs/")
def docs_index():
    return redirect("/docs/readme")


@app.get("/docs/presentation.pptx")
def docs_pptx():
    return send_file(_PKG_ROOT / "docs" / "presentation.pptx",
                     as_attachment=True,
                     download_name="planogram3d_presentation.pptx")


@app.get("/docs/presentation_md.pptx")
def docs_pptx_md():
    """Новая презентация (RO, Кишинёв + топливный контур) — отдельный
    файл, старый presentation.pptx не затрагивается."""
    return send_file(_PKG_ROOT / "docs" / "presentation_md.pptx",
                     as_attachment=True,
                     download_name="planogram3d_presentation_md.pptx")


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
    path, title_key = _DOCS[name]
    lang = _lang()
    md = (_PKG_ROOT / path).read_text(encoding="utf-8")
    return render_template(
        "docs.html", title=t(lang, title_key), current=name, lang=lang,
        nav=[(k, t(lang, title_key2)) for k, (_, title_key2) in _DOCS.items()],
        content=md_to_html(md))


@app.get("/team")
def team_page():
    lang = _lang()
    data = team.team(lang)
    return render_template("team.html", mode=data["mode"], lang=lang,
                           members=data["members"], feed=data["feed"])


@app.get("/api/state")
def api_state():
    state = network.state(_lang())
    state["zabbix_mode"] = zabbix_mode
    try:
        problems = zabbix.problems(_lang())
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
    lang = _lang()
    violations = check_compliance(store, lang=lang)
    return build_report_page(store, violations, lang=lang)


#: ключи каталога для JS страницы /store/<id>/live — канвас (изометрия
#: зала), лента событий и режим потока рисуются в браузере
_INSTORE_JS_KEYS = (
    "instore.mode.test", "instore.mode.real", "instore.est.text",
    "instore.label.bags", "instore.label.sco", "instore.label.scales",
    "instore.label.entrance", "instore.label.exit",
    "instore.queue.label", "instore.queue.sco_label",
    "instore.fridge.door_open", "instore.fridge.alarm",
    "instore.event.cam_in", "instore.event.cam_out", "instore.event.pick",
    "instore.event.scale", "instore.event.sco_in", "instore.event.sco_out",
    "instore.event.pos", "instore.event.fridge_alarm",
    "instore.event.source_real", "instore.event.source_test",
    "unit.meters_short", "unit.kg_short",
)


@app.get("/store/<store_id>/live")
def store_live(store_id):
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    lang = _lang()
    return render_template(
        "instore.html", store_id=store_id, store_name=store.name, lang=lang,
        i18n_json=client_catalog(lang, _INSTORE_JS_KEYS))


#: ключи каталога для JS страницы /store/<id>/game (тренажёр-соло):
#: конфигурация уровней, брифинг, подсказки-туториал, попапы и итоги
#: смены нарисованы в браузере (LEVELS/TUTOR — статичная конфигурация
#: игры, не данные опроса, см. комментарий у ключей "game.*" в i18n.py)
_GAME_JS_KEYS = (
    "game.brief.goal", "unit.min_short",
    "game.level1.title", "game.level1.brief1", "game.level1.brief2",
    "game.level1.brief3", "game.level2.title", "game.level2.brief1",
    "game.level2.brief2", "game.level2.brief3", "game.level3.title",
    "game.level3.brief1", "game.level3.brief2", "game.level3.brief3",
    "game.result.title_ok", "game.result.title_fail",
    "game.result.stat.revenue_label", "game.result.revenue_value",
    "game.result.stat.served", "game.result.stat.lost",
    "game.result.stat.restocks", "game.result.stat.cleaned",
    "game.result.stat.papers_fridges", "game.result.stat.reputation",
    "game.tip.lost", "game.tip.restocks", "game.tip.reputation",
    "game.tip.great", "team.mode.roblox", "team.mode.emulation",
    "game.rbx.total_label", "game.rbx.new_badge_label",
    "game.rbx.top_team_label", "game.rbx.no_roblox",
    "game.result.next_btn", "game.result.done_btn",
    "game.result.retry_btn", "game.tutor.1", "game.tutor.2",
    "game.tutor.3", "game.tutor.4", "game.hint.no_paper",
    "game.hint.replace_paper", "game.hint.queue_status",
    "game.hint.need_stock", "game.busy.storeroom", "game.busy.shelf",
    "game.busy.paper", "game.busy.mess", "game.busy.fridge",
    "game.popup.item_added", "game.popup.clean",
    "game.popup.fridge_fixed", "game.popup.paper_replaced",
    "game.popup.mess", "game.popup.fridge_alarm", "game.label.storeroom",
    "game.label.no_paper", "game.default_name",
    "instore.label.entrance", "instore.label.exit", "instore.label.fridge_n",
    "receipt.register",
)
_GAME_JS_PLURAL_KEYS = ("game.rbx.points_word",)


@app.get("/store/<store_id>/game")
def store_game(store_id):
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    lang = _lang()
    return render_template(
        "game.html", store_id=store_id, store_name=store.name, lang=lang,
        i18n_json=client_catalog(lang, _GAME_JS_KEYS),
        i18n_plural_json=client_plural_forms(lang, _GAME_JS_PLURAL_KEYS))


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


#: ключи каталога для JS страницы /store/<id>/game/multi (командная
#: смена): лобби, ростер, табличка итогов и лента событий рисуются в
#: браузере по данным опроса /api/mgame/.../state — тот роут не входит
#: в эту задачу, поэтому события там хранятся как ключ+параметры и
#: рендерятся здесь же, в браузере, через tt()/ttn() по каталогу,
#: загруженному один раз при открытии страницы (см. комментарий у
#: ключей "mgame.*" в i18n.py)
_GAME_MULTI_JS_KEYS = (
    "mgame.lobby.free_label", "mgame.lobby.room_line", "mgame.api_hint",
    "mgame.lobby.roster_label", "mgame.lobby.empty", "mgame.ai_suffix",
    "mgame.table.player", "mgame.table.role", "receipt.register",
    "mgame.table.shelves", "mgame.table.cleaning", "mgame.table.tech",
    "mgame.table.points", "mgame.result.title_ok", "game.result.title_fail",
    "mgame.status.play", "mgame.status.ended", "mgame.status.lobby",
    "mgame.you_suffix", "mgame.join_error_prefix", "mgame.joined_label",
    "mgame.label.sco_self", "mgame.role.cashier", "mgame.role.merch",
    "mgame.role.cleaner", "mgame.role.tech", "mgame.role.supervisor",
    "mgame.event.joined", "mgame.event.left", "mgame.event.started",
    "mgame.event.disconnected", "mgame.event.fridge_alarm",
    "mgame.event.finished_ok", "mgame.event.finished_fail",
    "mgame.fx.need_stock", "game.busy.storeroom", "game.busy.shelf",
    "game.busy.paper", "game.busy.mess", "game.busy.fridge",
    "game.popup.item_added", "game.popup.clean", "game.popup.fridge_fixed",
    "game.popup.paper_replaced", "game.popup.mess", "game.label.storeroom",
    "game.label.no_paper", "instore.label.scales", "instore.label.fridge_n",
    "delivery.eta.ai_badge", "delivery.side.events",
)
_GAME_MULTI_JS_PLURAL_KEYS = (
    "mgame.role.cashier_word", "mgame.role.merch_word",
    "mgame.role.cleaner_word", "mgame.role.tech_word",
    "mgame.role.supervisor_word", "mgame.event.started.team_word",
)


@app.get("/store/<store_id>/game/multi")
def store_game_multi(store_id):
    try:
        store = network.store(store_id)
    except KeyError:
        abort(404)
    lang = _lang()
    return render_template(
        "game_multi.html", store_id=store_id, store_name=store.name,
        lang=lang, i18n_json=client_catalog(lang, _GAME_MULTI_JS_KEYS),
        i18n_plural_json=client_plural_forms(
            lang, _GAME_MULTI_JS_PLURAL_KEYS))


@app.post("/api/mgame/<store_id>/<code>/join")
def mgame_join(store_id, code):
    """Подключение игрока (человек / внешний ИИ) к командной смене."""
    d = request.get_json(silent=True) or {}
    try:
        game = mgames.get(store_id, code)
    except KeyError:
        abort(404)
    # имя по умолчанию — на языке запроса; браузер сам подставляет
    # tt("game.default_name") до отправки, так что сюда попадают только
    # внешние ИИ-агенты, не указавшие имя явно
    name = d.get("name") or t(_lang(), "game.default_name")
    return jsonify(game.join(name, d.get("role", ""),
                             d.get("kind", "human"),
                             d.get("roblox_user", "")))


@app.post("/api/mgame/<store_id>/<code>/bot")
def mgame_bot(store_id, code):
    """Добавить встроенного ИИ-бота указанной роли."""
    d = request.get_json(silent=True) or {}
    game = mgames.get(store_id, code)
    role = d.get("role", "merch")
    lang = _lang()
    names = {"cashier": t(lang, "game.bot.cashier"),
             "merch": t(lang, "game.bot.merch"),
             "cleaner": t(lang, "game.bot.cleaner"),
             "tech": t(lang, "game.bot.tech"),
             "supervisor": t(lang, "game.bot.supervisor")}
    return jsonify(game.join(
        names.get(role, t(lang, "game.bot.default")), role, "bot"))


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
    return jsonify(instore.get(store_id, store).state(after_id=after,
                                                       lang=_lang()))


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
