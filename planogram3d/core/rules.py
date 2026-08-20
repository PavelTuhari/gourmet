"""Проверка выкладки на соответствие внутреннему регламенту и контрактам.

Функция :func:`check_compliance` возвращает список нарушений
(:class:`Violation`) по трём группам:

* ``regulation`` — внутренний регламент сети (вес, высота, переполнение полок);
* ``contract``   — контракты с поставщиками (доля полки, обязательные SKU,
  уровень глаз);
* ``planogram``  — расхождения фактической выкладки с утверждённой
  планограммой;
* ``sales``      — операционные алерты по продажам (пустая полка, низкий
  запас).
"""

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from .i18n import DEFAULT_LANG, t
from .models import Planogram, Store

#: Сигнатура пользовательской проверки для ``check_compliance``:
#: принимает магазин, возвращает список нарушений.
ComplianceCheck = Callable[["Store"], List["Violation"]]


@dataclass
class Violation:
    """Одно нарушение, найденное при проверке."""
    group: str      # regulation | contract | planogram | sales
    severity: str   # critical | warning
    where: str      # человекочитаемое место (стеллаж/полка/SKU)
    message: str


def _shelf_z(store: Store, gondola_id: str, shelf_index: int) -> float:
    return store.gondola(gondola_id).shelf(shelf_index).z


def check_regulations(store: Store, planogram: Planogram,
                      lang: str = DEFAULT_LANG) -> List[Violation]:
    """Внутренний регламент: вес, габариты, переполнение полок."""
    reg = store.regulations
    out: List[Violation] = []

    for p in planogram.placements:
        product = store.product(p.sku)
        gondola = store.gondola(p.gondola_id)
        shelf = gondola.shelf(p.shelf_index)
        where = t(lang, "rules.where_shelf", gondola=gondola.name,
                 n=p.shelf_index + 1, product=product.name)

        if (product.weight > reg.max_weight_high_shelf
                and shelf.z > reg.heavy_shelf_max_z):
            out.append(Violation(
                "regulation", "critical", where,
                t(lang, "rules.heavy_on_high_shelf",
                  weight=product.weight, z=shelf.z,
                  max_weight=reg.max_weight_high_shelf,
                  max_z=reg.heavy_shelf_max_z)))

        if product.height > shelf.clearance:
            out.append(Violation(
                "regulation", "critical", where,
                t(lang, "rules.too_tall_for_shelf",
                  height=product.height, clearance=shelf.clearance)))

        if p.offset + p.facings * product.width > gondola.width + 1e-9:
            out.append(Violation(
                "regulation", "critical", where,
                t(lang, "rules.overflow_shelf_edge",
                  facings=p.facings, width=product.width,
                  offset=p.offset, gwidth=gondola.width)))

    # взаимное перекрытие выкладок на одной полке
    by_shelf = {}
    for p in planogram.placements:
        by_shelf.setdefault((p.gondola_id, p.shelf_index), []).append(p)
    for (gid, sidx), items in by_shelf.items():
        items = sorted(items, key=lambda p: p.offset)
        for a, b in zip(items, items[1:]):
            a_end = a.offset + a.facings * store.product(a.sku).width
            if a_end > b.offset + 1e-9:
                gondola = store.gondola(gid)
                out.append(Violation(
                    "regulation", "critical",
                    t(lang, "rules.where_shelf_only", gondola=gondola.name,
                      n=sidx + 1),
                    t(lang, "rules.overlap", a=store.product(a.sku).name,
                      b=store.product(b.sku).name)))
    return out


def check_contracts(store: Store, planogram: Planogram,
                    lang: str = DEFAULT_LANG) -> List[Violation]:
    """Контракты с поставщиками: доля полки, обязательные SKU, уровень глаз."""
    reg = store.regulations
    out: List[Violation] = []

    # фронт выкладки (погонные метры фейсингов) по поставщикам
    front_by_supplier = {}
    total_front = 0.0
    for p in planogram.placements:
        product = store.product(p.sku)
        front = p.facings * product.width
        front_by_supplier[product.supplier_id] = (
            front_by_supplier.get(product.supplier_id, 0.0) + front)
        total_front += front

    facings_by_sku = {}
    for p in planogram.placements:
        facings_by_sku[p.sku] = facings_by_sku.get(p.sku, 0) + p.facings

    for contract in store.contracts:
        supplier = store.suppliers[contract.supplier_id]

        if contract.min_share_pct > 0 and total_front > 0:
            share = 100.0 * front_by_supplier.get(
                contract.supplier_id, 0.0) / total_front
            if share + 1e-9 < contract.min_share_pct:
                out.append(Violation(
                    "contract", "critical", supplier.name,
                    t(lang, "rules.share_below_contract", share=share,
                      min_share=contract.min_share_pct)))

        for sku, min_facings in contract.mandatory_skus.items():
            have = facings_by_sku.get(sku, 0)
            if have < min_facings:
                name = store.product(sku).name if sku in store.products else sku
                out.append(Violation(
                    "contract", "critical", f"{supplier.name} — {name}",
                    t(lang, "rules.mandatory_sku_shortage", have=have,
                      need=min_facings)))

        lo, hi = reg.eye_level_range
        for sku in contract.eye_level_skus:
            placements = [p for p in planogram.placements if p.sku == sku]
            if not placements:
                continue  # отсутствие уже поймано как mandatory
            on_eye_level = any(
                lo <= _shelf_z(store, p.gondola_id, p.shelf_index) <= hi
                for p in placements)
            if not on_eye_level:
                name = store.product(sku).name
                out.append(Violation(
                    "contract", "warning", f"{supplier.name} — {name}",
                    t(lang, "rules.eye_level_missing", lo=lo, hi=hi)))
    return out


