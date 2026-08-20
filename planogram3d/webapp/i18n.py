"""Локализация интерфейса: каталог сообщений на ru/ro/en и подстановка
множественного числа.

Почему свой велосипед, а не ``gettext``/Babel: в проекте сознательно нет
внешних зависимостей (см. `docs/HANDOFF.md` §3.8 — мини-Markdown вместо
библиотеки; тот же принцип держим здесь) и нет сборки .po/.mo под CI.
Каталог — обычный dict в питоне, грепается и пополняется без тулчейна;
это важно, потому что следующие этапы добавят сюда сотни ключей
(планограмма, тренажёр, топливный контур).

Контракт нормализации языка — тот же, что у прочих нормализаторов
проекта (например, id магазина/роли): неизвестное/пустое значение тихо
откатывается на дефолт, а не роняет запрос.
"""

from typing import Dict, Optional, Sequence, Union

LANGS = ("ru", "ro", "en")
DEFAULT_LANG = "ru"

#: значение ключа в MESSAGES — либо одна строка на язык (без числа),
#: либо список форм множественного числа на язык (индекс — из _PLURAL_FUNCS)
_Entry = Union[str, Sequence[str]]


def normalize_lang(code: Optional[str]) -> str:
    """Приводит код языка к одному из поддерживаемых, иначе — 'ru'."""
    code = (code or "").strip().lower()[:2]
    return code if code in LANGS else DEFAULT_LANG


# ----- выбор формы множественного числа по количеству -----------------------
#
# Функция возвращает индекс формы в списке MESSAGES[key][lang].
# Формы перечисляются от «наименьшей» к «наибольшей»: это позволяет
# держать разное число форм для разных языков в одном месте, без
# костылей вида "рейс(ов)"/"заказ(а)", раскиданных по коду сценариев.

