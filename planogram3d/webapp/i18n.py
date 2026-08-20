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