def check_against_approved(store: Store,
                           lang: str = DEFAULT_LANG) -> List[Violation]:
    """Расхождения фактической выкладки с утверждённой планограммой."""
    out: List[Violation] = []
    approved = store.approved_planogram
    current = store.current_planogram
    if approved is None or current is None:
        return out

    def key(p):
        return (p.sku, p.gondola_id, p.shelf_index)

    approved_map = {key(p): p for p in approved.placements}
    current_map = {key(p): p for p in current.placements}

    for k, ap in approved_map.items():
        product = store.product(ap.sku)
        gondola = store.gondola(ap.gondola_id)
        where = t(lang, "rules.where_shelf", gondola=gondola.name,
                 n=ap.shelf_index + 1, product=product.name)
        cp = current_map.get(k)
        if cp is None:
            out.append(Violation(
                "planogram", "critical", where,
                t(lang, "rules.missing_from_shelf")))
        elif cp.facings != ap.facings:
            out.append(Violation(
                "planogram", "warning", where,
                t(lang, "rules.facings_mismatch", facings=cp.facings,
                  approved=ap.facings)))

    for k, cp in current_map.items():
        if k not in approved_map:
            product = store.product(cp.sku)
            gondola = store.gondola(cp.gondola_id)
            out.append(Violation(
                "planogram", "warning",
                t(lang, "rules.where_shelf", gondola=gondola.name,
                  n=cp.shelf_index + 1, product=product.name),
                t(lang, "rules.unapproved_placement")))
    return out


def check_sales(store: Store, lang: str = DEFAULT_LANG) -> List[Violation]:
    """Операционные алерты по текущему состоянию продаж."""
    reg = store.regulations
    out: List[Violation] = []
    current = store.current_planogram
    if current is None:
        return out

    skus_on_shelf = {p.sku for p in current.placements}
    for sku in sorted(skus_on_shelf):
        info = store.sales.get(sku)
        if info is None:
            continue
        product = store.product(sku)
        if info.stock == 0:
            out.append(Violation(
                "sales", "critical", product.name,
                t(lang, "rules.out_of_stock")))
        elif info.fill_ratio < reg.low_stock_threshold:
            out.append(Violation(
                "sales", "warning", product.name,
                t(lang, "rules.low_stock", pct=info.fill_ratio * 100)))
        elif info.days_of_supply < reg.min_days_of_supply:
            out.append(Violation(
                "sales", "warning", product.name,
                t(lang, "rules.low_days_of_supply",
                  min_days=reg.min_days_of_supply,
                  days=info.days_of_supply)))
    return out


def check_compliance(
        store: Store,
        extra_checks: Optional[Iterable[ComplianceCheck]] = None,
        lang: str = DEFAULT_LANG,
) -> List[Violation]:
    """Полная проверка: регламент и контракты — по фактической выкладке,
    плюс расхождения с утверждённой планограммой и алерты по продажам.

    ``extra_checks`` — дополнительные пользовательские проверки
    (например, специфичные правила конкретной сети); каждая получает
    ``store`` и возвращает список :class:`Violation`.
    ``lang`` — язык текстов нарушений (``ru`` по умолчанию — прежнее
    поведение для существующих вызовов, включая CLI-отчёт).
    """
    planogram = store.current_planogram or store.approved_planogram
    out: List[Violation] = []
    if planogram is not None:
        out += check_regulations(store, planogram, lang)
        out += check_contracts(store, planogram, lang)
    out += check_against_approved(store, lang)
    out += check_sales(store, lang)
    for check in (extra_checks or []):
        out += list(check(store))
    severity_rank = {"critical": 0, "warning": 1}
    out.sort(key=lambda v: (severity_rank.get(v.severity, 2), v.group,
                            v.where))
    return out
