"""Локализация текстов ядра (ru/ro/en): нарушения регламента, подписи
3D-сцены, заголовки отчёта.

Почему отдельный, свой каталог, а не импорт `webapp.i18n`: `core/` —
переиспользуемая библиотека без внешних зависимостей и без знания о
вебе (см. `docs/HANDOFF.md` §3.1 — единственная интеграционная точка
ядра это `Store`, ядро не знает об источниках/потребителях данных).
Импорт `webapp.i18n` отсюда создал бы обратную зависимость
core → webapp, что ломает и слой (ядро обязано быть используемым как
самостоятельная библиотека, включая CLI-отчёт `python -m planogram3d`),
и тестируемость (webapp тянет Flask). Поэтому здесь — точная копия
приёма из `webapp/i18n.py` (обычный dict-каталог + `t()`), но со своим,
маленьким набором ключей, нужным только ядру. Дублирование десятка
строк кода признано меньшим злом, чем архитектурная связь в
неправильную сторону.

Все функции ядра, что раньше строили русский текст напрямую
(`core/rules.py`, `core/viz.py`, `core/report.py`), теперь принимают
необязательный параметр ``lang`` (по умолчанию ``"ru"`` — сохраняет
прежнее поведение для существующих вызовов, включая CLI). Веб-слой
передаёт туда язык текущего запроса тем же способом, каким он уже
передаёт его в `webapp/i18n.t()`.
"""

from typing import Dict

LANGS = ("ru", "ro", "en")
DEFAULT_LANG = "ru"

