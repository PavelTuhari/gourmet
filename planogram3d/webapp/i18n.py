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
}


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
        try:
            value = value.format(**fmt_params)
        except (KeyError, IndexError):
            pass
    return value


def client_catalog(lang: str, keys: Sequence[str]) -> Dict[str, str]:
    """Срез каталога для отдачи в браузер (см. `server.py`::api_i18n).

    Отдаём только запрошенные ключи, а не весь MESSAGES: клиентский JS
    сейчас переводит буквально несколько строк (кнопка печати чека),
    остальные ~270 строк интерфейса ещё захардкожены и будут переведены
    отдельным этапом — незачем тащить в браузер каталог целиком заранее.
    """
    lang = normalize_lang(lang)
    return {k: t(lang, k) for k in keys}