def _plural_ru(n: int) -> int:
    """Русский: 3 формы — 1/21/101 (один), 2-4/22-24 (два-четыре),
    остальное (пять и далее, а также 11-14 — особая «сотня» подряд)."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return 0                                   # заказ, рейс
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return 1                                   # заказа, рейса
    return 2                                        # заказов, рейсов


def _plural_ro(n: int) -> int:
    """Румынский: 3 формы (CLDR one/few/other), а не две.

    Ошибиться здесь легко и заметно носителю: «2 cursă» вместо «2 curse»
    выглядит так же неграмотно, как «2 рейс» по-русски. Правило:

    * 0 — ровно 1 («o cursă»);
    * 1 — few: ноль и всё, что по модулю 100 попадает в 1..19, кроме самой
      единицы («2 curse», «19 curse», «101 curse»);
    * 2 — other: остальное, и здесь румынский требует предлога «de»
      («20 de curse»), поэтому это отдельная форма, а не та же, что few.
    """
    n = abs(int(n))
    if n == 1:
        return 0                                   # o cursă
    if n == 0 or 1 <= (n % 100) <= 19:
        return 1                                   # 2..19, 101..119 curse
    return 2                                        # 20 de curse, 100 de curse


def _plural_en(n: int) -> int:
    """Английский: 2 формы — единственное/множественное, как обычно."""
    return 0 if abs(int(n)) == 1 else 1


_PLURAL_FUNCS = {"ru": _plural_ru, "ro": _plural_ro, "en": _plural_en}


# ----- каталог сообщений -----------------------------------------------------
#
# Ключи группируются по разделу интерфейса через точку в имени
# ("receipt.total", "log.route_built"), чтобы пополнение оставалось
# читаемым по мере роста каталога. Эмодзи в значениях не хранится —
# он не нуждается в переводе и на трёх языках выглядит одинаково;
# эмодзи добавляется в шаблоне/коде рядом с результатом t(...).
#
# Плейсхолдеры — obычный str.format: {name}, {n} и т.д.

MESSAGES: Dict[str, Dict[str, _Entry]] = {
    # ---- общее ----
    # заголовки вкладок браузера — тоже интерфейс: на румынской версии
    # русский <title> выглядит недоделкой, особенно в списке вкладок
    "page.title.map": {
        "ru": "Сеть «Гурман» — карта магазинов",
        "ro": "Rețeaua «Gurman» — harta magazinelor",
        "en": "Gurman network — store map",
    },
    "page.title.delivery": {
        "ru": "Интернет-заказы и доставка — сеть «Гурман»",
        "ro": "Comenzi online și livrare — rețeaua «Gurman»",
        "en": "Online orders and delivery — Gurman network",
    },
    "page.title.team": {
        "ru": "Команда «Гурман» — баллы и поощрения",
        "ro": "Echipa «Gurman» — puncte și recompense",
        "en": "Gurman team — points and rewards",
    },
    # ---- журнал задач автозаказа топлива ----
    # Зритель должен видеть не «мало топлива», а заведённую задачу с
    # ответственными и стадией — формулировки деловые, как в наряде.
    "fuel.task.stage.placed": {
        "ru": "заказ размещён, ждёт машину",
        "ro": "comandă plasată, așteaptă cisterna",
        "en": "order placed, awaiting a truck",
    },
    "fuel.task.stage.assigned": {
        "ru": "назначен рейс, выезд",
        "ro": "cursă atribuită, pornește",
        "en": "trip assigned, departing",
    },
    "fuel.task.stage.en_route": {
        "ru": "машина в пути",
        "ro": "cisterna este pe drum",
        "en": "truck en route",
    },
    "fuel.task.stage.unloading": {
        "ru": "идёт разгрузка",
        "ro": "se descarcă",
        "en": "unloading",
    },
    "fuel.task.stage.done": {
        "ru": "выполнена",
        "ro": "finalizată",
        "en": "completed",
    },
    "fuel.task.placed_by_auto": {
        "ru": "автозаказ (порог остатка)",
        "ro": "comandă automată (prag de stoc)",
        "en": "auto-order (stock threshold)",
    },
    "fuel.tasks.title": {
        "ru": "Задачи автозаказа",
        "ro": "Sarcini de comandă automată",
        "en": "Auto-order tasks",
    },
    "fuel.tasks.empty": {
        "ru": "активных задач нет",
        "ro": "nicio sarcină activă",
        "en": "no active tasks",
    },
    "fuel.task.assignee": {
        "ru": "назначено", "ro": "atribuit", "en": "assigned to",
    },
    "city.chisinau": {
        "ru": "Кишинёв", "ro": "Chișinău", "en": "Chisinau",
    },

    # ---- лента событий доставки (используется и в чеке — см. print_way.*) ----
    "log.route_built": {
        # {n} — число заказов в маршруте, {orders_word} — форма слова
        "ru": "Маршрут {route}: {n} {orders_word} из {store} → {courier} "
              "({app_title})",
        "ro": "Rută {route}: {n} {orders_word} de la {store} → {courier} "
              "({app_title})",
        "en": "Route {route}: {n} {orders_word} from {store} → {courier} "
              "({app_title})",
    },
    "log.route_built.orders_word": {
        "ru": ["заказ", "заказа", "заказов"],
        "ro": ["comandă", "comenzi", "de comenzi"],
        "en": ["order", "orders"],
    },

    # ---- фискальный чек (bon fiscal, HG 141/2019) ----
    "receipt.header_title": {
        "ru": "ФИСКАЛЬНЫЙ ЧЕК", "ro": "BON FISCAL", "en": "FISCAL RECEIPT",
    },
    "receipt.company_line2": {
        "ru": "Кишинёв, доставка интернет-заказов",
        "ro": "Chișinău, livrare comenzi online",
        "en": "Chisinau, online order delivery",
    },
    "receipt.idno": {
        "ru": "Фискальный код (IDNO)",
        "ro": "Cod fiscal (IDNO)",
        "en": "Tax code (IDNO)",
    },
    "receipt.subdivision_address": {
        "ru": "Адрес подразделения", "ro": "Adresa subdiviziunii",
        "en": "Subdivision address",
    },
    "receipt.ecc_serial": {
        "ru": "Заводской № ECC", "ro": "Nr. de fabricație ECC",
        "en": "ECC serial no.",
    },
    "receipt.ecc_reg": {
        "ru": "Рег. № ECC (SFS)", "ro": "Nr. de înregistrare ECC (SFS)",
        "en": "ECC registration no. (SFS)",
    },
    "receipt.receipt_no": {
        "ru": "№ чека", "ro": "Nr. bonului", "en": "Receipt no.",
    },
    "receipt.order": {"ru": "Заказ", "ro": "Comandă", "en": "Order"},
    "receipt.route": {"ru": "Маршрут", "ro": "Rută", "en": "Route"},
    "receipt.customer": {
        "ru": "Получатель", "ro": "Destinatar", "en": "Recipient",
    },
    "receipt.deliver_address": {
        "ru": "Адрес", "ro": "Adresă", "en": "Address",
    },
    "receipt.courier": {"ru": "Курьер", "ro": "Curier", "en": "Courier"},
    "receipt.register": {"ru": "Касса", "ro": "Casă", "en": "Register"},
    "receipt.vat_rate_short": {
        # рядом с ценой позиции: "TVA 20%" / "TVA 8%" — код+ставка вместе
        "ru": "ставка TVA {rate}%", "ro": "cota TVA {rate}%",
        "en": "VAT rate {rate}%",
    },
    "receipt.subtotal_no_vat": {
        "ru": "Сумма без TVA", "ro": "Suma fără TVA", "en": "Subtotal excl. VAT",
    },
    "receipt.vat_total_at_rate": {
        "ru": "Итого TVA {rate}%", "ro": "Total TVA {rate}%",
        "en": "Total VAT {rate}%",
    },
    "receipt.total": {"ru": "ИТОГО", "ro": "TOTAL", "en": "TOTAL"},
    "receipt.cashless": {
        "ru": "БЕЗНАЛИЧНЫМИ", "ro": "PLATĂ FĂRĂ NUMERAR", "en": "CARD PAYMENT",
    },
    "receipt.thanks": {
        "ru": "Спасибо за покупку!", "ro": "Vă mulțumim pentru cumpărătură!",
        "en": "Thank you for your purchase!",
    },
    "receipt.print_button": {
        "ru": "Печать чека", "ro": "Tipărire bon", "en": "Print receipt",
    },
    "receipt.print_way.smartpos": {
        "ru": "напечатан на терминале SmartOne (ECC на борту)",
        "ro": "tipărit la terminalul SmartOne (ECC la bord)",
        "en": "printed on the SmartOne terminal (onboard ECC)",
    },
    "receipt.print_way.android": {
        "ru": "фискализирован облачной кассой, электронный чек отправлен "
              "покупателю",
        "ro": "fiscalizat prin casa de marcat în cloud, bonul electronic "
              "a fost trimis cumpărătorului",
        "en": "fiscalized via the cloud register, the e-receipt was sent "
              "to the customer",
    },
    # Тип кассы курьера — подпись интерфейса, а не данные: печатается в чеке
    # («Касса: …») и показывается в карточке маршрута на /delivery, поэтому
    # переводится наравне с остальными подписями. Эмодзи держим в шаблоне
    # вывода, а не в переводимой строке.
    "receipt.app.android": {
        "ru": "Android (облачная касса)",
        "ro": "Android (casă de marcat în cloud)",
        "en": "Android (cloud register)",
    },
    "receipt.app.smartpos": {
        "ru": "SmartOne (ECC на борту)",
        "ro": "SmartOne (ECC la bord)",
        "en": "SmartOne (onboard ECC)",
    },

    # ---- лента событий сети магазинов (network.py) --------------------
    "log.dc_no_stock": {
        "ru": "Нет остатка «{name}» — {store} получит прямую поставку "
              "от поставщика",
        "ro": "Stoc epuizat «{name}» — {store} va primi livrare directă "
              "de la furnizor",
        "en": "No stock of «{name}» — {store} will get a direct "
              "delivery from the supplier",
    },
    "log.dc_shipment": {
        "ru": "Отгрузка в {store}: {name} × {qty}",
        "ro": "Expediere spre {store}: {name} × {qty}",
        "en": "Shipment to {store}: {name} × {qty}",
    },
    "log.dc_reorder": {
        "ru": "Заказ поставщику: {name} × {qty}",
        "ro": "Comandă către furnizor: {name} × {qty}",
        "en": "Order placed with supplier: {name} × {qty}",
    },
    "log.dc_supply_arrived": {
        "ru": "Приход от поставщика: {name} × {qty}",
        "ro": "Sosire de la furnizor: {name} × {qty}",
        "en": "Arrival from supplier: {name} × {qty}",
    },
    "log.shelf_empty": {
        "ru": "{name}: полка пуста, заказано пополнение",
        "ro": "{name}: raft gol, reaprovizionare comandată",
        "en": "{name}: shelf empty, restock ordered",
    },
    "log.out_of_stock": {
        "ru": "{name}: OUT-OF-STOCK",
        "ro": "{name}: OUT-OF-STOCK",
        "en": "{name}: OUT-OF-STOCK",
    },
    "log.shelf_restocked": {
        "ru": "{name}: полка пополнена (+{qty} шт.)",
        "ro": "{name}: raft reaprovizionat (+{qty} buc.)",
        "en": "{name}: shelf restocked (+{qty} pcs)",
    },

    # ---- лента событий доставки (delivery.py) --------------------------
    "log.new_order": {
        "ru": "Новый интернет-заказ {oid} → {store} ({n} {items_word}, "
              "{total} L)",
        "ro": "Comandă online nouă {oid} → {store} ({n} {items_word}, "
              "{total} L)",
        "en": "New online order {oid} → {store} ({n} {items_word}, "
              "{total} L)",
    },
    "log.new_order.items_word": {
        "ru": ["позиция", "позиции", "позиций"],
        "ro": ["produs", "produse", "de produse"],
        "en": ["item", "items"],
    },
    "log.picking_started": {
        "ru": "{oid}: сборщик приступил ({store})",
        "ro": "{oid}: pregătirea comenzii a început ({store})",
        "en": "{oid}: picker started ({store})",
    },
    "log.packed": {
        "ru": "{oid}: собран и упакован",
        "ro": "{oid}: pregătit și ambalat",
        "en": "{oid}: picked and packed",
    },
    "log.receipt_issued": {
        "ru": "Чек {rid} ({oid}, {total} L) — {print_way}",
        "ro": "Bon {rid} ({oid}, {total} L) — {print_way}",
        "en": "Receipt {rid} ({oid}, {total} L) — {print_way}",
    },
    "log.route_done": {
        "ru": "Маршрут {route} завершён ({courier})",
        "ro": "Ruta {route} finalizată ({courier})",
        "en": "Route {route} completed ({courier})",
    },
    "log.arrived": {
        "ru": "{route}: прибытие к {customer} ({address})",
        "ro": "{route}: sosire la {customer} ({address})",
        "en": "{route}: arrived at {customer} ({address})",
    },
    "status.new": {"ru": "новый", "ro": "nouă", "en": "new"},
    "status.picking": {"ru": "сборка", "ro": "în pregătire", "en": "picking"},
    "status.packed": {"ru": "собран", "ro": "ambalat", "en": "packed"},
    "status.routed": {
        "ru": "в доставке", "ro": "în livrare", "en": "delivering",
    },
    "status.delivered": {
        "ru": "доставлен", "ro": "livrat", "en": "delivered",
    },
    "gps.real": {
        "ru": "приложение (реальный GPS)",
        "ro": "aplicație (GPS real)",
        "en": "app (real GPS)",
    },
    "gps.emulated": {"ru": "эмуляция", "ro": "emulare", "en": "emulated"},
    "ai.handover_in_progress": {
        "ru": "курьер на точке, идёт вручение",
        "ro": "curierul e la punct, predarea în curs",
        "en": "courier on site, handing over",
    },
    "ai.model_trained": {
        "ru": "модель обучена ({n} {legs_word})",
        "ro": "model antrenat ({n} {legs_word})",
        "en": "model trained ({n} {legs_word})",
    },
    "ai.model_trained.legs_word": {
        "ru": ["плечо", "плеча", "плеч"],
        "ro": ["cursă", "curse", "de curse"],
        "en": ["leg", "legs"],
    },
    "ai.model_prior": {
        "ru": "априорная модель", "ro": "model a priori",
        "en": "prior model",
    },
    "ai.forecast_prefix": {
        "ru": "ИИ-прогноз · {note}", "ro": "Prognoză AI · {note}",
        "en": "AI forecast · {note}",
    },
    "ai.forecast_trained_trips": {
        "ru": "ИИ-прогноз (модель обучена, {n} {trips_word})",
        "ro": "Prognoză AI (model antrenat, {n} {trips_word})",
        "en": "AI forecast (model trained, {n} {trips_word})",
    },
    "ai.forecast_trained_trips.trips_word": {
        "ru": ["рейс", "рейса", "рейсов"],
        "ro": ["cursă", "curse", "de curse"],
        "en": ["trip", "trips"],
    },
    "ai.forecast_prior": {
        "ru": "ИИ-прогноз (априорная модель)",
        "ro": "Prognoză AI (model a priori)",
        "en": "AI forecast (prior model)",
    },
    "eta.dc_shipment": {
        "ru": "РЦ «Гурман»: {name} × {qty}",
        "ro": "CD «Gurman»: {name} × {qty}",
        "en": "DC «Gurman»: {name} × {qty}",
    },
    "eta.supplier_direct": {
        "ru": "Поставщик напрямую: {name} × {qty}",
        "ro": "Furnizor direct: {name} × {qty}",
        "en": "Supplier direct: {name} × {qty}",
    },
    "eta.supply_plan": {
        "ru": "план поставки", "ro": "plan de livrare",
        "en": "delivery plan",
    },
    "eta.this_point": {
        "ru": "эта точка", "ro": "acest punct", "en": "this point",
    },
    "eta.courier_assigning": {
        "ru": "курьер назначается…", "ro": "curierul se atribuie…",
        "en": "assigning a courier…",
    },
    "eta.board_title": {
        "ru": "Табло прибытия", "ro": "Tabel de sosiri",
        "en": "Arrival board",
    },
    "eta.plan_short": {"ru": "план", "ro": "plan", "en": "plan"},
    "eta.order_status_prefix": {
        "ru": "заказ: {status}", "ro": "comandă: {status}",
        "en": "order: {status}",
    },
    "unit.sec_short": {"ru": "с", "ro": "s", "en": "s"},
    "unit.min_short": {"ru": "мин", "ro": "min", "en": "min"},
    "unit.hour_short": {"ru": "ч", "ro": "h", "en": "h"},
    "unit.pcs_short": {"ru": "шт.", "ro": "buc.", "en": "pcs"},

    # ---- карта сети (map.html) -----------------------------------------
    "map.title": {
        "ru": "Сеть «Гурман» · Кишинёв", "ro": "Rețeaua «Gurman» · Chișinău",
        "en": "«Gurman» network · Chisinau",
    },
    "map.sub": {
        "ru": "Эмуляция торгового дня", "ro": "Emularea zilei comerciale",
        "en": "Trading day emulation",
    },
    "map.kpi.revenue": {
        "ru": "выручка сети", "ro": "venitul rețelei", "en": "network revenue",
    },
    "map.kpi.sales": {"ru": "продаж", "ro": "vânzări", "en": "sales"},
    "map.kpi.stores": {"ru": "магазинов", "ro": "magazine", "en": "stores"},
    "map.kpi.empty_shelves": {
        "ru": "пустых полок", "ro": "rafturi goale", "en": "empty shelves",
    },
    "map.kpi.zabbix_active": {
        "ru": "активных проблем Zabbix", "ro": "probleme active Zabbix",
        "en": "active Zabbix issues",
    },
    "map.kpi.zabbix_emulation": {
        "ru": " (эмуляция)", "ro": " (emulare)", "en": " (emulated)",
    },
    "map.link.delivery": {
        "ru": "Интернет-заказы и доставка →",
        "ro": "Comenzi online și livrare →",
        "en": "Online orders and delivery →",
    },
    "map.link.docs": {"ru": "Документация", "ro": "Documentație", "en": "Docs"},
    "map.link.presentation": {
        "ru": "Презентация", "ro": "Prezentare", "en": "Presentation",
    },
    "map.mode.2d": {"ru": "2D", "ro": "2D", "en": "2D"},
    "map.mode.3d": {"ru": "3D", "ro": "3D", "en": "3D"},
    "map.card.level": {"ru": "Уровень", "ro": "Nivel", "en": "Level"},
    "map.card.revenue": {"ru": "Выручка", "ro": "Venit", "en": "Revenue"},
    "map.card.sales": {"ru": "Продаж", "ro": "Vânzări", "en": "Sales"},
    "map.card.visitors": {
        "ru": "Покупателей в зале", "ro": "Clienți în magazin",
        "en": "Shoppers in store",
    },
    "map.card.fill": {
        "ru": "Заполненность полок", "ro": "Umplerea rafturilor",
        "en": "Shelf fill rate",
    },
    "map.card.violations": {
        "ru": "Нарушений (критич.)", "ro": "Încălcări (critice)",
        "en": "Violations (critical)",
    },
    "map.card.empty_shelves": {
        "ru": "Пустые полки: ", "ro": "Rafturi goale: ",
        "en": "Empty shelves: ",
    },
    "map.card.enter": {
        "ru": "Войти в магазин", "ro": "Intră în magazin",
        "en": "Enter the store",
    },
    "map.dc.stock": {
        "ru": "Остаток на складе", "ro": "Stoc în depozit",
        "en": "Warehouse stock",
    },
    "map.dc.low_sku": {
        "ru": "SKU ниже точки заказа", "ro": "SKU sub pragul de comandă",
        "en": "SKUs below reorder point",
    },
    "map.dc.trucks": {
        "ru": "Машин в пути", "ro": "Camioane în drum",
        "en": "Trucks en route",
    },
    "map.dc.supplier_line": {
        "ru": "от поставщика: {sku} × {qty} (~{eta_sec} с)",
        "ro": "de la furnizor: {sku} × {qty} (~{eta_sec} s)",
        "en": "from supplier: {sku} × {qty} (~{eta_sec} s)",
    },
    "map.zabbix.head": {
        "ru": "Zabbix: {n} {problems_word}",
        "ro": "Zabbix: {n} {problems_word}",
        "en": "Zabbix: {n} {problems_word}",
    },
    "map.zabbix.head.problems_word": {
        "ru": ["активная проблема", "активные проблемы", "активных проблем"],
        "ro": ["problemă activă", "probleme active", "de probleme active"],
        "en": ["active issue", "active issues"],
    },
    "map.zabbix.none": {
        "ru": "Zabbix: проблем нет", "ro": "Zabbix: fără probleme",
        "en": "Zabbix: no issues",
    },
    "map.eta.head": {
        "ru": "Табло прибытия · ИИ", "ro": "Tabel de sosiri · AI",
        "en": "Arrival board · AI",
    },
    "map.eta.none": {
        "ru": "машин поставщиков в пути нет",
        "ro": "niciun camion al furnizorilor în drum",
        "en": "no supplier trucks en route",
    },
    "map.eta.telemetry_note": {
        "ru": "GPS-телеметрия рейсов → онлайн-обучение",
        "ro": "Telemetrie GPS a curselor → învățare online",
        "en": "trip GPS telemetry → online learning",
    },
    "map.plan_short": {"ru": "план", "ro": "plan", "en": "plan"},
    "map.enter.text": {
        "ru": "входим в магазин…", "ro": "intrăm în magazin…",
        "en": "entering the store…",
    },
    "map.interior.tab_plan": {
        "ru": "Планограмма 3D", "ro": "Planogramă 3D", "en": "3D planogram",
    },
    "map.interior.tab_live": {
        "ru": "Симуляция зала", "ro": "Simularea sălii",
        "en": "Sales floor simulation",
    },
    "map.interior.tab_game": {
        "ru": "Тренажёр", "ro": "Simulator de instruire", "en": "Trainer",
    },
    "map.interior.back": {
        "ru": "Назад на карту", "ro": "Înapoi la hartă", "en": "Back to map",
    },
    "map.interior.status_line": {
        "ru": "выручка {rev} L · полки {fill}%",
        "ro": "venit {rev} L · rafturi {fill}%",
        "en": "revenue {rev} L · shelves {fill}%",
    },
    "map.interior.zabbix_active": {
        "ru": "Zabbix: {n} активных проблем",
        "ro": "Zabbix: {n} probleme active",
        "en": "Zabbix: {n} active issues",
    },
    "map.interior.zabbix_none": {
        "ru": "Zabbix: проблем нет", "ro": "Zabbix: fără probleme",
        "en": "Zabbix: no issues",
    },
    "map.dc.title": {"ru": "РЦ «Гурман»", "ro": "CD «Gurman»", "en": "DC «Gurman»"},

    # ---- страница доставки (delivery.html) -------------------------------
    "delivery.title": {
        "ru": "Интернет-заказы и доставка",
        "ro": "Comenzi online și livrare",
        "en": "Online orders and delivery",
    },
    "delivery.kpi.picking": {"ru": "сборка", "ro": "pregătire", "en": "picking"},
    "delivery.kpi.packed": {"ru": "готово", "ro": "gata", "en": "packed"},
    "delivery.kpi.delivering": {
        "ru": "в доставке", "ro": "în livrare", "en": "delivering",
    },
    "delivery.kpi.delivered": {
        "ru": "доставлено", "ro": "livrate", "en": "delivered",
    },
    "delivery.kpi.receipts": {"ru": "чеков", "ro": "bonuri", "en": "receipts"},
    "delivery.back_to_map": {
        "ru": "← карта сети", "ro": "← harta rețelei", "en": "← network map",
    },
    "delivery.side.routes": {
        "ru": "Маршруты и курьеры", "ro": "Rute și curieri",
        "en": "Routes and couriers",
    },
    "delivery.side.orders": {"ru": "Заказы", "ro": "Comenzi", "en": "Orders"},
    "delivery.side.events": {
        "ru": "События", "ro": "Evenimente", "en": "Events",
    },
    "delivery.routes.empty": {
        "ru": "ожидание сборки заказов…", "ro": "se așteaptă pregătirea "
        "comenzilor…", "en": "waiting for orders to be picked…",
    },
    "delivery.routes.addresses": {
        "ru": "{cur}/{total} адресов", "ro": "{cur}/{total} adrese",
        "en": "{cur}/{total} addresses",
    },
    "delivery.gantt.title": {
        "ru": "Диаграмма Ганта — доставка по маршрутам (план / факт)",
        "ro": "Diagramă Gantt — livrare pe rute (plan / fapt)",
        "en": "Gantt chart — delivery by route (plan / actual)",
    },
    "delivery.gantt.empty": {
        "ru": "маршруты появятся после сборки заказов",
        "ro": "rutele vor apărea după pregătirea comenzilor",
        "en": "routes will appear once orders are picked",
    },
    "delivery.receipts.title": {
        "ru": "Чеки при вручении", "ro": "Bonuri la predare",
        "en": "Receipts on handover",
    },
    "delivery.receipts.empty": {
        "ru": "чеки появятся при вручении заказов",
        "ro": "bonurile vor apărea la predarea comenzilor",
        "en": "receipts will appear on order handover",
    },
    "delivery.eta.title": {
        "ru": "Табло прибытия", "ro": "Tabel de sosiri",
        "en": "Arrival board",
    },
    "delivery.eta.ai_badge": {"ru": "ИИ", "ro": "AI", "en": "AI"},
    "delivery.stop.tooltip": {
        "ru": "клик: табло прибытия (ИИ)",
        "ro": "clic: tabel de sosiri (AI)",
        "en": "click: arrival board (AI)",
    },
    "delivery.ai_arrival": {
        "ru": "ИИ-прибытие: {t} ±{sigma} с",
        "ro": "Sosire AI: {t} ±{sigma} s",
        "en": "AI arrival: {t} ±{sigma} s",
    },

    # ---- команда (team.html) -------------------------------------------
    "team.header": {
        "ru": "Команда «Гурман»: баллы и поощрения",
        "ro": "Echipa «Gurman»: puncte și recompense",
        "en": "«Gurman» team: points and rewards",
    },
    "team.mode.roblox": {
        "ru": "Roblox Open Cloud", "ro": "Roblox Open Cloud",
        "en": "Roblox Open Cloud",
    },
    "team.mode.emulation": {
        "ru": "эмуляция Roblox", "ro": "emulare Roblox",
        "en": "Roblox emulation",
    },
    "team.link.trainer": {
        "ru": "тренажёр", "ro": "simulator", "en": "trainer",
    },
    "team.leaderboard": {
        "ru": "Лидерборд", "ro": "Clasament", "en": "Leaderboard",
    },
    "team.no_badges": {
        "ru": "без бейджей", "ro": "fără insigne", "en": "no badges",
    },
    "team.no_members": {
        "ru": "Пока никто не зарегистрирован — пройдите смену в {link}.",
        "ro": "Deocamdată nimeni nu s-a înregistrat — parcurgeți o tură "
              "în {link}.",
        "en": "No one is registered yet — complete a shift in {link}.",
    },
    "team.trainer_link_text": {
        "ru": "тренажёре", "ro": "simulator", "en": "the trainer",
    },
    "team.feed": {
        "ru": "Лента поощрений", "ro": "Fluxul de recompense",
        "en": "Rewards feed",
    },
    "team.feed_empty": {
        "ru": "Событий пока нет.", "ro": "Deocamdată fără evenimente.",
        "en": "No events yet.",
    },

    # ---- документация (docs.html) --------------------------------------
    "docs.pdf": {"ru": "PDF-презентация", "ro": "Prezentare PDF",
                "en": "PDF presentation"},
    "docs.html_article": {
        "ru": "HTML-версия статьи", "ro": "Versiune HTML a articolului",
        "en": "HTML article version",
    },
    "docs.back_to_map": {
        "ru": "← карта сети", "ro": "← harta rețelei", "en": "← network map",
    },
    "docs.demo_link": {"ru": "Демо", "ro": "Demo", "en": "Demo"},

    # ---- топливная сеть (fuel.html, peco_fuel.py) -----------------------
    "fuel.title": {
        "ru": "⛽ Топливная сеть PECO · Молдова",
        "ro": "⛽ Rețeaua de combustibil PECO · Moldova",
        "en": "⛽ PECO fuel network · Moldova",
    },
    "fuel.erp_link": {
        "ru": "→ учётная система (ERP)", "ro": "→ sistem ERP",
        "en": "→ ERP system",
    },
    "fuel.kpi.stations": {"ru": "АЗС: ", "ro": "Stații: ", "en": "Stations: "},
    "fuel.kpi.low": {
        "ru": "низкий запас: ", "ro": "stoc redus: ", "en": "low stock: ",
    },
    "fuel.kpi.dry": {
        "ru": "риск сухого бака: ", "ro": "risc de rezervor gol: ",
        "en": "dry tank risk: ",
    },
    "fuel.kpi.trips": {"ru": "рейсов: ", "ro": "curse: ", "en": "trips: "},
    "fuel.side.trips": {
        "ru": "Рейсы бензовозов", "ro": "Curse cisterne",
        "en": "Tanker trips",
    },
    "fuel.side.runs": {
        "ru": "Прогоны автозаказа", "ro": "Rulaje comandă automată",
        "en": "Auto-order runs",
    },
    "fuel.legend.normal": {
        "ru": "запас в норме", "ro": "stoc normal", "en": "stock normal",
    },
    "fuel.legend.low": {
        "ru": "ниже точки заказа", "ro": "sub pragul de comandă",
        "en": "below reorder point",
    },
    "fuel.legend.dry": {
        "ru": "риск сухого бака", "ro": "risc de rezervor gol",
        "en": "dry tank risk",
    },
    "fuel.eta.none": {
        "ru": "бензовозов в пути нет", "ro": "niciun autocisternă în drum",
        "en": "no tankers en route",
    },
    "fuel.eta.source_prefix": {
        "ru": "источник данных: ", "ro": "sursă date: ",
        "en": "data source: ",
    },
    "fuel.eta.tanker_row": {
        "ru": "{trip} · {driver} · {liters} л",
        "ro": "{trip} · {driver} · {liters} l",
        "en": "{trip} · {driver} · {liters} L",
    },
    "fuel.trip.done": {"ru": "завершён", "ro": "finalizat", "en": "completed"},
    "fuel.trip.enroute": {"ru": "в пути", "ro": "în drum", "en": "en route"},
    "fuel.trips.empty": {
        "ru": "рейсов пока нет", "ro": "deocamdată fără curse",
        "en": "no trips yet",
    },
    "fuel.runs.empty": {
        "ru": "автозаказов пока не было",
        "ro": "deocamdată fără comenzi automate",
        "en": "no auto-orders yet",
    },
    "fuel.station.tooltip": {
        "ru": "{name} · заполненность {pct}% · {days} дн. до сухого бака "
              "— клик: табло",
        "ro": "{name} · umplere {pct}% · {days} zile până la rezervor gol "
              "— clic: tabel",
        "en": "{name} · fill {pct}% · {days} days to dry tank "
              "— click: arrival board",
    },
    "fuel.tanker.tooltip": {
        "ru": "{id} · {driver} · {liters} л · прогресс {pct}%",
        "ro": "{id} · {driver} · {liters} l · progres {pct}%",
        "en": "{id} · {driver} · {liters} L · progress {pct}%",
    },
    # ---- сценарная демонстрация автозаказа (fuel.html, ?focus=<id>) -----
    "fuel.demo.phase_waiting": {
        "ru": "🛢 Сработал автозаказ — {name}. Собираем бензовоз в рейс…",
        "ro": "🛢 Comandă automată declanșată — {name}. Se pregătește "
              "autocisternă…",
        "en": "🛢 Auto-order triggered — {name}. Dispatching a tanker…",
    },
    "fuel.demo.phase_enroute": {
        "ru": "🚛 Бензовоз в пути → {name} · {liters} л · {driver}",
        "ro": "🚛 Autocisternă în drum → {name} · {liters} l · {driver}",
        "en": "🚛 Tanker en route → {name} · {liters} L · {driver}",
    },
    "fuel.demo.phase_arriving": {
        "ru": "⛽ Прибыл на {name} — переходим на планограмму станции…",
        "ro": "⛽ A ajuns la {name} — se trece la planograma stației…",
        "en": "⛽ Arrived at {name} — switching to the station layout…",
    },
    "unit.liters_short": {"ru": "л", "ro": "l", "en": "L"},
    "unit.kg_short": {"ru": "кг", "ro": "kg", "en": "kg"},
    "unit.meters_short": {"ru": "м", "ro": "m", "en": "m"},
    "unit.days_short": {"ru": "дн.", "ro": "zile", "en": "days"},

    # ---- 3D-планограмма заправки (fuelviz.py, station_page) -------------
    "fuel.open_3d": {
        "ru": "🧊 3D-планограмма станции", "ro": "🧊 Planogramă 3D a stației",
        "en": "🧊 3D station layout",
    },
    "fuelviz.title": {
        "ru": "⛽ {name} — 3D-планограмма",
        "ro": "⛽ {name} — planogramă 3D",
        "en": "⛽ {name} — 3D layout",
    },
    "fuelviz.back_to_map": {
        "ru": "← карта топливной сети", "ro": "← harta rețelei de combustibil",
        "en": "← fuel network map",
    },
    "fuelviz.axis.height": {
        "ru": "высота, м (0 = земля)", "ro": "înălțime, m (0 = sol)",
        "en": "height, m (0 = ground)",
    },
    "fuelviz.legend_title": {
        "ru": "марка топлива", "ro": "tip de combustibil", "en": "fuel grade",
    },
    "fuelviz.ground_hover": {
        "ru": "<b>{name}</b><br>площадка АЗС, уровень земли",
        "ro": "<b>{name}</b><br>platforma stației, nivelul solului",
        "en": "<b>{name}</b><br>station forecourt, ground level",
    },
    "fuelviz.underground_hover": {
        "ru": "подземный контур — цистерны хранения ниже уровня земли",
        "ro": "contur subteran — rezervoare de stocare sub nivelul solului",
        "en": "underground contour — storage tanks below ground level",
    },
    "fuelviz.canopy_hover": {
        "ru": "навес топливораздаточных колонок",
        "ro": "copertină a pompelor de combustibil",
        "en": "fuel dispenser canopy",
    },
    "fuelviz.dispenser_hover": {
        "ru": "колонка ТРК · отпускает: {grades}",
        "ro": "pompă de combustibil · distribuie: {grades}",
        "en": "fuel dispenser · dispenses: {grades}",
    },
    "fuelviz.dispenser_grade_hover": {
        "ru": "марка {grade}", "ro": "tip {grade}", "en": "grade {grade}",
    },
    "fuelviz.tank_hover": {
        "ru": "<b>Цистерна {grade}</b><br>{cur} / {cap} л ({pct}%)",
        "ro": "<b>Rezervor {grade}</b><br>{cur} / {cap} l ({pct}%)",
        "en": "<b>Tank {grade}</b><br>{cur} / {cap} L ({pct}%)",
    },
    "fuelviz.hatch_hover": {
        "ru": "горловина цистерны {grade} — люк до уровня земли",
        "ro": "gura rezervorului {grade} — gură până la nivelul solului",
        "en": "tank {grade} hatch — manhole up to ground level",
    },
    "fuelviz.truck_hover": {
        "ru": "🚛 бензовоз ({driver}) сливает {liters} л · разгрузка {pct}%",
        "ro": "🚛 autocisternă ({driver}) descarcă {liters} l · descărcare {pct}%",
        "en": "🚛 tanker ({driver}) unloading {liters} L · progress {pct}%",
    },
    "fuelviz.truck_label": {
        "ru": "слив {pct}%", "ro": "descărcare {pct}%",
        "en": "unloading {pct}%",
    },
    "fuelviz.demo_driver": {
        "ru": "демо-водитель", "ro": "șofer demo", "en": "demo driver",
    },
    "fuelviz.panel.unloading": {
        "ru": "Идёт разгрузка: {driver}, {liters} л, {pct}% слито",
        "ro": "Descărcare în curs: {driver}, {liters} l, {pct}% descărcat",
        "en": "Unloading in progress: {driver}, {liters} L, {pct}% done",
    },

    # ---- лента событий и прогоны топливного контура (peco_fuel.py) ------
    "fuel.log.autoorder_dispatch": {
        "ru": "Автозаказ → рейс {trip} ({driver}): {names}",
        "ro": "Comandă automată → cursă {trip} ({driver}): {names}",
        "en": "Auto-order → trip {trip} ({driver}): {names}",
    },
    "fuel.log.tanker_fill": {
        "ru": "{trip}: залив {name} (+{qty} л)",
        "ro": "{trip}: alimentare {name} (+{qty} l)",
        "en": "{trip}: filled {name} (+{qty} L)",
    },
    "fuel.log.trip_done": {
        "ru": "Рейс {trip} завершён ({driver})",
        "ro": "Cursa {trip} finalizată ({driver})",
        "en": "Trip {trip} completed ({driver})",
    },
    "fuel.log.artgranit_down": {
        "ru": "Artgranit недоступен ({error}), переход на эмуляцию по "
              "истечении окна свежести",
        "ro": "Artgranit indisponibil ({error}), se trece la emulare după "
              "expirarea ferestrei de prospețime",
        "en": "Artgranit unavailable ({error}), switching to emulation "
              "once the freshness window expires",
    },
    "fuel.log.artgranit_up": {
        "ru": "Artgranit на связи: {n} АЗС, {n2} {trips_word}",
        "ro": "Artgranit conectat: {n} stații, {n2} {trips_word}",
        "en": "Artgranit connected: {n} stations, {n2} {trips_word}",
    },
    "fuel.log.artgranit_offline": {
        "ru": "Artgranit молчит дольше {sec} с — эмуляция",
        "ro": "Artgranit tace de peste {sec} s — emulare",
        "en": "Artgranit silent for over {sec} s — emulation",
    },
    "fuel.run.message": {
        "ru": "Автозаказ: {n} АЗС, {qty} л, рейс {trip}",
        "ro": "Comandă automată: {n} stații, {qty} l, cursa {trip}",
        "en": "Auto-order: {n} stations, {qty} L, trip {trip}",
    },

    # ---- симуляция торгового зала (instore.html, instore.py) ------------
    "instore.side.title": {
        "ru": "🎮 Симуляция торгового зала",
        "ro": "🎮 Simularea sălii de vânzare",
        "en": "🎮 Sales floor simulation",
    },
    "instore.mode.test": {
        "ru": "🧪 тестовый поток", "ro": "🧪 flux de test",
        "en": "🧪 test feed",
    },
    "instore.mode.real": {
        "ru": "📡 реальный поток (кассы/CCTV)",
        "ro": "📡 flux real (case de marcat/CCTV)",
        "en": "📡 live feed (registers/CCTV)",
    },
    "instore.kpi.in_store": {
        "ru": "в зале сейчас", "ro": "în magazin acum",
        "en": "in store now",
    },
    "instore.kpi.visitors": {
        "ru": "посетителей", "ro": "vizitatori", "en": "visitors",
    },
    "instore.kpi.receipts": {"ru": "чеков", "ro": "bonuri", "en": "receipts"},
    "instore.kpi.revenue": {
        "ru": "выручка касс", "ro": "venit case", "en": "register revenue",
    },
    "instore.kpi.sco_share": {
        "ru": "доля СКО", "ro": "cotă self-checkout",
        "en": "self-checkout share",
    },
    "instore.kpi.weighings": {
        "ru": "взвешиваний", "ro": "cântăriri", "en": "weighings",
    },
    "instore.est.label": {
        "ru": "👥 Оценка по датчикам входа/выхода",
        "ro": "👥 Estimare după senzorii de intrare/ieșire",
        "en": "👥 Estimate from entry/exit sensors",
    },
    "instore.est.text": {
        "ru": "в зале ~{in_store}, в очередях {in_queues}, по залу {on_floor}",
        "ro": "în magazin ~{in_store}, la coadă {in_queues}, prin magazin "
              "{on_floor}",
        "en": "in store ~{in_store}, in queues {in_queues}, "
              "on the floor {on_floor}",
    },
    "instore.cons.title": {
        "ru": "🧻 Расходники", "ro": "🧻 Consumabile", "en": "🧻 Consumables",
    },
    "instore.label.bags": {"ru": "Кульки", "ro": "Pungi", "en": "Bags"},
    "instore.label.pos_n": {
        "ru": "Касса {n}", "ro": "Casă {n}", "en": "Register {n}",
    },
    "instore.label.scales": {"ru": "Весы", "ro": "Cântar", "en": "Scale"},
    "instore.label.entrance": {"ru": "ВХОД", "ro": "INTRARE", "en": "ENTRY"},
    "instore.label.exit": {"ru": "ВЫХОД", "ro": "IEȘIRE", "en": "EXIT"},
    "instore.label.sco": {
        # СКО (самообслуживание) — общепринятая аббревиатура self-checkout;
        # в ro/en даём то же короткое, узнаваемое название, а не дословный
        # перевод «касса с самообслуживанием»
        "ru": "СКО", "ro": "self-checkout", "en": "self-checkout",
    },
    "instore.label.fridge_n": {
        # ХВ — холодильная витрина; ro/en используют предметное название
        # (не транслитерацию), т.к. аббревиатура ХВ ничего не говорит
        # неруссскоязычному читателю
        "ru": "ХВ-{n}", "ro": "vitrină frig. {n}", "en": "chiller {n}",
    },
    "instore.label.tsd_n": {
        # ТСД — терминал сбора данных; в рознице ro/en принято называть
        # устройство по функции (сканер), а не по абревиатуре
        "ru": "ТСД-{n}", "ro": "terminal date {n}",
        "en": "handheld scanner {n}",
    },
    "instore.queue.label": {
        "ru": "👥 очередь: {n}", "ro": "👥 coadă: {n}", "en": "👥 queue: {n}",
    },
    "instore.queue.sco_label": {
        "ru": "👥 очередь СКО: {n}", "ro": "👥 coadă self-checkout: {n}",
        "en": "👥 self-checkout queue: {n}",
    },
    "instore.fridge.door_open": {
        "ru": " · дверца!", "ro": " · ușă deschisă!", "en": " · door open!",
    },
    "instore.fridge.alarm": {
        "ru": "⚠ ТРЕВОГА", "ro": "⚠ ALARMĂ", "en": "⚠ ALARM",
    },
    "instore.perishable.zone": {
        "ru": "скоропорт", "ro": "perisabile", "en": "perishables",
    },
    "instore.perishable.zone_cold": {
        "ru": "скоропорт · холод", "ro": "perisabile · frig",
        "en": "perishables · chilled",
    },
    "instore.event.cam_in": {
        "ru": "Видеонаблюдение: посетитель вошёл",
        "ro": "Videosupraveghere: vizitator intrat",
        "en": "CCTV: visitor entered",
    },
    "instore.event.cam_out": {
        "ru": "Видеонаблюдение: посетитель вышел",
        "ro": "Videosupraveghere: vizitator ieșit",
        "en": "CCTV: visitor left",
    },
    "instore.event.pick": {
        "ru": "Взято с полки: {name}", "ro": "Luat de pe raft: {name}",
        "en": "Picked from shelf: {name}",
    },
    "instore.event.scale": {
        "ru": "Весы: {name} — {weight} кг",
        "ro": "Cântar: {name} — {weight} kg",
        "en": "Scale: {name} — {weight} kg",
    },
    "instore.event.sco_in": {
        "ru": "Вход в зону касс самообслуживания",
        "ro": "Intrare în zona self-checkout",
        "en": "Entering the self-checkout zone",
    },
    "instore.event.sco_out": {
        "ru": "Выход из зоны СКО", "ro": "Ieșire din zona self-checkout",
        "en": "Leaving the self-checkout zone",
    },
    "instore.event.pos": {
        "ru": "{register}: чек {total} L ({items} поз.)",
        "ro": "{register}: bon {total} L ({items} art.)",
        "en": "{register}: receipt {total} L ({items} items)",
    },
    "instore.event.fridge_alarm": {
        "ru": "{id}: ТРЕВОГА — температура {temp}°C",
        "ro": "{id}: ALARMĂ — temperatură {temp}°C",
        "en": "{id}: ALARM — temperature {temp}°C",
    },
    "instore.event.source_real": {
        "ru": "поток", "ro": "flux", "en": "feed",
    },
    "instore.event.source_test": {
        "ru": "тест", "ro": "test", "en": "test",
    },
    "instore.log.paper_low": {
        "ru": "заканчивается лента ({level}%), вызван сотрудник",
        "ro": "se termină banda ({level}%), a fost chemat un angajat",
        "en": "paper roll running low ({level}%), staff called",
    },
    "instore.log.bags_low": {
        "ru": "кульки для овощей заканчиваются ({n} шт.), заказано "
              "пополнение",
        "ro": "pungile pentru legume se termină ({n} buc.), "
              "reaprovizionare comandată",
        "en": "vegetable bags running low ({n} pcs), restock ordered",
    },
    "instore.log.paper_replaced": {
        "ru": "лента заменена", "ro": "banda a fost înlocuită",
        "en": "paper roll replaced",
    },
    "instore.log.bags_replenished": {
        "ru": "кульки пополнены (теперь {n} шт.)",
        "ro": "pungile au fost reaprovizionate (acum {n} buc.)",
        "en": "bags restocked (now {n} pcs)",
    },

    # ---- аварии мониторинга (zabbix.py, эмуляция) — показываются в -----
    # ---- карточке магазина на карте -------------------------------------
    "zabbix.problem.pos_offline": {
        "ru": "Касса №2: нет связи с сервером",
        "ro": "Casa nr. 2: fără legătură cu serverul",
        "en": "Register #2: no connection to server",
    },
    "zabbix.problem.acquiring_timeout": {
        "ru": "Эквайринг: тайм-ауты авторизации",
        "ro": "Acceptare carduri: timeout la autorizare",
        "en": "Card acquiring: authorization timeouts",
    },
    "zabbix.problem.fridge_temp": {
        "ru": "Холодильная витрина: температура выше нормы",
        "ro": "Vitrină frigorifică: temperatură peste normă",
        "en": "Chiller display: temperature above normal",
    },
    "zabbix.problem.ups_battery": {
        "ru": "ИБП: переход на питание от батареи",
        "ro": "UPS: trecere pe alimentare cu baterie",
        "en": "UPS: switched to battery power",
    },
    "zabbix.problem.disk_full": {
        "ru": "Сервер магазина: диск заполнен > 90%",
        "ro": "Serverul magazinului: disc ocupat > 90%",
        "en": "Store server: disk over 90% full",
    },
    "zabbix.problem.scales_unresponsive": {
        "ru": "Весы в торговом зале не отвечают",
        "ro": "Cântarul din sala de vânzare nu răspunde",
        "en": "Sales floor scale not responding",
    },
    "zabbix.problem.scanner_errors": {
        "ru": "Сканер ШК на кассе №1: ошибки чтения",
        "ro": "Scanerul de coduri de bare la casa nr. 1: erori de citire",
        "en": "Barcode scanner at register #1: read errors",
    },
    "zabbix.problem.camera_offline": {
        "ru": "Камера видеонаблюдения №4 офлайн",
        "ro": "Camera de supraveghere nr. 4 offline",
        "en": "CCTV camera #4 offline",
    },
    "zabbix.severity.0": {
        "ru": "не классифицировано", "ro": "neclasificat",
        "en": "not classified",
    },
    "zabbix.severity.1": {
        "ru": "информация", "ro": "informare", "en": "information",
    },
    "zabbix.severity.2": {
        "ru": "предупреждение", "ro": "avertizare", "en": "warning",
    },
    "zabbix.severity.3": {"ru": "средняя", "ro": "medie", "en": "average"},
    "zabbix.severity.4": {"ru": "высокая", "ro": "ridicată", "en": "high"},
    "zabbix.severity.5": {
        "ru": "чрезвычайная", "ro": "critică", "en": "disaster",
    },

    # ---- навигация документации (server.py _DOCS) ------------------------
    "docs.nav.readme": {
        "ru": "О модуле", "ro": "Despre modul", "en": "About the module",
    },
    "docs.nav.tz": {
        "ru": "Техзадание", "ro": "Caiet de sarcini",
        "en": "Requirements spec",
    },
    "docs.nav.erp3d": {
        "ru": "3D для ERP", "ro": "3D pentru ERP", "en": "3D for ERP",
    },
    "docs.nav.library": {
        "ru": "Справочник API", "ro": "Referință API",
        "en": "API reference",
    },
    "docs.nav.integration": {
        "ru": "Интеграция", "ro": "Integrare", "en": "Integration",
    },
    "docs.nav.article": {
        "ru": "Методичка", "ro": "Ghid metodic", "en": "Training guide",
    },
    "docs.nav.roadmap": {
        "ru": "Роадмап ИИ", "ro": "Foaia de parcurs AI",
        "en": "AI roadmap",
    },
    "docs.nav.plan": {
        "ru": "План презентации", "ro": "Planul prezentării",
        "en": "Presentation plan",
    },
    "docs.nav.handoff": {
        "ru": "База знаний", "ro": "Bază de cunoștințe",
        "en": "Knowledge base",
    },

    # ---- встроенные ИИ-боты командной смены (server.py, mgame_bot) -------
    "game.bot.cashier": {
        "ru": "ИИ-Кассир", "ro": "AI-Casier", "en": "AI Cashier",
    },
    "game.bot.merch": {
        "ru": "ИИ-Мерч", "ro": "AI-Merchandiser", "en": "AI Merchandiser",
    },
    "game.bot.cleaner": {
        "ru": "ИИ-Клинер", "ro": "AI-Curățenie", "en": "AI Cleaner",
    },
    "game.bot.tech": {
        "ru": "ИИ-Техник", "ro": "AI-Tehnician", "en": "AI Technician",
    },
    "game.bot.supervisor": {
        "ru": "ИИ-Супервайзер", "ro": "AI-Supervizor",
        "en": "AI Supervisor",
    },
    "game.bot.default": {
        "ru": "ИИ-Бот", "ro": "AI-Bot", "en": "AI Bot",
    },

    # ---- команда: бейджи и лента поощрений (roblox.py) -------------------
    "roblox.badge.cashier_novice": {
        "ru": "🥉 Кассир-новичок", "ro": "🥉 Casier debutant",
        "en": "🥉 Rookie cashier",
    },
    "roblox.badge.cleanliness_guardian": {
        "ru": "🥈 Хранитель чистоты", "ro": "🥈 Gardianul curățeniei",
        "en": "🥈 Cleanliness guardian",
    },
    "roblox.badge.rush_hour_hero": {
        "ru": "🥇 Герой часа пик", "ro": "🥇 Eroul orei de vârf",
        "en": "🥇 Rush hour hero",
    },
    "roblox.badge.shift_master": {
        "ru": "🏆 Наставник смены", "ro": "🏆 Mentorul turei",
        "en": "🏆 Shift mentor",
    },
    "roblox.feed.joined": {
        "ru": "👋 {name} ({roblox_user}) присоединился к команде",
        "ro": "👋 {name} ({roblox_user}) s-a alăturat echipei",
        "en": "👋 {name} ({roblox_user}) joined the team",
    },
    "roblox.feed.shift_passed": {
        "ru": "смена {level} пройдена, {stars}",
        "ro": "tura {level} finalizată, {stars}",
        "en": "shift {level} passed, {stars}",
    },
    "roblox.feed.shift_failed": {
        "ru": "смена {level} не пройдена",
        "ro": "tura {level} nereușită",
        "en": "shift {level} not passed",
    },
    "roblox.feed.revenue_suffix": {
        "ru": ", выручка {revenue} L", "ro": ", venit {revenue} L",
        "en": ", revenue {revenue} L",
    },
    "roblox.feed.points_award": {
        "ru": "💎 {name}: +{points} баллов — {reason}",
        "ro": "💎 {name}: +{points} puncte — {reason}",
        "en": "💎 {name}: +{points} points — {reason}",
    },

    # ---- тренажёр соло (game.html) ---------------------------------------
    #
    # Часть строк — константы уровней и подсказки, зашитые в JS шаблона
    # (LEVELS/TUTOR): переводятся через client_catalog + tt() на клиенте,
    # т.к. это статичная конфигурация игры, а не данные с сервера при
    # каждом опросе. Общие с командным тренажёром подписи (busy-лейблы,
    # тексты попапов, "СКЛАД"/"НЕТ ЛЕНТЫ") держим одним ключом на оба
    # файла — см. переиспользование в group ниже (game_multi.html).
    "game.page_title_suffix": {
        "ru": "— тренажёр персонала", "ro": "— simulator de instruire",
        "en": "— staff trainer",
    },
    "game.hud.revenue": {"ru": "выручка", "ro": "venit", "en": "revenue"},
    "game.hud.shift_time": {
        "ru": "время смены", "ro": "timp tură", "en": "shift time",
    },
    "game.hud.reputation": {
        "ru": "репутация", "ro": "reputație", "en": "reputation",
    },
    "game.hud.shift": {"ru": "смена", "ro": "tură", "en": "shift"},
    "game.hud.carrying": {
        "ru": "в руках", "ro": "în mâini", "en": "carrying",
    },
    "game.hud.loading": {
        "ru": "Загрузка…", "ro": "Se încarcă…", "en": "Loading…",
    },
    "game.brief.title": {
        "ru": "🎓 Тренажёр персонала магазина",
        "ro": "🎓 Simulator de instruire pentru personal",
        "en": "🎓 Store staff trainer",
    },
    "game.brief.name_placeholder": {
        "ru": "Имя сотрудника", "ro": "Numele angajatului",
        "en": "Employee name",
    },
    "game.brief.roblox_placeholder": {
        "ru": "Ник в Roblox", "ro": "Nume Roblox", "en": "Roblox username",
    },
    "game.brief.start_btn": {
        "ru": "▶ Начать смену", "ro": "▶ Începe tura", "en": "▶ Start shift",
    },
    "game.brief.multi_link": {
        "ru": "👥 Командная смена: до 10 игроков и ИИ-ботов →",
        "ro": "👥 Tură de echipă: până la 10 jucători și boți AI →",
        "en": "👥 Team shift: up to 10 players and AI bots →",
    },
    "game.brief.goal": {
        "ru": "🎯 Цель смены: выручка {goal} L за {mins} {min_unit}",
        "ro": "🎯 Obiectivul turei: venit {goal} L în {mins} {min_unit}",
        "en": "🎯 Shift goal: {goal} L revenue in {mins} {min_unit}",
    },
    "game.level1.title": {
        "ru": "Смена 1 · Основы", "ro": "Tura 1 · Bazele",
        "en": "Shift 1 · Basics",
    },
    "game.level1.brief1": {
        "ru": "Пополняйте полки со склада 📦 до того, как они опустеют",
        "ro": "Reaprovizionați rafturile din depozit 📦 înainte să se "
              "golească",
        "en": "Restock shelves from the storeroom 📦 before they run empty",
    },
    "game.level1.brief2": {
        "ru": "Обслуживайте покупателей на кассе — кликните по кассе",
        "ro": "Deserviți clienții la casă — faceți clic pe casă",
        "en": "Serve customers at the register — click the register",
    },
    "game.level1.brief3": {
        "ru": "У покупателей есть терпение ❤ — не заставляйте их ждать",
        "ro": "Clienții au răbdare ❤ — nu-i lăsați să aștepte",
        "en": "Customers have patience ❤ — don't make them wait",
    },
    "game.level2.title": {
        "ru": "Смена 2 · Чистота и лента",
        "ro": "Tura 2 · Curățenie și bandă",
        "en": "Shift 2 · Cleanliness and paper roll",
    },
    "game.level2.brief1": {
        "ru": "Появились новые заботы: разливы на полу 🫗 — убирайте их",
        "ro": "Au apărut griji noi: lichide vărsate pe podea 🫗 — "
              "curățați-le",
        "en": "New concerns appeared: floor spills 🫗 — clean them up",
    },
    "game.level2.brief2": {
        "ru": "Следите за чековой лентой кассы 🧻 — меняйте вовремя",
        "ro": "Urmăriți banda de casă 🧻 — schimbați-o la timp",
        "en": "Watch the register's paper roll 🧻 — replace it in time",
    },
    "game.level2.brief3": {
        "ru": "Поток покупателей вырос — планируйте цепочки действий",
        "ro": "Fluxul de clienți a crescut — planificați lanțuri de "
              "acțiuni",
        "en": "Customer flow has grown — plan action chains",
    },
    "game.level3.title": {
        "ru": "Смена 3 · Час пик", "ro": "Tura 3 · Ora de vârf",
        "en": "Shift 3 · Rush hour",
    },
    "game.level3.brief1": {
        "ru": "Час пик: покупатели нетерпеливее, поток плотнее",
        "ro": "Ora de vârf: clienții sunt mai nerăbdători, fluxul e mai "
              "dens",
        "en": "Rush hour: customers are less patient, the flow is denser",
    },
    "game.level3.brief2": {
        "ru": "Холодильники дают сбои 🧊 — реагируйте на тревоги",
        "ro": "Frigiderele dau erori 🧊 — reacționați la alarme",
        "en": "Chillers are failing 🧊 — respond to the alarms",
    },
    "game.level3.brief3": {
        "ru": "Держите репутацию: злые покупатели уходят без покупок",
        "ro": "Păstrați reputația: clienții supărați pleacă fără "
              "cumpărături",
        "en": "Protect your reputation: angry customers leave without "
              "buying",
    },
    "game.result.title_ok": {
        "ru": "✅ Смена пройдена!", "ro": "✅ Tură reușită!",
        "en": "✅ Shift complete!",
    },
    "game.result.title_fail": {
        "ru": "❌ План не выполнен", "ro": "❌ Planul nu a fost îndeplinit",
        "en": "❌ Target missed",
    },
    "game.result.stat.revenue_label": {
        "ru": "Выручка", "ro": "Venit", "en": "Revenue",
    },
    "game.result.revenue_value": {
        "ru": "{money} L из {goal} L", "ro": "{money} L din {goal} L",
        "en": "{money} L of {goal} L",
    },
    "game.result.stat.served": {
        "ru": "Обслужено покупателей", "ro": "Clienți deserviți",
        "en": "Customers served",
    },
    "game.result.stat.lost": {
        "ru": "Ушли недовольными", "ro": "Au plecat nemulțumiți",
        "en": "Left dissatisfied",
    },
    "game.result.stat.restocks": {
        "ru": "Пополнений полок", "ro": "Reaprovizionări rafturi",
        "en": "Shelf restocks",
    },
    "game.result.stat.cleaned": {
        "ru": "Убрано разливов", "ro": "Curățări lichide vărsate",
        "en": "Spills cleaned",
    },
    "game.result.stat.papers_fridges": {
        "ru": "Замен ленты / ремонтов ХВ",
        "ro": "Schimbări bandă / reparații frig.",
        "en": "Paper changes / fridge repairs",
    },
    "game.result.stat.reputation": {
        "ru": "Репутация", "ro": "Reputație", "en": "Reputation",
    },
    "game.tip.lost": {
        "ru": "Много потерянных покупателей — обслуживайте кассу раньше, "
              "чем кончится терпение.",
        "ro": "Mulți clienți pierduți — deserviți casa înainte să se "
              "termine răbdarea.",
        "en": "Too many lost customers — serve the register before "
              "patience runs out.",
    },
    "game.tip.restocks": {
        "ru": "Полки пустели: держите запас — берите со склада до "
              "out-of-stock.",
        "ro": "Rafturile s-au golit: mențineți stocul — luați din depozit "
              "înainte de out-of-stock.",
        "en": "Shelves ran empty: keep stock up — restock from the "
              "storeroom before out-of-stock.",
    },
    "game.tip.reputation": {
        "ru": "Репутация страдает от разливов и тревог — реагируйте на "
              "события сразу.",
        "ro": "Reputația suferă din cauza lichidelor vărsate și a "
              "alarmelor — reacționați imediat la evenimente.",
        "en": "Reputation suffers from spills and alarms — react to "
              "events right away.",
    },
    "game.tip.great": {
        "ru": "Отличная работа: процессы кассира, мерчандайзера и "
              "клининга под контролем!",
        "ro": "Muncă excelentă: procesele de casier, merchandiser și "
              "curățenie sunt sub control!",
        "en": "Great work: cashier, merchandising and cleaning processes "
              "are under control!",
    },
    "game.rbx.points_word": {
        "ru": ["балл", "балла", "баллов"],
        "ro": ["punct", "puncte", "de puncte"],
        "en": ["point", "points"],
    },
    "game.rbx.total_label": {"ru": "всего", "ro": "total", "en": "total"},
    "game.rbx.new_badge_label": {
        "ru": "🏅 Новый бейдж: ", "ro": "🏅 Insignă nouă: ",
        "en": "🏅 New badge: ",
    },
    "game.rbx.top_team_label": {
        "ru": "Топ команды:", "ro": "Top echipă:", "en": "Team leaderboard:",
    },
    "game.rbx.no_roblox": {
        "ru": "🎮 Укажите ник в Roblox на брифинге — баллы и бейджи будут "
              "начисляться в командный опыт Roblox.",
        "ro": "🎮 Indicați numele Roblox la briefing — punctele și "
              "insignele vor fi acordate în experiența de echipă Roblox.",
        "en": "🎮 Enter your Roblox username at the briefing — points and "
              "badges will be credited to the team's Roblox experience.",
    },
    "game.result.next_btn": {
        "ru": "▶ Следующая смена", "ro": "▶ Tura următoare",
        "en": "▶ Next shift",
    },
    "game.result.done_btn": {
        "ru": "🏆 Обучение пройдено — играть снова",
        "ro": "🏆 Instruire finalizată — joacă din nou",
        "en": "🏆 Training complete — play again",
    },
    "game.result.retry_btn": {
        "ru": "↻ Повторить смену", "ro": "↻ Repetă tura",
        "en": "↻ Retry shift",
    },
    "game.tutor.1": {
        "ru": "Кликните на СКЛАД 📦 (дверь на задней стене справа), "
              "чтобы взять товар",
        "ro": "Faceți clic pe DEPOZIT 📦 (ușa din peretele din spate, "
              "dreapta) pentru a lua marfă",
        "en": "Click the STOREROOM 📦 (door on the back wall, right "
              "side) to grab stock",
    },
    "game.tutor.2": {
        "ru": "Теперь кликните на стеллаж, чтобы пополнить полку",
        "ro": "Acum faceți clic pe raft pentru a-l reaproviziona",
        "en": "Now click a shelf to restock it",
    },
    "game.tutor.3": {
        "ru": "Покупатель идёт на кассу — кликните на КАССУ, чтобы "
              "обслужить",
        "ro": "Clientul merge la casă — faceți clic pe CASĂ pentru a-l "
              "deservi",
        "en": "A customer is heading to the register — click the "
              "REGISTER to serve them",
    },
    "game.tutor.4": {
        "ru": "Отлично! Следите за полками, кассой и терпением "
              "покупателей ❤",
        "ro": "Excelent! Urmăriți rafturile, casa și răbdarea "
              "clienților ❤",
        "en": "Great! Keep an eye on shelves, the register and customer "
              "patience ❤",
    },
    "game.hint.no_paper": {
        "ru": "🧻 Кончилась чековая лента! Кликните на кассу, чтобы "
              "заменить",
        "ro": "🧻 S-a terminat banda de casă! Faceți clic pe casă pentru "
              "a o schimba",
        "en": "🧻 Out of paper roll! Click the register to replace it",
    },
    "game.hint.replace_paper": {
        "ru": "🧻 Замените ленту: кликните на кассу!",
        "ro": "🧻 Schimbați banda: faceți clic pe casă!",
        "en": "🧻 Replace the paper roll: click the register!",
    },
    "game.hint.queue_status": {
        "ru": "Очередь: {n} · Кликайте: склад → полки, касса, уборка",
        "ro": "Coadă: {n} · Faceți clic: depozit → rafturi, casă, "
              "curățenie",
        "en": "Queue: {n} · Click: storeroom → shelves, register, "
              "cleaning",
    },
    "game.hint.need_stock": {
        "ru": "Сначала возьмите товар на складе 📦!",
        "ro": "Mai întâi luați marfă din depozit 📦!",
        "en": "First grab stock from the storeroom 📦!",
    },
    "game.busy.storeroom": {
        "ru": "берём товар 📦", "ro": "luăm marfă 📦",
        "en": "grabbing stock 📦",
    },
    "game.busy.shelf": {
        "ru": "выкладка…", "ro": "aranjare pe raft…",
        "en": "stocking shelf…",
    },
    "game.busy.paper": {
        "ru": "замена ленты 🧻", "ro": "schimbare bandă 🧻",
        "en": "replacing paper roll 🧻",
    },
    "game.busy.mess": {
        "ru": "уборка 🧹", "ro": "curățenie 🧹", "en": "cleaning 🧹",
    },
    "game.busy.fridge": {
        "ru": "ремонт ХВ 🧊", "ro": "reparare frig. 🧊",
        "en": "fixing chiller 🧊",
    },
    "game.popup.item_added": {
        "ru": "+товар", "ro": "+marfă", "en": "+stock",
    },
    "game.popup.clean": {"ru": "чисто ✓", "ro": "curat ✓", "en": "clean ✓"},
    "game.popup.fridge_fixed": {
        "ru": "холод ✓", "ro": "frig ✓", "en": "fixed ✓",
    },
    "game.popup.paper_replaced": {
        "ru": "лента ✓", "ro": "bandă ✓", "en": "paper ✓",
    },
    "game.popup.mess": {
        "ru": "разлив! 🫗", "ro": "vărsare! 🫗", "en": "spill! 🫗",
    },
    "game.popup.fridge_alarm": {
        "ru": "тревога! 🧊", "ro": "alarmă! 🧊", "en": "alarm! 🧊",
    },
    "game.label.storeroom": {
        "ru": "📦 СКЛАД", "ro": "📦 DEPOZIT", "en": "📦 STOREROOM",
    },
    "game.label.no_paper": {
        "ru": "🧻 НЕТ ЛЕНТЫ", "ro": "🧻 FĂRĂ BANDĂ", "en": "🧻 NO PAPER",
    },
    "game.default_name": {
        "ru": "Стажёр", "ro": "Stagiar", "en": "Trainee",
    },

    # ---- командная смена (game_multi.html, multigame.py) -----------------
    #
    # Лента событий и всплывающие подсказки командной смены собираются
    # сервером (multigame.py) как ключ+параметры, но рендерятся в
    # браузере через tt()/ttn() — тот же принцип "ключ+параметры,
    # рендер при отдаче", только "отдача" здесь означает JS-рендер в
    # момент опроса, а не Python-рендер в `state()`: `/api/mgame/.../
    # state` не входит в состав этой задачи (см. отчёт), поэтому язык
    # рендера событий берётся из каталога, загруженного один раз при
    # первом открытии страницы (`store_game_multi`), а не из query
    # запроса опроса. Переключение языка на лету не перекрашивает уже
    # накопленную ленту заново — ограничение, а не баг данного этапа.
    "mgame.page_title_suffix": {
        "ru": "— командная смена", "ro": "— tură de echipă",
        "en": "— team shift",
    },
    "mgame.lobby.title": {
        "ru": "👥 Командная смена — до 10 игроков",
        "ro": "👥 Tură de echipă — până la 10 jucători",
        "en": "👥 Team shift — up to 10 players",
    },
    "mgame.lobby.name_placeholder": {
        "ru": "Имя студента", "ro": "Numele studentului",
        "en": "Student name",
    },
    "mgame.lobby.roblox_placeholder": {
        "ru": "Ник в Roblox (необязательно — для баллов команды)",
        "ro": "Nume Roblox (opțional — pentru puncte de echipă)",
        "en": "Roblox username (optional — for team points)",
    },
    "mgame.lobby.join_btn": {
        "ru": "Войти в смену", "ro": "Intră în tură", "en": "Join shift",
    },
    "mgame.lobby.add_ai_label": {
        "ru": "Добавить ИИ:", "ro": "Adaugă AI:", "en": "Add AI:",
    },
    "mgame.side.title": {
        "ru": "👥 Командная смена", "ro": "👥 Tură de echipă",
        "en": "👥 Team shift",
    },
    "mgame.side.lobby_status": {
        "ru": "лобби", "ro": "lobby", "en": "lobby",
    },
    "mgame.side.revenue_goal": {
        "ru": "выручка / цель", "ro": "venit / obiectiv",
        "en": "revenue / goal",
    },
    "mgame.side.time": {"ru": "время", "ro": "timp", "en": "time"},
    "mgame.side.reputation": {
        "ru": "репутация", "ro": "reputație", "en": "reputation",
    },
    "mgame.side.queue": {
        "ru": "очередь кассы", "ro": "coadă casă", "en": "register queue",
    },
    "mgame.side.team": {"ru": "Команда", "ro": "Echipă", "en": "Team"},
    "mgame.result.retry_btn": {
        "ru": "↻ Ещё смена", "ro": "↻ Încă o tură", "en": "↻ Another shift",
    },
    "mgame.role.cashier": {
        "ru": "Кассир", "ro": "Casier", "en": "Cashier",
    },
    "mgame.role.merch": {
        "ru": "Мерчандайзер", "ro": "Merchandiser", "en": "Merchandiser",
    },
    "mgame.role.cleaner": {
        "ru": "Клинер", "ro": "Cleaner", "en": "Cleaner",
    },
    "mgame.role.tech": {
        "ru": "Техник", "ro": "Tehnician", "en": "Technician",
    },
    "mgame.role.supervisor": {
        "ru": "Супервайзер", "ro": "Supervizor", "en": "Supervisor",
    },
    "mgame.role.cashier_word": {
        "ru": ["кассир", "кассира", "кассиров"],
        "ro": ["casier", "casieri", "de casieri"],
        "en": ["cashier", "cashiers"],
    },
    "mgame.role.merch_word": {
        "ru": ["мерчандайзер", "мерчандайзера", "мерчандайзеров"],
        "ro": ["merchandiser", "merchandiseri", "de merchandiseri"],
        "en": ["merchandiser", "merchandisers"],
    },
    "mgame.role.cleaner_word": {
        "ru": ["клинер", "клинера", "клинеров"],
        "ro": ["cleaner", "cleaneri", "de cleaneri"],
        "en": ["cleaner", "cleaners"],
    },
    "mgame.role.tech_word": {
        "ru": ["техник", "техника", "техников"],
        "ro": ["tehnician", "tehnicieni", "de tehnicieni"],
        "en": ["technician", "technicians"],
    },
    "mgame.role.supervisor_word": {
        "ru": ["супервайзер", "супервайзера", "супервайзеров"],
        "ro": ["supervizor", "supervizori", "de supervizori"],
        "en": ["supervisor", "supervisors"],
    },
    "mgame.lobby.free_label": {
        "ru": "своб.: ", "ro": "liber: ", "en": "free: ",
    },
    "mgame.lobby.room_line": {
        "ru": "{store} · комната «{code}» · роли: ",
        "ro": "{store} · camera «{code}» · roluri: ",
        "en": "{store} · room «{code}» · roles: ",
    },
    "mgame.api_hint": {
        # {api} — единственный настоящий плейсхолдер (подставляется в
        # браузере через tt(), см. game_multi.html); JSON-примеры в
        # фигурных скобках — буквальный текст, не форматируется: этот
        # ключ отдаётся клиенту сырым (`client_catalog` → t(lang, key)
        # без params), .format() здесь не вызывается вовсе, поэтому
        # скобки не нужно экранировать удвоением.
        "ru": 'API для внешних ИИ-агентов: POST {api}/join '
              '{"name","role","kind":"api"} → цикл GET {api}/state и '
              'POST {api}/action {"player","action":"serve|storeroom|'
              'restock|clean|fix_fridge|paper|move"}',
        "ro": 'API pentru agenți AI externi: POST {api}/join '
              '{"name","role","kind":"api"} → ciclu GET {api}/state și '
              'POST {api}/action {"player","action":"serve|storeroom|'
              'restock|clean|fix_fridge|paper|move"}',
        "en": 'API for external AI agents: POST {api}/join '
              '{"name","role","kind":"api"} → loop GET {api}/state and '
              'POST {api}/action {"player","action":"serve|storeroom|'
              'restock|clean|fix_fridge|paper|move"}',
    },
    "mgame.lobby.roster_label": {
        "ru": "В лобби:", "ro": "În lobby:", "en": "In lobby:",
    },
    "mgame.lobby.empty": {
        "ru": "пока никого", "ro": "deocamdată nimeni", "en": "no one yet",
    },
    "mgame.ai_suffix": {
        "ru": " (ИИ)", "ro": " (AI)", "en": " (AI)",
    },
    "mgame.table.player": {"ru": "Игрок", "ro": "Jucător", "en": "Player"},
    "mgame.table.role": {"ru": "Роль", "ro": "Rol", "en": "Role"},
    "mgame.table.shelves": {
        "ru": "Полки", "ro": "Rafturi", "en": "Shelves",
    },
    "mgame.table.cleaning": {
        "ru": "Уборка", "ro": "Curățenie", "en": "Cleaning",
    },
    "mgame.table.tech": {"ru": "Техника", "ro": "Tehnică", "en": "Tech"},
    "mgame.table.points": {"ru": "Баллы", "ro": "Puncte", "en": "Points"},
    "mgame.result.title_ok": {
        "ru": "✅ Командная смена пройдена!",
        "ro": "✅ Tura de echipă reușită!",
        "en": "✅ Team shift complete!",
    },
    "mgame.status.play": {
        "ru": "смена идёт", "ro": "tura este în desfășurare",
        "en": "shift in progress",
    },
    "mgame.status.ended": {
        "ru": "смена завершена", "ro": "tura s-a încheiat",
        "en": "shift ended",
    },
    "mgame.status.lobby": {
        "ru": "лобби — ждём игроков", "ro": "lobby — așteptăm jucători",
        "en": "lobby — waiting for players",
    },
    "mgame.you_suffix": {"ru": " (вы)", "ro": " (tu)", "en": " (you)"},
    "mgame.join_error_prefix": {
        "ru": "Не удалось войти: ", "ro": "Intrarea a eșuat: ",
        "en": "Failed to join: ",
    },
    "mgame.joined_label": {
        "ru": "✓ Вы в смене ({name})", "ro": "✓ Sunteți în tură ({name})",
        "en": "✓ You're on shift ({name})",
    },
    "mgame.label.sco_self": {
        "ru": "СКО (само)", "ro": "self-checkout (auto)",
        "en": "self-checkout (auto)",
    },
    "mgame.event.joined": {
        "ru": "👋 {name} вошёл в смену — {icon} {role}{ai}",
        "ro": "👋 {name} a intrat în tură — {icon} {role}{ai}",
        "en": "👋 {name} joined the shift — {icon} {role}{ai}",
    },
    "mgame.event.left": {
        "ru": "🚪 {name} покинул смену", "ro": "🚪 {name} a părăsit tura",
        "en": "🚪 {name} left the shift",
    },
    "mgame.event.started": {
        "ru": "▶ Смена началась! Команда: {n} {team_word}, цель {goal} L",
        "ro": "▶ Tura a început! Echipă: {n} {team_word}, obiectiv "
              "{goal} L",
        "en": "▶ Shift started! Team: {n} {team_word}, goal {goal} L",
    },
    "mgame.event.started.team_word": {
        "ru": ["чел.", "чел.", "чел."],
        "ro": ["membru", "membri", "de membri"],
        "en": ["member", "members"],
    },
    "mgame.event.disconnected": {
        "ru": "🚪 {name} отключился", "ro": "🚪 {name} s-a deconectat",
        "en": "🚪 {name} disconnected",
    },
    "mgame.event.fridge_alarm": {
        "ru": "🧊 {id}: тревога температуры!",
        "ro": "🧊 {id}: alarmă de temperatură!",
        "en": "🧊 {id}: temperature alarm!",
    },
    "mgame.event.finished_ok": {
        "ru": "✅ Смена пройдена! Выручка {money} L из {goal} L",
        "ro": "✅ Tură reușită! Venit {money} L din {goal} L",
        "en": "✅ Shift complete! Revenue {money} L of {goal} L",
    },
    "mgame.event.finished_fail": {
        "ru": "❌ План не выполнен. Выручка {money} L из {goal} L",
        "ro": "❌ Planul nu a fost îndeplinit. Venit {money} L din "
              "{goal} L",
        "en": "❌ Target missed. Revenue {money} L of {goal} L",
    },
    "mgame.fx.need_stock": {
        "ru": "нужен товар со склада!",
        "ro": "e nevoie de marfă din depozit!",
        "en": "need stock from the storeroom!",
    },

    # ---- новая презентация /presentation2: Кишинёв + топливный контур,
    # ИИ-табло, bon fiscal, трёхъязычность (старая /presentation не
    # трогается, см. docs/HANDOFF.md) ----
    "p2.page_title": {
        "ru": "planogram3d — презентация",
        "ro": "planogram3d — prezentare",
        "en": "planogram3d — presentation",
    },
    "p2.nav.demo": {"ru": "демо-система", "ro": "sistem demo", "en": "demo system"},
    "p2.nav.docs": {"ru": "документация", "ro": "documentație", "en": "documentation"},
    "p2.lbl.demo": {
        "ru": "🔗 Живое демо:", "ro": "🔗 Demo live:", "en": "🔗 Live demo:",
    },
    "p2.lbl.more": {
        "ru": "🔗 Подробнее:", "ro": "🔗 Detalii:", "en": "🔗 More:",
    },
    "p2.lbl.all": {
        "ru": "🔗 Всё сразу:", "ro": "🔗 Totul deodată:", "en": "🔗 Everything at once:",
    },
    "p2.lbl.process": {
        "ru": "🔗 Весь процесс вживую:", "ro": "🔗 Tot procesul, live:",
        "en": "🔗 The whole process, live:",
    },
    "p2.lbl.materials": {
        "ru": "🔗 Материалы:", "ro": "🔗 Materiale:", "en": "🔗 Materials:",
    },

    "p2.link.map": {
        "ru": "Карта сети 2D/3D", "ro": "Harta rețelei 2D/3D",
        "en": "Network map 2D/3D",
    },
    "p2.link.delivery": {"ru": "Доставка", "ro": "Livrare", "en": "Delivery"},
    "p2.link.fuel": {
        "ru": "Топливная сеть", "ro": "Rețeaua de combustibil",
        "en": "Fuel network",
    },
    "p2.link.trainer": {"ru": "Тренажёр", "ro": "Simulator", "en": "Trainer"},
    "p2.link.docs": {
        "ru": "Документация", "ro": "Documentație", "en": "Documentation",
    },

    # -- слайд 1: титул --
    "p2.s1.tag": {
        "ru": "Цифровой двойник розничной сети «Гурман» в Кишинёве и "
              "топливной сети АЗС по всей Молдове",
        "ro": "Geamănul digital al rețelei de retail «Gurman» din Chișinău "
              "și al rețelei de stații de alimentare din toată Moldova",
        "en": "Digital twin of the «Gurman» retail network in Chisinau and "
              "a nationwide Moldova fuel-station network",
    },
    "p2.s1.desc": {
        "ru": "3D-планограммы и контроль соответствия · живая карта сети "
              "Кишинёва · датчики торгового зала · игровой тренажёр "
              "персонала и Roblox · доставка с ИИ-табло прибытия · "
              "топливная сеть АЗС Молдовы · молдавский фискальный чек "
              "(bon fiscal) · три языка интерфейса. Все ссылки в этой "
              "презентации ведут в работающую демо-систему.",
        "ro": "Planograme 3D și control de conformitate · harta live a "
              "rețelei din Chișinău · senzori ai sălii de vânzare · "
              "simulator de instruire a personalului și Roblox · livrare "
              "cu tablou de sosire bazat pe IA · rețea de stații de "
              "alimentare din toată Moldova · bon fiscal moldovenesc · "
              "interfață în trei limbi. Toate linkurile din această "
              "prezentare duc la sistemul demo funcțional.",
        "en": "3D planograms and compliance checks · live Chisinau network "
              "map · store-floor sensors · a gamified staff trainer and "
              "Roblox · delivery with an AI arrival board · a "
              "Moldova-wide fuel-station network · a Moldovan fiscal "
              "receipt (bon fiscal) · a three-language interface. Every "
              "link in this presentation opens the working demo system.",
    },

    # -- слайд 2: возможности --
    "p2.s2.title": {
        "ru": "Шесть работающих блоков платформы",
        "ro": "Șase blocuri funcționale ale platformei",
        "en": "Six working platform building blocks",
    },
    "p2.s2.c1.title": {"ru": "🧊 3D-планограммы", "ro": "🧊 Planograme 3D",
                        "en": "🧊 3D planograms"},
    "p2.s2.c1.desc": {
        "ru": "Текущие продажи с теплокартой остатков и утверждённая "
              "выкладка по поставщикам; карточки SKU при наведении.",
        "ro": "Vânzări curente cu hartă termică a stocurilor și "
              "planograma aprobată pe furnizori; carduri SKU la hover.",
        "en": "Current sales with a stock heat-map and the approved "
              "layout by supplier; SKU cards on hover.",
    },
    "p2.s2.c1.link": {
        "ru": "Открыть 3D-планограмму →", "ro": "Deschide planograma 3D →",
        "en": "Open the 3D planogram →",
    },
    "p2.s2.c2.title": {"ru": "✅ Контроль соответствия",
                        "ro": "✅ Control de conformitate",
                        "en": "✅ Compliance control"},
    "p2.s2.c2.desc": {
        "ru": "Регламент, контракты, факт против плана, OOS — отчёт под "
              "3D-сценой, 16 нарушений в демо.",
        "ro": "Regulament, contracte, fapt vs. plan, OOS — raport sub "
              "scena 3D, 16 abateri în demo.",
        "en": "In-house rules, contracts, plan-vs-actual, OOS — a report "
              "beneath the 3D scene, 16 violations in the demo.",
    },
    "p2.s2.c2.link": {
        "ru": "Отчёт о нарушениях →", "ro": "Raportul abaterilor →",
        "en": "Violation report →",
    },
    "p2.s2.c3.title": {"ru": "🗺 Живая карта Кишинёва",
                        "ro": "🗺 Harta live a Chișinăului",
                        "en": "🗺 Live Chisinau map"},
    "p2.s2.c3.desc": {
        "ru": "Реальный город (OSM) в 2D/3D, эмуляция торгового дня, "
              "Zabbix, логистический центр с рейсами.",
        "ro": "Orașul real (OSM) în 2D/3D, emularea zilei comerciale, "
              "Zabbix, centrul logistic cu curse.",
        "en": "The real city (OSM) in 2D/3D, a simulated trading day, "
              "Zabbix, a distribution centre with runs.",
    },
    "p2.s2.c3.link": {
        "ru": "Карта сети →", "ro": "Harta rețelei →", "en": "Network map →",
    },
    "p2.s2.c4.title": {"ru": "📡 Датчики зала", "ro": "📡 Senzorii sălii",
                        "en": "📡 Store-floor sensors"},
    "p2.s2.c4.desc": {
        "ru": "Очереди, ТСД по BLE/LoRa, холодильники, расходники, оценка "
              "трафика по датчикам входа/выхода.",
        "ro": "Cozi, terminale mobile pe BLE/LoRa, frigidere, "
              "consumabile, estimarea traficului din senzorii de "
              "intrare/ieșire.",
        "en": "Queues, BLE/LoRa handheld terminals, fridges, "
              "consumables, footfall estimated from entry/exit sensors.",
    },
    "p2.s2.c4.link": {
        "ru": "Симуляция зала →", "ro": "Simularea sălii →",
        "en": "Store-floor simulation →",
    },
    "p2.s2.c5.title": {"ru": "🎓 Тренажёр + Roblox",
                        "ro": "🎓 Simulator + Roblox",
                        "en": "🎓 Trainer + Roblox"},
    "p2.s2.c5.desc": {
        "ru": "Игра-обучение кассиров; баллы, бейджи и лидерборд команды "
              "через Open Cloud.",
        "ro": "Joc de instruire a casierilor; puncte, insigne și "
              "clasament al echipei prin Open Cloud.",
        "en": "A training game for cashiers; points, badges and a team "
              "leaderboard via Open Cloud.",
    },
    "p2.s2.c5.link": {
        "ru": "Играть смену →", "ro": "Joacă un schimb →",
        "en": "Play a shift →",
    },
    "p2.s2.c6.title": {"ru": "🛵 Доставка", "ro": "🛵 Livrare",
                        "en": "🛵 Delivery"},
    "p2.s2.c6.desc": {
        "ru": "Сборка, маршруты, диаграмма Ганта, ИИ-табло прибытия и "
              "bon fiscal при вручении.",
        "ro": "Asamblare, rute, diagramă Gantt, tablou de sosire cu IA "
              "și bon fiscal la predare.",
        "en": "Picking, routes, a Gantt chart, an AI arrival board and a "
              "fiscal receipt on hand-over.",
    },
    "p2.s2.c6.link": {
        "ru": "Дашборд доставки →", "ro": "Panoul de livrare →",
        "en": "Delivery dashboard →",
    },

    # -- слайд 3: архитектура --
    "p2.s3.title": {
        "ru": "Архитектура: встраиваемое ядро и надстройки",
        "ro": "Arhitectură: nucleu integrabil și extensii",
        "en": "Architecture: an embeddable core plus extensions",
    },
    "p2.s3.box1.title": {"ru": "planogram3d.core", "ro": "planogram3d.core",
                          "en": "planogram3d.core"},
    "p2.s3.box1.desc": {
        "ru": "модель данных Store · проверки соответствия · 3D-сцены "
              "(Plotly) · отчёты HTML",
        "ro": "modelul de date Store · verificări de conformitate · "
              "scene 3D (Plotly) · rapoarte HTML",
        "en": "the Store data model · compliance checks · 3D scenes "
              "(Plotly) · HTML reports",
    },
    "p2.s3.box1.note": {
        "ru": "зависимость — только plotly", "ro": "singura dependință — plotly",
        "en": "only dependency — plotly",
    },
    "p2.s3.box2.title": {"ru": "planogram3d.webapp", "ro": "planogram3d.webapp",
                          "en": "planogram3d.webapp"},
    "p2.s3.box2.desc": {
        "ru": "карта сети · симуляция зала · тренажёр · доставка · "
              "топливный контур · Zabbix · Roblox-команда (Flask)",
        "ro": "harta rețelei · simularea sălii · simulator · livrare · "
              "contur de combustibil · Zabbix · echipa Roblox (Flask)",
        "en": "network map · store-floor simulation · trainer · "
              "delivery · fuel loop · Zabbix · the Roblox team (Flask)",
    },
    "p2.s3.box2.note": {
        "ru": "REST API для интеграций", "ro": "API REST pentru integrări",
        "en": "REST API for integrations",
    },
    "p2.s3.box3.title": {"ru": "planogram3d.robloxkit",
                          "ro": "planogram3d.robloxkit",
                          "en": "planogram3d.robloxkit"},
    "p2.s3.box3.desc": {
        "ru": "конвертер сцен в .rbxlx · Luau-скрипты тренажёра · "
              "place-файлы для Roblox Studio",
        "ro": "convertor de scene în .rbxlx · scripturi Luau ale "
              "simulatorului · fișiere place pentru Roblox Studio",
        "en": "a scene-to-.rbxlx converter · trainer Luau scripts · "
              "place files for Roblox Studio",
    },
    "p2.s3.box3.note": {
        "ru": "без зависимостей", "ro": "fără dependințe", "en": "no dependencies",
    },
    "p2.s3.card.title": {
        "ru": "Один объект Store — все данные системы",
        "ro": "Un singur obiect Store — toate datele sistemului",
        "en": "One Store object — all the system's data",
    },
    "p2.s3.card.desc": {
        "ru": "Магазины, стеллажи, товары, поставщики, контракты, "
              "планограммы, продажи, а также топливные станции и рейсы "
              "бензовозов. Наполняется из учётной системы (в том числе "
              "Artgranit), БД или CSV; свои правила — через extra_checks.",
        "ro": "Magazine, rafturi, produse, furnizori, contracte, "
              "planograme, vânzări, precum și stații de combustibil și "
              "curse de cisterne. Se alimentează din sistemul de "
              "evidență (inclusiv Artgranit), BD sau CSV; reguli proprii "
              "— prin extra_checks.",
        "en": "Stores, shelving, products, suppliers, contracts, "
              "planograms, sales, plus fuel stations and tanker runs. "
              "Populated from an accounting system (including "
              "Artgranit), a database or CSV; custom rules via "
              "extra_checks.",
    },
    "p2.s3.link.library": {
        "ru": "Справочник API", "ro": "Referință API", "en": "API reference",
    },
    "p2.s3.link.integration": {
        "ru": "Руководство по интеграции", "ro": "Ghid de integrare",
        "en": "Integration guide",
    },
    "p2.s3.link.core": {
        "ru": "Пример работы ядра", "ro": "Exemplu de funcționare a nucleului",
        "en": "Core in action",
    },

    # -- слайд 3b: 3D для ERP --
    "p2.s3b.title": {
        "ru": "3D-инновация для ERP — самодельным модулем",
        "ro": "Inovație 3D pentru ERP — printr-un modul propriu",
        "en": "3D innovation for ERP — a home-grown module",
    },
    "p2.s3b.sub": {
        "ru": "ERP знает всё, но показывает таблицами. Половина данных "
              "ритейла и топливной логистики пространственна — полка, "
              "зал, город, трасса.",
        "ro": "ERP știe totul, dar afișează în tabele. Jumătate din "
              "datele retailului și logisticii de combustibil sunt "
              "spațiale — raft, sală, oraș, șosea.",
        "en": "ERP knows everything but shows it as tables. Half of "
              "retail and fuel-logistics data is spatial — a shelf, a "
              "floor, a city, a road.",
    },
    "p2.s3b.li1": {
        "ru": "3D переносит интерпретацию с человека на систему: пустая "
              "полка краснеет, бензовоз едет по трассе, очередь видна "
              "как очередь",
        "ro": "3D mută interpretarea de la om la sistem: raftul gol se "
              "colorează roșu, cisterna se deplasează pe șosea, coada "
              "se vede ca o coadă",
        "en": "3D shifts interpretation from the person to the system: "
              "an empty shelf turns red, a tanker drives along the "
              "road, a queue looks like a queue",
    },
    "p2.s3b.li2": {
        "ru": "Шесть контуров ERP одним модулем: мерчандайзинг, "
              "запасы/РЦ, IoT-мониторинг, доставка с ИИ-табло, обучение "
              "персонала, топливная логистика — на одних данных",
        "ro": "Șase contururi ERP într-un singur modul: merchandising, "
              "stocuri/DC, monitorizare IoT, livrare cu tablou IA, "
              "instruirea personalului, logistica de combustibil — pe "
              "aceleași date",
        "en": "Six ERP domains in one module: merchandising, "
              "stock/DC, IoT monitoring, delivery with an AI board, "
              "staff training, fuel logistics — on the same data",
    },
    "p2.s3b.li3": {
        "ru": "Самодельный — это стратегия: ядро ~850 строк Python, "
              "одна зависимость, без лицензий и чужих облаков",
        "ro": "Propriu — este o strategie: nucleu de ~850 de linii "
              "Python, o singură dependință, fără licențe și cloud-uri "
              "străine",
        "en": "Home-grown is a strategy: a ~850-line Python core, one "
              "dependency, no licences and no third-party clouds",
    },
    "p2.s3b.li4": {
        "ru": "Интеграция с любой ERP (1С, SAP, Odoo, Artgranit, "
              "самописной) через один объект Store: адаптер CSV/REST в "
              "десятки строк",
        "ro": "Integrare cu orice ERP (1С, SAP, Odoo, Artgranit, "
              "sistem propriu) printr-un singur obiect Store: adaptor "
              "CSV/REST în câteva zeci de linii",
        "en": "Integration with any ERP (1C, SAP, Odoo, Artgranit, an "
              "in-house one) through one Store object: a CSV/REST "
              "adapter in a few dozen lines",
    },
    "p2.s3b.li5": {
        "ru": "Эмуляторы всех внешних контуров: демо работает в первый "
              "день, интеграции подключаются по готовности — как уже "
              "сделано с Artgranit",
        "ro": "Emulatoare pentru toate contururile externe: demo-ul "
              "funcționează din prima zi, integrările se conectează pe "
              "măsură ce sunt gata — cum s-a făcut deja cu Artgranit",
        "en": "Emulators for every external loop: the demo works from "
              "day one, integrations plug in when ready — as already "
              "done with Artgranit",
    },
    "p2.s3b.li6": {
        "ru": "Дорожка: PoC на своих данных за 2 недели → пилотный "
              "магазин за месяц → сеть за квартал",
        "ro": "Traseu: PoC pe datele proprii în 2 săptămâni → magazin "
              "pilot într-o lună → rețea într-un trimestru",
        "en": "Roadmap: a PoC on your own data in 2 weeks → a pilot "
              "store in a month → the whole network in a quarter",
    },
    "p2.s3b.stat1": {
        "ru": "строк — ядро<br>3D и проверок",
        "ro": "linii — nucleul<br>3D și verificărilor",
        "en": "lines — the 3D<br>and checks core",
    },
    "p2.s3b.stat2": {
        "ru": "объект Store —<br>вся интеграция",
        "ro": "obiect Store —<br>toată integrarea",
        "en": "Store object —<br>the whole integration",
    },
    "p2.s3b.stat3": {
        "ru": "лицензий и<br>внешних облаков",
        "ro": "licențe și<br>cloud-uri externe",
        "en": "licences and<br>external clouds",
    },
    "p2.s3b.link.article": {
        "ru": "Статья «3D для ERP»", "ro": "Articolul «3D pentru ERP»",
        "en": "Article «3D for ERP»",
    },
    "p2.s3b.link.example": {
        "ru": "Живой пример: планограмма из данных учёта",
        "ro": "Exemplu live: planograma din datele de evidență",
        "en": "Live example: a planogram built from accounting data",
    },
    "p2.s3b.link.integration": {
        "ru": "Как подключить свою ERP", "ro": "Cum conectezi propriul ERP",
        "en": "How to connect your own ERP",
    },

    # -- слайд 4: 3D-планограмма --
    "p2.s4.title": {
        "ru": "3D-планограмма: продажи и утверждённая выкладка",
        "ro": "Planograma 3D: vânzări și planograma aprobată",
        "en": "3D planogram: sales and the approved layout",
    },
    "p2.s4.li1": {
        "ru": "Два режима одной сцены — «Текущее состояние продаж» и "
              "«Утверждённая планограмма», переключение кнопками",
        "ro": "Două regimuri ale aceleiași scene — „Starea curentă a "
              "vânzărilor” și „Planograma aprobată”, comutare prin "
              "butoane",
        "en": "Two modes of one scene — “Current sales state” and "
              "“Approved planogram”, switched with buttons",
    },
    "p2.s4.li2": {
        "ru": "Теплокарта остатков: зелёный — полная полка, красный "
              "полупрозрачный — out-of-stock",
        "ro": "Hartă termică a stocurilor: verde — raft plin, roșu "
              "semitransparent — out-of-stock",
        "en": "A stock heat-map: green — a full shelf, translucent red "
              "— out of stock",
    },
    "p2.s4.li3": {
        "ru": "Глубина стопки товара пропорциональна остатку",
        "ro": "Adâncimea stivei de produs este proporțională cu stocul",
        "en": "The stack depth of goods is proportional to the stock "
              "level",
    },
    "p2.s4.li4": {
        "ru": "Утверждённая выкладка раскрашена по поставщикам — видны "
              "доли полки по контрактам",
        "ro": "Planograma aprobată este colorată pe furnizori — se văd "
              "cotele de raft din contracte",
        "en": "The approved layout is colour-coded by supplier — "
              "contract shelf-shares are visible",
    },
    "p2.s4.li5": {
        "ru": "Карточка при наведении: SKU, поставщик, фейсинги, "
              "остаток, скорость продаж, запас в днях",
        "ro": "Card la hover: SKU, furnizor, facinguri, stoc, viteza de "
              "vânzare, rezervă în zile",
        "en": "A hover card: SKU, supplier, facings, stock, sales "
              "velocity, days of cover",
    },
    "p2.s4.li6": {
        "ru": "Отчёт — автономный HTML-файл: можно отправить письмом",
        "ro": "Raportul — un fișier HTML autonom: poate fi trimis prin "
              "e-mail",
        "en": "The report is a self-contained HTML file — it can be "
              "emailed",
    },
    "p2.s4.stat": {
        "ru": "режима сцены<br>в одном отчёте",
        "ro": "regimuri ale scenei<br>într-un singur raport",
        "en": "scene modes<br>in one report",
    },
    "p2.s4.link1": {"ru": "Магазин №17 · Штефан чел Маре",
                     "ro": "Magazinul nr. 17 · Ștefan cel Mare",
                     "en": "Store 17 · Ștefan cel Mare"},
    "p2.s4.link2": {"ru": "Магазин №3 · Измаил", "ro": "Magazinul nr. 3 · Ismail",
                     "en": "Store 3 · Ismail"},
    "p2.s4.link3": {"ru": "Магазин №8 · Рышкановка",
                     "ro": "Magazinul nr. 8 · Râșcani", "en": "Store 8 · Rîșcani"},

    # -- слайд 5: соответствие --
    "p2.s5.title": {
        "ru": "Контроль соответствия: регламент и контракты",
        "ro": "Control de conformitate: regulament și contracte",
        "en": "Compliance control: rules and contracts",
    },
    "p2.s5.li1": {
        "ru": "Внутренний регламент — вес на верхних полках, габариты в "
              "просвете, переполнение и пересечения выкладок",
        "ro": "Regulament intern — greutate pe rafturile de sus, "
              "gabarite în lumina raftului, supraîncărcare și "
              "suprapuneri de expunere",
        "en": "In-house rules — weight on top shelves, clearance "
              "dimensions, overfilled or overlapping layouts",
    },
    "p2.s5.li2": {
        "ru": "Контракты с поставщиками — минимальная доля полки, "
              "обязательные SKU, уровень глаз",
        "ro": "Contracte cu furnizorii — cotă minimă de raft, SKU "
              "obligatorii, nivelul ochilor",
        "en": "Supplier contracts — minimum shelf-share, mandatory "
              "SKUs, eye level",
    },
    "p2.s5.li3": {
        "ru": "Факт против планограммы — отсутствующие и лишние "
              "позиции, расхождение фейсингов",
        "ro": "Fapt vs. planogramă — poziții lipsă sau în plus, "
              "discrepanțe de facinguri",
        "en": "Actual vs. planned — missing or extra items, facing "
              "mismatches",
    },
    "p2.s5.li4": {
        "ru": "Продажи — out-of-stock, низкая заполненность, запас "
              "меньше дневных продаж",
        "ro": "Vânzări — out-of-stock, umplere scăzută, stoc sub "
              "vânzările zilnice",
        "en": "Sales — out-of-stock, low fill rate, stock below daily "
              "sales",
    },
    "p2.s5.li5": {
        "ru": "Каждое нарушение с адресом: стеллаж, полка, SKU, причина",
        "ro": "Fiecare abatere are o „adresă”: raft, poliță, SKU, motiv",
        "en": "Every violation has an address: rack, shelf, SKU, "
              "reason",
    },
    "p2.s5.stat": {
        "ru": "нарушений находит<br>демо-магазин (6 критичных)",
        "ro": "abateri găsește<br>magazinul demo (6 critice)",
        "en": "violations found<br>in the demo store (6 critical)",
    },
    "p2.s5.link.report": {
        "ru": "Отчёт под 3D-сценой", "ro": "Raportul sub scena 3D",
        "en": "The report beneath the 3D scene",
    },
    "p2.s5.link.rules": {
        "ru": "Свои правила (extra_checks)", "ro": "Reguli proprii (extra_checks)",
        "en": "Custom rules (extra_checks)",
    },

    # -- слайд 6: карта сети --
    "p2.s6.title": {
        "ru": "Живая карта Кишинёва, Zabbix и логистический центр",
        "ro": "Harta live a Chișinăului, Zabbix și centrul logistic",
        "en": "Live Chisinau map, Zabbix and the distribution centre",
    },
    "p2.s6.li1": {
        "ru": "Карта из OpenStreetMap: улицы, здания Кишинёва — "
              "автономна, интернет не нужен; 2D/3D с выдавливанием по "
              "этажности",
        "ro": "Hartă din OpenStreetMap: străzi, clădiri din Chișinău — "
              "autonomă, nu necesită internet; 2D/3D cu extrudare pe "
              "număr de etaje",
        "en": "A map from OpenStreetMap: Chisinau streets and "
              "buildings — self-contained, no internet needed; 2D/3D "
              "extruded by floor count",
    },
    "p2.s6.li2": {
        "ru": "Эмуляция торгового дня (1 с = 10 мин): продажи и выручка "
              "в молдавских леях (L), пустые полки, лента событий",
        "ro": "Emularea zilei comerciale (1 s = 10 min): vânzări și "
              "venituri în lei moldovenești (L), rafturi goale, flux de "
              "evenimente",
        "en": "A simulated trading day (1 s = 10 min): sales and "
              "revenue in Moldovan lei (L), empty shelves, an event "
              "feed",
    },
    "p2.s6.li3": {
        "ru": "Zabbix: бейдж активных проблем на каждом магазине, "
              "список в карточке (реальный API или эмуляция)",
        "ro": "Zabbix: insignă cu probleme active pe fiecare magazin, "
              "listă în card (API real sau emulare)",
        "en": "Zabbix: an active-problems badge on every store, listed "
              "in its card (a real API or an emulation)",
    },
    "p2.s6.li4": {
        "ru": "РЦ-буфер: пустая полка → заказ → грузовик по улицам "
              "Кишинёва → пополнение; перезаказ у поставщиков",
        "ro": "Buffer DC: raft gol → comandă → camion pe străzile "
              "Chișinăului → reaprovizionare; recomandă la furnizori",
        "en": "A DC buffer: empty shelf → order → a truck through "
              "Chisinau streets → restock; supplier re-ordering",
    },
    "p2.s6.li5": {
        "ru": "Игровой вход в магазин: подлёт камеры, «дверь», "
              "интерьер с тремя вкладками",
        "ro": "Intrare în magazin, în stil de joc: zbor de cameră, "
              "„ușă”, interior cu trei file",
        "en": "A gamified store entry: a camera fly-in, a “door”, an "
              "interior with three tabs",
    },
    "p2.s6.stat1": {
        "ru": "магазинов сети<br>в Кишинёве",
        "ro": "magazine ale rețelei<br>din Chișinău",
        "en": "network stores<br>in Chisinau",
    },
    "p2.s6.stat2": {
        "ru": "рейсы РЦ по улицам<br>города, в реальном времени",
        "ro": "curse DC pe străzile<br>orașului, în timp real",
        "en": "DC runs on city<br>streets, in real time",
    },
    "p2.s6.link.map": {
        "ru": "Карта сети (3D + Zabbix + РЦ)",
        "ro": "Harta rețelei (3D + Zabbix + DC)",
        "en": "Network map (3D + Zabbix + DC)",
    },
    "p2.s6.link.api": {
        "ru": "API состояния сети (JSON)", "ro": "API stare rețea (JSON)",
        "en": "Network state API (JSON)",
    },

    # -- слайд 7: симуляция зала --
    "p2.s7.title": {
        "ru": "Симуляция зала: датчики магазина на одной схеме",
        "ro": "Simularea sălii: senzorii magazinului pe o singură schemă",
        "en": "Store-floor simulation: every sensor on one screen",
    },
    "p2.s7.li1": {
        "ru": "Покупатели ходят к реальным стеллажам планограммы, "
              "весам, кассам и СКО",
        "ro": "Clienții merg la rafturile reale ale planogramei, la "
              "cântare, case și punctul de control",
        "en": "Shoppers walk to the planogram's real racks, scales, "
              "tills and the checkpoint",
    },
    "p2.s7.li2": {
        "ru": "Очереди у касс в реальном времени; оценка трафика: "
              "датчики входа/выхода − очереди = равномерно по залу",
        "ro": "Cozi la case în timp real; estimarea traficului: "
              "senzori intrare/ieșire − cozi = distribuit uniform în "
              "sală",
        "en": "Real-time checkout queues; footfall estimate: "
              "entry/exit sensors minus queues = spread evenly over the "
              "floor",
    },
    "p2.s7.li3": {
        "ru": "ТСД: BLE-маяки (±0.5–1 м) в торговой зоне, LoRa (±2–3.5 "
              "м) на остальной площади, круги точности",
        "ro": "Terminale mobile: beacon-uri BLE (±0.5–1 m) în zona de "
              "vânzare, LoRa (±2–3.5 m) pe restul suprafeței, cercuri de "
              "precizie",
        "en": "Handhelds: BLE beacons (±0.5–1 m) on the sales floor, "
              "LoRa (±2–3.5 m) elsewhere, accuracy circles",
    },
    "p2.s7.li4": {
        "ru": "Холодильники: температура, дверца, компрессор, тревоги; "
              "зоны скоропорта выделены",
        "ro": "Frigidere: temperatură, ușă, compresor, alarme; zonele "
              "de produse perisabile sunt evidențiate",
        "en": "Fridges: temperature, door, compressor, alarms; "
              "perishable zones are highlighted",
    },
    "p2.s7.li5": {
        "ru": "Расходники: лента касс/весов, кульки — заявки на замену",
        "ro": "Consumabile: bandă case/cântare, pungi — cereri de "
              "înlocuire",
        "en": "Consumables: till/scale rolls, bags — replacement "
              "requests",
    },
    "p2.s7.li6": {
        "ru": "Единая шина событий: эмулятор или реальные кассы/CCTV "
              "(POST /api/instore/&lt;id&gt;/ingest)",
        "ro": "O singură magistrală de evenimente: emulator sau case "
              "reale/CCTV (POST /api/instore/&lt;id&gt;/ingest)",
        "en": "One event bus: an emulator or real tills/CCTV (POST "
              "/api/instore/&lt;id&gt;/ingest)",
    },
    "p2.s7.stat": {
        "ru": "типов событий<br>от реальных систем",
        "ro": "tipuri de evenimente<br>din sisteme reale",
        "en": "event types<br>from real systems",
    },
    "p2.s7.link.hall": {
        "ru": "Зал магазина №17", "ro": "Sala magazinului nr. 17",
        "en": "Store 17 floor",
    },
    "p2.s7.link.api": {
        "ru": "Поток состояния (JSON)", "ro": "Flux de stare (JSON)",
        "en": "State stream (JSON)",
    },

    # -- слайд 8: тренажёр + Roblox --
    "p2.s8.title": {
        "ru": "Тренажёр персонала и мотивация в Roblox",
        "ro": "Simulator pentru personal și motivare în Roblox",
        "en": "Staff trainer and Roblox motivation",
    },
    "p2.s8.li1": {
        "ru": "Игра в жанре тайм-менеджмента: склад → полки → касса, "
              "уборка, лента, холодильники",
        "ro": "Joc de tip time-management: depozit → rafturi → casă, "
              "curățenie, bandă, frigidere",
        "en": "A time-management game: storeroom → shelves → till, "
              "cleaning, the belt, fridges",
    },
    "p2.s8.li2": {
        "ru": "Покупатели с терпением ❤ — уходят злыми, если ждать",
        "ro": "Clienți cu răbdare ❤ — pleacă supărați dacă așteaptă",
        "en": "Shoppers have patience ❤ — they leave angry if kept "
              "waiting",
    },
    "p2.s8.li3": {
        "ru": "3 смены-уровня, звёзды, разбор ошибок и советы в конце",
        "ro": "3 schimburi-nivel, stele, analiza greșelilor și sfaturi "
              "la final",
        "en": "3 shift levels, stars, an end-of-shift error review and "
              "tips",
    },
    "p2.s8.li4": {
        "ru": "Регистрация: имя + ник Roblox; баллы и бейджи за кейсы",
        "ro": "Înregistrare: nume + nick Roblox; puncte și insigne "
              "pentru cazuri",
        "en": "Sign-up: a name plus a Roblox nickname; points and "
              "badges per scenario",
    },
    "p2.s8.li5": {
        "ru": "Open Cloud: DataStore + MessagingService — поощрение "
              "видно прямо в Roblox-опыте",
        "ro": "Open Cloud: DataStore + MessagingService — recompensele "
              "se văd direct în experiența Roblox",
        "en": "Open Cloud: DataStore + MessagingService — rewards show "
              "up right inside the Roblox experience",
    },
    "p2.s8.li6": {
        "ru": "Конвертер robloxkit: зал с реальной планограммой → "
              ".rbxlx для Roblox Studio",
        "ro": "Convertorul robloxkit: sala cu planograma reală → "
              ".rbxlx pentru Roblox Studio",
        "en": "The robloxkit converter: the floor with a real "
              "planogram → .rbxlx for Roblox Studio",
    },
    "p2.s8.stat1": {
        "ru": "смены-уровня<br>обучения", "ro": "schimburi-nivel<br>de instruire",
        "en": "training<br>shift levels",
    },
    "p2.s8.stat2": {
        "ru": "бейджа<br>команды", "ro": "insigne<br>de echipă",
        "en": "team<br>badges",
    },
    "p2.s8.link.play": {"ru": "Сыграть смену", "ro": "Joacă un schimb",
                         "en": "Play a shift"},
    "p2.s8.link.team": {"ru": "Лидерборд команды", "ro": "Clasamentul echipei",
                         "en": "Team leaderboard"},
    "p2.s8.link.api": {"ru": "API команды (JSON)", "ro": "API echipă (JSON)",
                        "en": "Team API (JSON)"},

    # -- слайд 9: доставка --
    "p2.s9.title": {
        "ru": "Интернет-заказы: сборка → маршруты → Гант → GPS → чек",
        "ro": "Comenzi online: asamblare → rute → Gantt → GPS → bon",
        "en": "Online orders: picking → routes → Gantt → GPS → receipt",
    },
    "p2.s9.li1": {
        "ru": "Заказы привязываются к ближайшему магазину, сборка по "
              "планограмме",
        "ro": "Comenzile se leagă de cel mai apropiat magazin, "
              "asamblare după planogramă",
        "en": "Orders attach to the nearest store, picking follows the "
              "planogram",
    },
    "p2.s9.li2": {
        "ru": "Группировка в маршруты по 2–4 адреса («ближайший "
              "сосед»)",
        "ro": "Gruparea în rute de 2–4 adrese („cel mai apropiat "
              "vecin”)",
        "en": "Grouping into routes of 2–4 addresses (“nearest "
              "neighbour”)",
    },
    "p2.s9.li3": {
        "ru": "Диаграмма Ганта: план/факт каждого плеча, линия «сейчас», "
              "опоздания красным",
        "ro": "Diagramă Gantt: plan/fapt pentru fiecare etapă, linia "
              "„acum”, întârzierile în roșu",
        "en": "A Gantt chart: plan vs. actual per leg, a “now” line, "
              "delays in red",
    },
    "p2.s9.li4": {
        "ru": "Курьеры на карте по GPS из приложения "
              "(POST /api/delivery/gps); без телеметрии — эмуляция",
        "ro": "Curieri pe hartă după GPS din aplicație "
              "(POST /api/delivery/gps); fără telemetrie — emulare",
        "en": "Couriers on the map by GPS from the app "
              "(POST /api/delivery/gps); an emulation without telemetry",
    },
    "p2.s9.li5": {
        "ru": "Чек в момент вручения — bon fiscal по молдавскому "
              "законодательству (HG 141/2019); печатная форма 80 мм",
        "ro": "Bonul la predare — bon fiscal conform legislației "
              "moldovenești (HG 141/2019); format tipărit de 80 mm",
        "en": "A receipt on hand-over — a Moldovan bon fiscal (HG "
              "141/2019); an 80 mm printed slip",
    },
    "p2.s9.stat": {
        "ru": "варианта курьерского<br>приложения",
        "ro": "variante de aplicație<br>pentru curier",
        "en": "courier app<br>variants",
    },
    "p2.s9.link.dash": {"ru": "Дашборд доставки", "ro": "Panoul de livrare",
                         "en": "Delivery dashboard"},
    "p2.s9.link.receipt": {
        "ru": "Последний bon fiscal", "ro": "Ultimul bon fiscal",
        "en": "Latest fiscal receipt",
    },
    "p2.s9.link.api": {"ru": "API доставки (JSON)", "ro": "API livrare (JSON)",
                        "en": "Delivery API (JSON)"},

    # -- слайд 10: ИИ-табло --
    "p2.s10.title": {
        "ru": "ИИ-табло прибытия: каждый пункт видит свой транспорт",
        "ro": "Tablou de sosire cu IA: fiecare punct își vede "
              "transportul",
        "en": "AI arrival board: every point sees its own transport",
    },
    "p2.s10.sub": {
        "ru": "по аналогии с «умными остановками» городского транспорта "
              "(Urban Way, Бельцы · EIT Urban Mobility): GPS-телеметрия "
              "машин → ИИ-модель → онлайн-табло на пункте",
        "ro": "prin analogie cu „stațiile inteligente” de transport "
              "public (Urban Way, Bălți · EIT Urban Mobility): "
              "telemetrie GPS a mașinilor → model IA → tablou online la "
              "punct",
        "en": "by analogy with “smart stops” for city transit (Urban "
              "Way, Bălți · EIT Urban Mobility): vehicle GPS telemetry "
              "→ an AI model → an online board at the point",
    },
    "p2.s10.li1": {
        "ru": "Магазин: табло машин поставщиков и РЦ прямо в карточке "
              "на карте — время прибытия, ±σ, прогресс рейса",
        "ro": "Magazin: tabloul mașinilor furnizorilor și DC direct în "
              "cardul de pe hartă — ora de sosire, ±σ, progresul cursei",
        "en": "Store: a board of supplier and DC vehicles right in the "
              "map card — ETA, ±σ, run progress",
    },
    "p2.s10.li2": {
        "ru": "Адрес покупателя: клик по точке на дашборде доставки — "
              "курьер, позиция в очереди, ИИ-время против плана, живое "
              "обновление",
        "ro": "Adresa clientului: clic pe punctul de pe panoul de "
              "livrare — curier, poziția în coadă, ora IA vs. plan, "
              "actualizare live",
        "en": "Customer address: click a point on the delivery "
              "dashboard — courier, queue position, AI time vs. plan, "
              "live updates",
    },
    "p2.s10.li3": {
        "ru": "Модель обучается онлайн на телеметрии каждого "
              "завершённого плеча: EWMA-скорости с дисперсией, "
              "коэффициенты трафика по часу суток, длительность "
              "вручения",
        "ro": "Modelul învață online din telemetria fiecărei etape "
              "finalizate: viteze EWMA cu dispersie, coeficienți de "
              "trafic pe ora zilei, durata predării",
        "en": "The model trains online on every completed leg's "
              "telemetry: EWMA speeds with variance, hourly traffic "
              "coefficients, hand-over duration",
    },
    "p2.s10.li4": {
        "ru": "Неопределённость честная: ±1σ накапливается по плечам "
              "маршрута",
        "ro": "Incertitudinea este onestă: ±1σ se acumulează pe "
              "etapele rutei",
        "en": "Honest uncertainty: ±1σ accumulates leg by leg along "
              "the route",
    },
    "p2.s10.li5": {
        "ru": "Тот же прогнозист обслуживает и топливный контур: табло "
              "прибытия бензовозов на АЗС",
        "ro": "Același predictor deservește și conturul de combustibil: "
              "tabloul de sosire al cisternelor la stații",
        "en": "The same forecaster also serves the fuel loop: a "
              "tanker arrival board at fuel stations",
    },
    "p2.s10.stat1": {
        "ru": "доверительный<br>интервал прогноза",
        "ro": "interval de<br>încredere al prognozei",
        "en": "forecast<br>confidence interval",
    },
    "p2.s10.stat2": {
        "ru": "обучаемых часовых<br>коэффициента трафика",
        "ro": "coeficienți orari<br>de trafic, antrenabili",
        "en": "trainable hourly<br>traffic coefficients",
    },
    "p2.s10.link.points": {
        "ru": "Табло на точках доставки", "ro": "Tabloul la punctele de livrare",
        "en": "Board at delivery points",
    },
    "p2.s10.link.store": {
        "ru": "Табло магазина на карте", "ro": "Tabloul magazinului pe hartă",
        "en": "Store board on the map",
    },
    "p2.s10.link.api": {
        "ru": "API табло (JSON)", "ro": "API tablou (JSON)",
        "en": "Board API (JSON)",
    },

    # -- слайд 11: топливный контур (новое) --
    "p2.s11.title": {
        "ru": "Топливный контур: цифровой двойник сети АЗС Молдовы",
        "ro": "Contur de combustibil: geamănul digital al rețelei de "
              "stații din Moldova",
        "en": "Fuel loop: a digital twin of Moldova's fuel-station "
              "network",
    },
    "p2.s11.sub": {
        "ru": "тот же архитектурный приём, что и у розничной сети — "
              "автономная карта, движение по реальным дорогам, "
              "ИИ-табло прибытия — применён к другому домену",
        "ro": "aceeași soluție arhitecturală ca la rețeaua de retail — "
              "hartă autonomă, deplasare pe drumuri reale, tablou de "
              "sosire cu IA — aplicată unui alt domeniu",
        "en": "the same architectural trick as retail — a "
              "self-contained map, movement on real roads, an AI "
              "arrival board — applied to a different domain",
    },
    "p2.s11.li1": {
        "ru": "46 реальных АЗС по всей Молдове плюс нефтебаза Сынжера "
              "— автономная карта страны (OSM), интернет не нужен",
        "ro": "46 de stații reale din toată Moldova, plus baza de "
              "combustibil Sîngera — hartă autonomă a țării (OSM), fără "
              "internet",
        "en": "46 real fuel stations across Moldova plus the Sîngera "
              "fuel depot — a self-contained country map (OSM), no "
              "internet needed",
    },
    "p2.s11.li2": {
        "ru": "Бензовозы едут по настоящим трассам Молдовы (граф "
              "дорог, A*), а не по прямой",
        "ro": "Cisternele circulă pe șoselele reale ale Moldovei (graf "
              "rutier, A*), nu în linie dreaptă",
        "en": "Tankers drive on Moldova's real roads (a road graph, "
              "A*), not straight lines",
    },
    "p2.s11.li3": {
        "ru": "Автозаказ: остаток на станции падает ниже порога → "
              "рейс бензовоза формируется автоматически",
        "ro": "Comandă automată: stocul stației scade sub prag → cursa "
              "cisternei se generează automat",
        "en": "Auto-ordering: a station's stock drops below a "
              "threshold → a tanker run is generated automatically",
    },
    "p2.s11.li4": {
        "ru": "Живая интеграция с ERP Artgranit: система опрашивает "
              "реальный источник, при недоступности откатывается в "
              "эмуляцию по таймауту — без единого сбоя демо",
        "ro": "Integrare live cu ERP Artgranit: sistemul interoghează "
              "sursa reală, iar la indisponibilitate revine la emulare "
              "după un timeout — fără nicio întrerupere a demo-ului",
        "en": "A live integration with the Artgranit ERP: the system "
              "polls the real source and falls back to emulation on a "
              "timeout when it's unreachable — with no demo downtime",
    },
    "p2.s11.li5": {
        "ru": "ИИ-табло прибытия на каждой станции — тот же "
              "прогнозист eta_ai.py, что и в розничной доставке",
        "ro": "Tablou de sosire cu IA la fiecare stație — același "
              "predictor eta_ai.py ca la livrarea de retail",
        "en": "An AI arrival board at every station — the same "
              "eta_ai.py forecaster as retail delivery",
    },
    "p2.s11.li6": {
        "ru": "Лента событий: заказ, отгрузка с нефтебазы, прибытие, "
              "отказ/восстановление связи с ERP",
        "ro": "Flux de evenimente: comandă, expediere de la baza de "
              "combustibil, sosire, pierderea/restabilirea legăturii cu "
              "ERP",
        "en": "An event feed: order, dispatch from the depot, "
              "arrival, ERP link loss/recovery",
    },
    "p2.s11.stat1": {
        "ru": "АЗС по<br>всей Молдове", "ro": "stații în<br>toată Moldova",
        "en": "stations across<br>Moldova",
    },
    "p2.s11.stat2": {
        "ru": "источник данных:<br>эмуляция или Artgranit",
        "ro": "sursa datelor:<br>emulare sau Artgranit",
        "en": "data source:<br>emulation or Artgranit",
    },
    "p2.s11.link.map": {
        "ru": "Карта топливной сети", "ro": "Harta rețelei de combustibil",
        "en": "Fuel network map",
    },
    "p2.s11.link.api": {
        "ru": "API состояния (JSON)", "ro": "API stare (JSON)",
        "en": "State API (JSON)",
    },
    "p2.s11.link.integration": {
        "ru": "Как подключена ERP Artgranit", "ro": "Cum e conectat ERP-ul Artgranit",
        "en": "How the Artgranit ERP is connected",
    },

    # -- слайд 12: bon fiscal (новое) --
    "p2.s12.title": {
        "ru": "Чек по молдавскому законодательству: bon fiscal",
        "ro": "Bonul conform legislației moldovenești: bon fiscal",
        "en": "A receipt under Moldovan law: bon fiscal",
    },
    "p2.s12.sub": {
        "ru": "HG 141/2019, Serviciul Fiscal de Stat — формат чека "
              "переработан под требования Молдовы",
        "ro": "HG 141/2019, Serviciul Fiscal de Stat — formatul bonului "
              "a fost adaptat cerințelor Moldovei",
        "en": "HG 141/2019, Serviciul Fiscal de Stat — the receipt "
              "format was rebuilt for Moldova's requirements",
    },
    "p2.s12.li1": {
        "ru": "Реквизиты компании: наименование, IDNO (фискальный "
              "код), адрес подразделения",
        "ro": "Datele companiei: denumire, IDNO (cod fiscal), adresa "
              "subdiviziunii",
        "en": "Company details: name, IDNO (tax code), subdivision "
              "address",
    },
    "p2.s12.li2": {
        "ru": "Заводской и регистрационный номера ECC (аппарата "
              "контроля кассового), а не российские ФН/ФД/ФП",
        "ro": "Numărul de fabricație și de înregistrare ECC, nu FN/FD/FP "
              "din legislația rusă",
        "en": "ECC factory and registration numbers, not the Russian "
              "FN/FD/FP fields",
    },
    "p2.s12.li3": {
        "ru": "TVA считается по ставкам отдельно для каждой позиции: "
              "20% стандартная, 8% льготная (хлеб, молоко и другие "
              "товары первой необходимости)",
        "ro": "TVA se calculează pe cote, separat pentru fiecare "
              "poziție: 20% standard, 8% redusă (pâine, lapte și alte "
              "produse de primă necesitate)",
        "en": "VAT (TVA) is computed per rate for each line item: 20% "
              "standard, 8% reduced (bread, milk and other essentials)",
    },
    "p2.s12.li4": {
        "ru": "Печатная форма 80 мм — тот же чек, что уходит на "
              "Android с облачной кассой или на терминал SmartOne",
        "ro": "Format tipărit de 80 mm — același bon care merge pe "
              "Android cu casă de marcat în cloud sau pe terminalul "
              "SmartOne",
        "en": "An 80 mm printed slip — the same receipt sent to an "
              "Android device with a cloud till or a SmartOne terminal",
    },
    "p2.s12.li5": {
        "ru": "Формируется в момент вручения заказа курьером, привязан "
              "к конкретному маршруту и получателю",
        "ro": "Se generează în momentul predării comenzii de către "
              "curier, legat de o rută și un destinatar anume",
        "en": "Generated the moment a courier hands over the order, "
              "tied to a specific route and recipient",
    },
    "p2.s12.stat": {
        "ru": "ставки TVA<br>по видам товаров",
        "ro": "cote TVA<br>pe categorii de produse",
        "en": "TVA rates<br>by product category",
    },
    "p2.s12.link.receipt": {
        "ru": "Последний bon fiscal (демо)",
        "ro": "Ultimul bon fiscal (demo)", "en": "Latest bon fiscal (demo)",
    },
    "p2.s12.link.dash": {
        "ru": "Дашборд доставки", "ro": "Panoul de livrare",
        "en": "Delivery dashboard",
    },

    # -- слайд 13: трёхъязычность (новое) --
    "p2.s13.title": {
        "ru": "Три языка интерфейса: ru / ro / en",
        "ro": "Trei limbi ale interfeței: ru / ro / en",
        "en": "Three interface languages: ru / ro / en",
    },
    "p2.s13.sub": {
        "ru": "румынский — государственный язык страны, русский и "
              "английский — рабочие языки текущей аудитории",
        "ro": "româna — limba de stat, rusa și engleza — limbile de "
              "lucru ale audienței curente",
        "en": "Romanian is the state language, Russian and English "
              "are the current audience's working languages",
    },
    "p2.s13.li1": {
        "ru": "Каталог из 422 переводимых ключей: интерфейс, лента "
              "событий, чек, подсказки тренажёра",
        "ro": "Catalog cu 422 de chei traduse: interfață, flux de "
              "evenimente, bon, indicii ale simulatorului",
        "en": "A catalogue of 422 translatable keys: interface, event "
              "feed, receipt, trainer hints",
    },
    "p2.s13.li2": {
        "ru": "Переключатель языка на каждом экране — карта, "
              "доставка, топливная сеть, планограмма, тренажёр, "
              "документация, презентации",
        "ro": "Comutator de limbă pe fiecare ecran — hartă, livrare, "
              "rețea de combustibil, planogramă, simulator, "
              "documentație, prezentări",
        "en": "A language switcher on every screen — map, delivery, "
              "fuel network, planogram, trainer, documentation, "
              "presentations",
    },
    "p2.s13.li3": {
        "ru": "Множественное число считается по правилам каждого "
              "языка отдельно (русский — 3 формы, румынский — 2, "
              "английский — 2)",
        "ro": "Pluralul se calculează după regulile fiecărei limbi în "
              "parte (rusa — 3 forme, română — 2, engleză — 2)",
        "en": "Plural forms follow each language's own rules "
              "(Russian — 3 forms, Romanian — 2, English — 2)",
    },
    "p2.s13.li4": {
        "ru": "Выбор языка запоминается (localStorage) и переживает "
              "переходы между разделами по ссылке",
        "ro": "Alegerea limbii este reținută (localStorage) și "
              "supraviețuiește navigării între secțiuni prin linkuri",
        "en": "The language choice is remembered (localStorage) and "
              "survives navigation between sections via links",
    },
    "p2.s13.li5": {
        "ru": "Событийная лента и bon fiscal собираются на языке "
              "запроса на сервере — не только статические подписи",
        "ro": "Fluxul de evenimente și bonul fiscal se compun pe "
              "server, în limba cererii — nu doar etichetele statice",
        "en": "The event feed and the fiscal receipt are assembled on "
              "the server in the request's language — not just static "
              "labels",
    },
    "p2.s13.stat1": {"ru": "языка", "ro": "limbi", "en": "languages"},
    "p2.s13.stat2": {
        "ru": "ключа каталога", "ro": "chei de catalog", "en": "catalogue keys",
    },
    "p2.s13.link.ro": {
        "ru": "Эта презентация по-румынски", "ro": "Această prezentare în română",
        "en": "This presentation in Romanian",
    },
    "p2.s13.link.en": {
        "ru": "Эта презентация по-английски", "ro": "Această prezentare în engleză",
        "en": "This presentation in English",
    },
    "p2.s13.link.docs": {
        "ru": "Документация (тоже на 3 языках)",
        "ro": "Documentație (tot în 3 limbi)", "en": "Docs (also 3 languages)",
    },

    # -- BPMN: пополнение полки --
    "p2.bpmn1.title": {
        "ru": "Бизнес-процесс: пополнение полки через РЦ",
        "ro": "Proces de business: reaprovizionarea raftului prin DC",
        "en": "Business process: shelf replenishment via the DC",
    },
    "p2.bpmn.sub": {
        "ru": "Нотация BPMN (стиль ELMA) · каждая фигура кликабельна и "
              "открывает соответствующий экран демо-системы",
        "ro": "Notație BPMN (stil ELMA) · fiecare figură este "
              "clickabilă și deschide ecranul corespunzător din demo",
        "en": "BPMN notation (ELMA style) · every shape is clickable "
              "and opens the matching demo screen",
    },
    "p2.bpmn1.lane1": {"ru": "Магазин (торговый зал)", "ro": "Magazin (sala de vânzare)",
                        "en": "Store (sales floor)"},
    "p2.bpmn1.lane2": {"ru": "Логистический центр", "ro": "Centrul logistic",
                        "en": "Distribution centre"},
    "p2.bpmn1.lane3": {"ru": "Поставщик", "ro": "Furnizor", "en": "Supplier"},
    "p2.bpmn1.start": {"ru": "продажи идут", "ro": "vânzările continuă",
                        "en": "sales in progress"},
    "p2.bpmn1.t1": {"ru": "Контроль остатков", "ro": "Control stocuri",
                     "en": "Stock monitoring"},
    "p2.bpmn1.t1.sub": {"ru": "3D-планограмма ↗", "ro": "planogramă 3D ↗",
                         "en": "3D planogram ↗"},
    "p2.bpmn1.d1": {"ru": "полка", "ro": "raftul", "en": "shelf"},
    "p2.bpmn1.d1.sub": {"ru": "пуста? ↗", "ro": "gol? ↗", "en": "empty? ↗"},
    "p2.bpmn1.t2": {"ru": "Заказ пополнения", "ro": "Comandă de reaprovizionare",
                     "en": "Replenishment order"},
    "p2.bpmn1.t2.sub": {"ru": "в РЦ (карта) ↗", "ro": "la DC (hartă) ↗",
                         "en": "to the DC (map) ↗"},
    "p2.bpmn1.d2": {"ru": "есть на", "ro": "există în", "en": "in"},
    "p2.bpmn1.d2b": {"ru": "складе? ↗", "ro": "depozit? ↗", "en": "stock? ↗"},
    "p2.bpmn1.t3": {"ru": "Отгрузка: рейс 🚚", "ro": "Expediere: cursă 🚚",
                     "en": "Dispatch: a run 🚚"},
    "p2.bpmn1.t3.sub": {"ru": "грузовик на карте ↗", "ro": "camion pe hartă ↗",
                         "en": "truck on the map ↗"},
    "p2.bpmn1.t4": {"ru": "Приёмка и пополнение", "ro": "Recepție și reaprovizionare",
                     "en": "Receiving and restocking"},
    "p2.bpmn1.t4.sub": {"ru": "полки (зал) ↗", "ro": "raft (sală) ↗",
                         "en": "the shelf (floor) ↗"},
    "p2.bpmn1.t5": {"ru": "Заказ поставщику", "ro": "Comandă la furnizor",
                     "en": "Order to supplier"},
    "p2.bpmn1.t5.sub": {"ru": "(лента событий) ↗", "ro": "(flux evenimente) ↗",
                         "en": "(event feed) ↗"},
    "p2.bpmn1.t6": {"ru": "Поставка в РЦ", "ro": "Livrare la DC",
                     "en": "Delivery to the DC"},
    "p2.bpmn1.t6.sub": {"ru": "приход на склад ↗", "ro": "recepție la depozit ↗",
                         "en": "warehouse receipt ↗"},
    "p2.bpmn1.no": {"ru": "нет", "ro": "nu", "en": "no"},
    "p2.bpmn1.yes": {"ru": "да", "ro": "da", "en": "yes"},
    "p2.bpmn.legend1": {
        "ru": "🟩 старт · 🔷 задача (клик — экран системы) · 🔶 "
              "шлюз-решение · 🟥 завершение",
        "ro": "🟩 start · 🔷 sarcină (clic — ecran de sistem) · 🔶 "
              "poartă de decizie · 🟥 final",
        "en": "🟩 start · 🔷 task (click — a system screen) · 🔶 "
              "decision gateway · 🟥 end",
    },
    "p2.bpmn1.link": {
        "ru": "Карта: OOS → рейс РЦ → пополнение",
        "ro": "Harta: OOS → cursă DC → reaprovizionare",
        "en": "Map: OOS → DC run → restocking",
    },

    # -- BPMN: интернет-заказ --
    "p2.bpmn2.title": {
        "ru": "Бизнес-процесс: интернет-заказ и доставка",
        "ro": "Proces de business: comandă online și livrare",
        "en": "Business process: an online order and delivery",
    },
    "p2.bpmn2.lane1": {"ru": "Клиент", "ro": "Client", "en": "Customer"},
    "p2.bpmn2.lane2": {"ru": "Магазин: сборка и диспетчеризация",
                        "ro": "Magazin: asamblare și dispecerizare",
                        "en": "Store: picking and dispatch"},
    "p2.bpmn2.lane3": {"ru": "Курьер (приложение с GPS)",
                        "ro": "Curier (aplicație cu GPS)",
                        "en": "Courier (GPS app)"},
    "p2.bpmn2.t1": {"ru": "Заказ на сайте", "ro": "Comandă pe site",
                     "en": "Order on the site"},
    "p2.bpmn2.t1.sub": {"ru": "панель заказов ↗", "ro": "panoul comenzilor ↗",
                         "en": "orders panel ↗"},
    "p2.bpmn2.t2": {"ru": "Сборка по планограмме", "ro": "Asamblare după planogramă",
                     "en": "Picking by planogram"},
    "p2.bpmn2.t2.sub": {"ru": "new→picking→packed ↗",
                         "ro": "new→picking→packed ↗", "en": "new→picking→packed ↗"},
    "p2.bpmn2.d1": {"ru": "набралась", "ro": "s-a strâns", "en": "a batch"},
    "p2.bpmn2.d1b": {"ru": "партия? ↗", "ro": "un lot? ↗", "en": "is ready? ↗"},
    "p2.bpmn2.t3": {"ru": "Маршрут 2–4 адреса", "ro": "Rută de 2–4 adrese",
                     "en": "Route of 2–4 addresses"},
    "p2.bpmn2.t3.sub": {"ru": "план на Ганте ↗", "ro": "plan pe Gantt ↗",
                         "en": "plan on Gantt ↗"},
    "p2.bpmn2.t4": {"ru": "Доставка: GPS-трекинг", "ro": "Livrare: urmărire GPS",
                     "en": "Delivery: GPS tracking"},
    "p2.bpmn2.t4.sub": {"ru": "курьер на карте ↗", "ro": "curier pe hartă ↗",
                         "en": "courier on the map ↗"},
    "p2.bpmn2.d2": {"ru": "вручено", "ro": "predat", "en": "handed"},
    "p2.bpmn2.d2b": {"ru": "клиенту? ↗", "ro": "clientului? ↗", "en": "to customer? ↗"},
    "p2.bpmn2.t5": {"ru": "Bon fiscal", "ro": "Bon fiscal", "en": "Bon fiscal"},
    "p2.bpmn2.t5.sub": {"ru": "печатная форма ↗", "ro": "format tipărit ↗",
                         "en": "printed slip ↗"},
    "p2.bpmn2.end_label": {"ru": "заказ у клиента", "ro": "comanda ajunge la client",
                            "en": "order at the customer"},
    "p2.bpmn2.no_wait": {"ru": "нет, ждём", "ro": "nu, așteptăm",
                          "en": "no, waiting"},
    "p2.bpmn2.legend": {
        "ru": "Фигура «Bon fiscal» ведёт на последний живой чек "
              "демо-системы (обновляется автоматически)",
        "ro": "Figura „Bon fiscal” duce la ultimul bon live al "
              "sistemului demo (se actualizează automat)",
        "en": "The “Bon fiscal” shape opens the demo system's latest "
              "live receipt (updates automatically)",
    },
    "p2.bpmn2.link": {
        "ru": "Дашборд доставки с Гантом", "ro": "Panoul de livrare cu Gantt",
        "en": "Delivery dashboard with Gantt",
    },

    # -- BPMN: автозаказ топлива (новое) --
    "p2.bpmn3.title": {
        "ru": "Бизнес-процесс: автозаказ бензовоза на АЗС",
        "ro": "Proces de business: comanda automată a cisternei la "
              "stație",
        "en": "Business process: automatic tanker order for a fuel "
              "station",
    },
    "p2.bpmn3.lane1": {"ru": "АЗС", "ro": "Stația de alimentare",
                        "en": "Fuel station"},
    "p2.bpmn3.lane2": {"ru": "Нефтебаза Сынжера", "ro": "Baza de combustibil Sîngera",
                        "en": "Sîngera fuel depot"},
    "p2.bpmn3.lane3": {"ru": "ERP Artgranit", "ro": "ERP Artgranit",
                        "en": "Artgranit ERP"},
    "p2.bpmn3.start": {"ru": "заправки идут", "ro": "alimentările continuă",
                        "en": "refuelling in progress"},
    "p2.bpmn3.t1": {"ru": "Контроль остатка", "ro": "Control stoc",
                     "en": "Stock monitoring"},
    "p2.bpmn3.t1.sub": {"ru": "карта топлива ↗", "ro": "harta combustibilului ↗",
                         "en": "fuel map ↗"},
    "p2.bpmn3.d1": {"ru": "ниже", "ro": "sub", "en": "below"},
    "p2.bpmn3.d1b": {"ru": "порога? ↗", "ro": "prag? ↗", "en": "threshold? ↗"},
    "p2.bpmn3.t2": {"ru": "Автозаказ рейса", "ro": "Comandă automată a cursei",
                     "en": "Auto-order a run"},
    "p2.bpmn3.t2.sub": {"ru": "без участия человека ↗",
                         "ro": "fără intervenție umană ↗",
                         "en": "no human in the loop ↗"},
    "p2.bpmn3.t3": {"ru": "Опрос ERP Artgranit", "ro": "Interogarea ERP Artgranit",
                     "en": "Polling the Artgranit ERP"},
    "p2.bpmn3.t3.sub": {"ru": "реальные остатки ↗", "ro": "stocuri reale ↗",
                         "en": "real stock levels ↗"},
    "p2.bpmn3.d2": {"ru": "ERP", "ro": "ERP", "en": "ERP"},
    "p2.bpmn3.d2b": {"ru": "доступна? ↗", "ro": "disponibil? ↗",
                      "en": "reachable? ↗"},
    "p2.bpmn3.t4": {"ru": "Откат в эмуляцию", "ro": "Revenire la emulare",
                     "en": "Fall back to emulation"},
    "p2.bpmn3.t4.sub": {"ru": "по таймауту ↗", "ro": "după timeout ↗",
                         "en": "on timeout ↗"},
    "p2.bpmn3.t5": {"ru": "Наливка бензовоза", "ro": "Încărcarea cisternei",
                     "en": "Loading the tanker"},
    "p2.bpmn3.t5.sub": {"ru": "выезд с нефтебазы ↗", "ro": "plecare de la bază ↗",
                         "en": "leaving the depot ↗"},
    "p2.bpmn3.t6": {"ru": "Рейс по трассе", "ro": "Cursă pe șosea",
                     "en": "Run along the highway"},
    "p2.bpmn3.t6.sub": {"ru": "ИИ-табло прибытия ↗", "ro": "tablou de sosire IA ↗",
                         "en": "AI arrival board ↗"},
    "p2.bpmn3.end_label": {"ru": "остаток пополнен", "ro": "stocul a fost refăcut",
                            "en": "stock replenished"},
    "p2.bpmn3.legend": {
        "ru": "Тот же приём, что и у розничного пополнения полки: "
              "мониторинг → авторешение → рейс по реальным дорогам; "
              "разница — реальный источник остатков (Artgranit) вместо "
              "эмуляции продаж",
        "ro": "Aceeași abordare ca la reaprovizionarea raftului: "
              "monitorizare → decizie automată → cursă pe drumuri "
              "reale; diferența — sursa reală de stocuri (Artgranit) în "
              "loc de emularea vânzărilor",
        "en": "The same trick as retail shelf replenishment: "
              "monitoring → an automatic decision → a run on real "
              "roads; the difference is a real stock source (Artgranit) "
              "instead of a sales emulation",
    },
    "p2.bpmn3.link": {
        "ru": "Карта: остаток → рейс → табло",
        "ro": "Harta: stoc → cursă → tablou", "en": "Map: stock → run → board",
    },

    # -- слайд итогов --
    "p2.sf.title": {
        "ru": "Итоги и развитие", "ro": "Concluzii și dezvoltare",
        "en": "Summary and roadmap",
    },
    "p2.sf.stat1": {
        "ru": "магазинов сети<br>в Кишинёве", "ro": "magazine ale rețelei<br>din Chișinău",
        "en": "network stores<br>in Chisinau",
    },
    "p2.sf.stat2": {
        "ru": "АЗС в<br>топливном контуре", "ro": "stații în<br>conturul de combustibil",
        "en": "stations in<br>the fuel loop",
    },
    "p2.sf.stat3": {
        "ru": "языка<br>интерфейса", "ro": "limbi ale<br>interfeței",
        "en": "interface<br>languages",
    },
    "p2.sf.stat4": {
        "ru": "объект Store<br>для всех данных",
        "ro": "obiect Store<br>pentru toate datele",
        "en": "Store object<br>for all data",
    },
    "p2.sf.desc": {
        "ru": "Одна платформа — от полки Кишинёва до топливной трассы "
              "по всей Молдове — на одном ядре, с живой интеграцией "
              "первого внешнего источника (Artgranit) и молдавским "
              "фискальным чеком.",
        "ro": "O singură platformă — de la raftul din Chișinău până la "
              "șoseaua de combustibil din toată Moldova — pe un singur "
              "nucleu, cu prima integrare live (Artgranit) și bonul "
              "fiscal moldovenesc.",
        "en": "One platform — from a Chisinau shelf to a fuel highway "
              "across all of Moldova — on one core, with the first "
              "live external integration (Artgranit) and a Moldovan "
              "fiscal receipt.",
    },
    "p2.sf.next": {
        "ru": "Следующий шаг: пилот на одном реальном магазине или на "
              "топливном сегменте, интеграция через один объект Store.",
        "ro": "Următorul pas: un pilot pe un magazin real sau pe "
              "segmentul de combustibil, integrare printr-un singur "
              "obiect Store.",
        "en": "Next step: a pilot on one real store or the fuel "
              "segment, integrated through a single Store object.",
    },
    "p2.sf.link.home": {"ru": "Карта сети", "ro": "Harta rețelei",
                         "en": "Network map"},
    "p2.sf.link.fuel": {"ru": "Топливная сеть", "ro": "Rețeaua de combustibil",
                         "en": "Fuel network"},
    "p2.sf.link.docs": {"ru": "Документация", "ro": "Documentație",
                         "en": "Documentation"},
    "p2.sf.link.pptx": {
        "ru": "Скачать PPTX (RO)", "ro": "Descarcă PPTX (RO)",
        "en": "Download PPTX (RO)",
    },
}


class PluralRef:
    """Отложенная ссылка на другой ключ каталога внутри параметра.

    Нужна, когда событие ленты хранит вложенный переводимый кусок
    (слово-число «{n} {orders_word}» или подпись типа кассы курьера
    «{app_title}»): сам он не может быть выбран в момент записи события
    (см. `render_event`) — язык ещё не известен, поэтому вместо готовой
    строки в params кладётся ``PluralRef("...")``, а резолвится он здесь
    же, вместе с остальными параметрами внешнего ключа. Если у ссылки
    свои параметры не заданы, используется count внешнего вызова
    (форма множественного числа); если заданы — count не наследуется.
    """

    __slots__ = ("key", "params")

    def __init__(self, key: str, **params):
        self.key = key
        self.params = params


def t(lang: Optional[str], key: str, count: Optional[int] = None,
      **params) -> str:
    """Перевод по ключу с подстановкой параметров и, если задан ``count``,
    выбором нужной формы множественного числа.

    Отсутствующий ключ не роняет страницу — возвращается сам ключ, чтобы
    дыра в каталоге была видна на экране, а не терялась в 500-й ошибке.
    """
    lang = normalize_lang(lang)
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    value = entry.get(lang, entry.get(DEFAULT_LANG))
    if isinstance(value, (list, tuple)):
        forms = value
        idx = _PLURAL_FUNCS[lang](count if count is not None else 0)
        value = forms[min(idx, len(forms) - 1)]
    if params or count is not None:
        fmt_params = dict(params)
        if count is not None:
            fmt_params.setdefault("n", count)
        for k, v in fmt_params.items():
            if isinstance(v, PluralRef):
                fmt_params[k] = (t(lang, v.key, **v.params) if v.params
                                 else t(lang, v.key, count=count))
        try:
            value = value.format(**fmt_params)
        except (KeyError, IndexError):
            pass
    return value


def render_event(lang: str, ev: Dict) -> str:
    """Собирает текст события ленты из ключа+параметров на нужном языке.

    Событие хранится в моделях (network.py, delivery.py, ...) как
    ``{"key": ..., "params": {...}, "count": int|None}`` — без готовой
    строки, поэтому язык не фиксируется в момент создания события,
    а выбирается здесь, при отдаче ленты на конкретный запрос. Эмодзи
    (``icon``) хранится отдельно от переводимого текста и приклеивается
    здесь же, а не живёт внутри строки каталога.
    """
    text = t(lang, ev["key"], count=ev.get("count"), **ev.get("params", {}))
    icon = ev.get("icon")
    return f"{icon} {text}" if icon else text


def client_catalog(lang: str, keys: Sequence[str]) -> Dict[str, str]:
    """Срез каталога для отдачи в браузер: готовые строки на языке
    запроса, без плейсхолдеров множественного числа (для них — см.
    `client_plural_forms` ниже, там число известно только в браузере)."""
    lang = normalize_lang(lang)
    return {k: t(lang, k) for k in keys}


def client_plural_forms(lang: str, keys: Sequence[str]) -> Dict[str, list]:
    """Сырые формы множественного числа для ключей, где число известно
    только в браузере (например, счётчик проблем Zabbix в карточке
    магазина, обновляемый на каждый опрос). Выбор формы по числу — на
    клиенте, тем же алгоритмом, что и `_plural_ru/ro/en` (см. static/js).
    """
    lang = normalize_lang(lang)
    out: Dict[str, list] = {}
    for k in keys:
        entry = MESSAGES.get(k, {})
        v = entry.get(lang, entry.get(DEFAULT_LANG, [k]))
        out[k] = list(v) if isinstance(v, (list, tuple)) else [v]
    return out
