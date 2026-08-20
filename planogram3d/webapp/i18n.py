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
    """Румынский: 2 формы, но с той самой особенностью CLDR — числа,
    оканчивающиеся на 01-19 (в том числе после сотен: 101, 119, 219),
    используют ту же форму, что единица, а не «множественную»."""
    n = abs(int(n))
    if n == 1 or 1 <= (n % 100) <= 19:
        return 0                                   # comandă, comenzi (1..19, 101..119...)
    return 1                                        # comenzi (20, 30, 100, 200...)


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
        "ro": ["comandă", "comenzi"],
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
        "ro": ["produs", "produse"],
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
        "ro": ["cursă", "curse"],
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
        "ro": ["cursă", "curse"],
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
        "ro": ["problemă activă", "probleme active"],
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
    "unit.liters_short": {"ru": "л", "ro": "l", "en": "L"},
    "unit.kg_short": {"ru": "кг", "ro": "kg", "en": "kg"},
    "unit.meters_short": {"ru": "м", "ro": "m", "en": "m"},
    "unit.days_short": {"ru": "дн.", "ro": "zile", "en": "days"},

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