MESSAGES: Dict[str, Dict[str, str]] = {
    # ---- core/rules.py: нарушения регламента и контрактов ----------------
    "rules.where_shelf": {
        "ru": "{gondola}, полка {n}, {product}",
        "ro": "{gondola}, raft {n}, {product}",
        "en": "{gondola}, shelf {n}, {product}",
    },
    "rules.where_shelf_only": {
        "ru": "{gondola}, полка {n}",
        "ro": "{gondola}, raft {n}",
        "en": "{gondola}, shelf {n}",
    },
    "rules.heavy_on_high_shelf": {
        "ru": "Тяжёлый товар ({weight:.1f} кг) на полке высотой {z:.2f} м "
              "— по регламенту тяжелее {max_weight:.0f} кг только ниже "
              "{max_z:.1f} м",
        "ro": "Produs greu ({weight:.1f} kg) pe un raft la înălțimea "
              "{z:.2f} m — conform regulamentului, peste {max_weight:.0f} "
              "kg doar sub {max_z:.1f} m",
        "en": "Heavy item ({weight:.1f} kg) on a shelf at height {z:.2f} m "
              "— by policy, over {max_weight:.0f} kg only below "
              "{max_z:.1f} m",
    },
    "rules.too_tall_for_shelf": {
        "ru": "Товар высотой {height:.2f} м не помещается в просвет полки "
              "{clearance:.2f} м",
        "ro": "Produsul cu înălțimea {height:.2f} m nu încape în spațiul "
              "raftului de {clearance:.2f} m",
        "en": "Item {height:.2f} m tall does not fit the shelf clearance "
              "of {clearance:.2f} m",
    },
    "rules.overflow_shelf_edge": {
        "ru": "Выкладка выходит за край полки: {facings} фейс. × "
              "{width:.2f} м со смещением {offset:.2f} м при длине полки "
              "{gwidth:.2f} м",
        "ro": "Expunerea depășește marginea raftului: {facings} fețe × "
              "{width:.2f} m cu decalaj {offset:.2f} m la o lungime a "
              "raftului de {gwidth:.2f} m",
        "en": "Facing overflows the shelf edge: {facings} facings × "
              "{width:.2f} m at offset {offset:.2f} m on a shelf "
              "{gwidth:.2f} m long",
    },
    "rules.overlap": {
        "ru": "Пересечение выкладок «{a}» и «{b}»",
        "ro": "Suprapunere între «{a}» și «{b}»",
        "en": "Overlapping facings: «{a}» and «{b}»",
    },
    "rules.share_below_contract": {
        "ru": "Доля полки {share:.1f}% меньше контрактной {min_share:.1f}%",
        "ro": "Cota de raft {share:.1f}% este sub cea contractuală de "
              "{min_share:.1f}%",
        "en": "Shelf share {share:.1f}% is below the contracted "
              "{min_share:.1f}%",
    },
    "rules.mandatory_sku_shortage": {
        "ru": "Обязательный SKU: {have} фейс. вместо минимум {need} по "
              "контракту",
        "ro": "SKU obligatoriu: {have} fețe în loc de minimum {need} "
              "conform contractului",
        "en": "Mandatory SKU: {have} facings instead of the contracted "
              "minimum of {need}",
    },
    "rules.eye_level_missing": {
        "ru": "По контракту SKU должен стоять на уровне глаз "
              "({lo:.1f}–{hi:.1f} м), фактически — нет",
        "ro": "Conform contractului, SKU trebuie să fie la nivelul "
              "ochilor ({lo:.1f}–{hi:.1f} m), dar nu este",
        "en": "By contract the SKU must sit at eye level "
              "({lo:.1f}–{hi:.1f} m), but currently does not",
    },
    "rules.missing_from_shelf": {
        "ru": "Позиция из утверждённой планограммы отсутствует на полке",
        "ro": "Poziția din planograma aprobată lipsește de pe raft",
        "en": "An item from the approved planogram is missing from the "
              "shelf",
    },
    "rules.facings_mismatch": {
        "ru": "Число фейсингов {facings} вместо утверждённых {approved}",
        "ro": "Număr de fețe {facings} în loc de {approved} aprobate",
        "en": "Facing count {facings} instead of the approved {approved}",
    },
    "rules.unapproved_placement": {
        "ru": "Позиция выложена вне утверждённой планограммы",
        "ro": "Poziția este expusă în afara planogramei aprobate",
        "en": "An item is placed outside the approved planogram",
    },
    "rules.out_of_stock": {
        "ru": "Товар закончился на полке (out-of-stock), продажи "
              "остановлены",
        "ro": "Produsul s-a terminat pe raft (out-of-stock), vânzările "
              "s-au oprit",
        "en": "The item is out of stock on the shelf, sales have stopped",
    },
    "rules.low_stock": {
        "ru": "Низкий остаток: полка заполнена на {pct:.0f}%",
        "ro": "Stoc redus: raftul este umplut în proporție de {pct:.0f}%",
        "en": "Low stock: shelf is {pct:.0f}% full",
    },
    "rules.low_days_of_supply": {
        "ru": "Запаса меньше чем на {min_days:.0f} день продаж "
              "({days:.1f} дн.)",
        "ro": "Stoc pentru mai puțin de {min_days:.0f} zile de vânzări "
              "({days:.1f} zile)",
        "en": "Less than {min_days:.0f} days of stock left "
              "({days:.1f} days)",
    },

    # ---- core/viz.py: подписи 3D-сцены, тултипы, легенда -------------------
    "viz.floor": {"ru": "Пол", "ro": "Podea", "en": "Floor"},
    "viz.shelf_hover": {
        "ru": "<b>{gondola}</b><br>Полка {n} (h={z:.2f} м)",
        "ro": "<b>{gondola}</b><br>Raft {n} (h={z:.2f} m)",
        "en": "<b>{gondola}</b><br>Shelf {n} (h={z:.2f} m)",
    },
    "viz.gondola_hover": {
        "ru": "<b>{name}</b><br>{width:.1f} × {depth:.1f} м",
        "ro": "<b>{name}</b><br>{width:.1f} × {depth:.1f} m",
        "en": "<b>{name}</b><br>{width:.1f} × {depth:.1f} m",
    },
    "viz.hover.sku": {
        "ru": "SKU: {sku} · {category}",
        "ro": "SKU: {sku} · {category}",
        "en": "SKU: {sku} · {category}",
    },
    "viz.hover.supplier": {
        "ru": "Поставщик: {name}", "ro": "Furnizor: {name}",
        "en": "Supplier: {name}",
    },
    "viz.hover.facings": {
        "ru": "Фейсингов: {n}", "ro": "Fețe: {n}", "en": "Facings: {n}",
    },
    "viz.hover.stock": {
        "ru": "Остаток: {stock} из {capacity} шт. ({pct:.0f}%)",
        "ro": "Stoc: {stock} din {capacity} buc. ({pct:.0f}%)",
        "en": "Stock: {stock} of {capacity} pcs ({pct:.0f}%)",
    },
    "viz.hover.sold_today": {
        "ru": "Продано сегодня: {n} шт.", "ro": "Vândut azi: {n} buc.",
        "en": "Sold today: {n} pcs",
    },
    "viz.hover.sales_rate": {
        "ru": "Скорость продаж: {rate:.1f} шт./день",
        "ro": "Ritm de vânzare: {rate:.1f} buc./zi",
        "en": "Sales rate: {rate:.1f} pcs/day",
    },
    "viz.hover.days_of_supply": {
        "ru": "Запас: {dos} дн.", "ro": "Stoc: {dos} zile",
        "en": "Supply: {dos} days",
    },
    "viz.hover.out_of_stock": {
        "ru": "⚠ OUT-OF-STOCK", "ro": "⚠ OUT-OF-STOCK",
        "en": "⚠ OUT-OF-STOCK",
    },
    "viz.legend.full": {
        "ru": "Полная выкладка (≥90%)", "ro": "Expunere completă (≥90%)",
        "en": "Full facing (≥90%)",
    },
    "viz.legend.medium": {
        "ru": "Средний остаток (~50%)", "ro": "Stoc mediu (~50%)",
        "en": "Medium stock (~50%)",
    },
    "viz.legend.low": {
        "ru": "Низкий остаток (≤30%)", "ro": "Stoc redus (≤30%)",
        "en": "Low stock (≤30%)",
    },
    "viz.legend.oos": {
        "ru": "Out-of-stock", "ro": "Out-of-stock", "en": "Out-of-stock",
    },
    "viz.button.sales": {
        "ru": "📊 Текущее состояние продаж",
        "ro": "📊 Starea curentă a vânzărilor",
        "en": "📊 Current sales state",
    },
    "viz.button.approved": {
        "ru": "📋 Утверждённая планограмма",
        "ro": "📋 Planograma aprobată",
        "en": "📋 Approved planogram",
    },
    "viz.title.sales": {
        "ru": "{store} — текущее состояние продаж (фактическая выкладка)",
        "ro": "{store} — starea curentă a vânzărilor (expunere reală)",
        "en": "{store} — current sales state (actual facing)",
    },
    "viz.title.approved": {
        "ru": "{store} — {planogram} (регламент + контракты с "
              "поставщиками)",
        "ro": "{store} — {planogram} (regulament + contracte cu "
              "furnizorii)",
        "en": "{store} — {planogram} (policy + supplier contracts)",
    },
    "viz.axis.height": {
        "ru": "Высота, м", "ro": "Înălțime, m", "en": "Height, m",
    },

    # ---- core/report.py: заголовки отчёта о соответствии ------------------
    "report.group.regulation": {
        "ru": "Внутренний регламент", "ro": "Regulament intern",
        "en": "Internal policy",
    },
    "report.group.contract": {
        "ru": "Контракты с поставщиками", "ro": "Contracte cu furnizorii",
        "en": "Supplier contracts",
    },
    "report.group.planogram": {
        "ru": "Соответствие утверждённой планограмме",
        "ro": "Conformitate cu planograma aprobată",
        "en": "Compliance with the approved planogram",
    },
    "report.group.sales": {
        "ru": "Продажи и остатки", "ro": "Vânzări și stocuri",
        "en": "Sales and stock",
    },
    "report.severity.critical": {
        "ru": "критично", "ro": "critic", "en": "critical",
    },
    "report.severity.warning": {
        "ru": "предупреждение", "ro": "avertizare", "en": "warning",
    },
    "report.console.none": {
        "ru": "✔ Нарушений не найдено: выкладка соответствует регламенту "
              "и контрактам.",
        "ro": "✔ Nicio încălcare găsită: expunerea respectă regulamentul "
              "și contractele.",
        "en": "✔ No violations found: the facing complies with policy "
              "and contracts.",
    },
    "report.console.found": {
        "ru": "Найдено нарушений: {n}", "ro": "Încălcări găsite: {n}",
        "en": "Violations found: {n}",
    },
    "report.html.none_title": {
        "ru": "✔ Нарушений не найдено",
        "ro": "✔ Nicio încălcare găsită",
        "en": "✔ No violations found",
    },
    "report.html.none_text": {
        "ru": "Выкладка соответствует внутреннему регламенту и контрактам "
              "с поставщиками.",
        "ro": "Expunerea respectă regulamentul intern și contractele cu "
              "furnizorii.",
        "en": "The facing complies with internal policy and supplier "
              "contracts.",
    },
    "report.html.title": {
        "ru": "Отчёт о соответствии: {n} нарушений (критичных — {crit})",
        "ro": "Raport de conformitate: {n} încălcări (critice — {crit})",
        "en": "Compliance report: {n} violations ({crit} critical)",
    },
    "report.html.col_level": {
        "ru": "Уровень", "ro": "Nivel", "en": "Level",
    },
    "report.html.col_where": {"ru": "Где", "ro": "Unde", "en": "Where"},
    "report.html.col_desc": {
        "ru": "Описание", "ro": "Descriere", "en": "Description",
    },
}


def t(lang: str, key: str, **params) -> str:
    """Перевод по ключу с подстановкой параметров — упрощённая версия
    `webapp.i18n.t` (без множественного числа, оно ядру не требуется:
    тексты нарушений вставляют число как есть, без словоформ)."""
    lang = lang if lang in LANGS else DEFAULT_LANG
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    value = entry.get(lang, entry.get(DEFAULT_LANG))
    if params:
        try:
            value = value.format(**params)
        except (KeyError, IndexError):
            pass
    return value
