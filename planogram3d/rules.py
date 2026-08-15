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
from typing import List

from .models import Planogram, Store


@dataclass
class Violation:
    """Одно нарушение, найденное при проверке."""
    group: str      # regulation | contract | planogram | sales
    severity: str   # critical | warning
    where: str      # человекочитаемое место (стеллаж/полка/SKU)
    message: str


def _shelf_z(store: Store, gondola_id: str, shelf_index: int) -> float:
    return store.gondola(gondola_id).shelf(shelf_index).z


def check_regulations(store: Store, planogram: Planogram) -> List[Violation]:
    """Внутренний регламент: вес, габариты, переполнение полок."""
    reg = store.regulations
    out: List[Violation] = []

    for p in planogram.placements:
        product = store.product(p.sku)
        gondola = store.gondola(p.gondola_id)
        shelf = gondola.shelf(p.shelf_index)
        where = f"{gondola.name}, полка {p.shelf_index + 1}, {product.name}"

        if (product.weight > reg.max_weight_high_shelf
                and shelf.z > reg.heavy_shelf_max_z):
            out.append(Violation(
                "regulation", "critical", where,
                f"Тяжёлый товар ({product.weight:.1f} кг) на полке высотой "
                f"{shelf.z:.2f} м — по регламенту тяжелее "
                f"{reg.max_weight_high_shelf:.0f} кг только ниже "
                f"{reg.heavy_shelf_max_z:.1f} м"))

        if product.height > shelf.clearance:
            out.append(Violation(
                "regulation", "critical", where,
                f"Товар высотой {product.height:.2f} м не помещается в "
                f"просвет полки {shelf.clearance:.2f} м"))

        if p.offset + p.facings * product.width > gondola.width + 1e-9:
            out.append(Violation(
                "regulation", "critical", where,
                f"Выкладка выходит за край полки: {p.facings} фейс. × "
                f"{product.width:.2f} м со смещением {p.offset:.2f} м при "
                f"длине полки {gondola.width:.2f} м"))

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
                    f"{gondola.name}, полка {sidx + 1}",
                    f"Пересечение выкладок «{store.product(a.sku).name}» и "
                    f"«{store.product(b.sku).name}»"))
    return out


def check_contracts(store: Store, planogram: Planogram) -> List[Violation]:
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
                    f"Доля полки {share:.1f}% меньше контрактной "
                    f"{contract.min_share_pct:.1f}%"))

        for sku, min_facings in contract.mandatory_skus.items():
            have = facings_by_sku.get(sku, 0)
            if have < min_facings:
                name = store.product(sku).name if sku in store.products else sku
                out.append(Violation(
                    "contract", "critical", f"{supplier.name} — {name}",
                    f"Обязательный SKU: {have} фейс. вместо минимум "
                    f"{min_facings} по контракту"))

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
                    f"По контракту SKU должен стоять на уровне глаз "
                    f"({lo:.1f}–{hi:.1f} м), фактически — нет"))
    return out


def check_against_approved(store: Store) -> List[Violation]:
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
        where = f"{gondola.name}, полка {ap.shelf_index + 1}, {product.name}"
        cp = current_map.get(k)
        if cp is None:
            out.append(Violation(
                "planogram", "critical", where,
                "Позиция из утверждённой планограммы отсутствует на полке"))
        elif cp.facings != ap.facings:
            out.append(Violation(
                "planogram", "warning", where,
                f"Число фейсингов {cp.facings} вместо утверждённых "
                f"{ap.facings}"))

    for k, cp in current_map.items():
        if k not in approved_map:
            product = store.product(cp.sku)
            gondola = store.gondola(cp.gondola_id)
            out.append(Violation(
                "planogram", "warning",
                f"{gondola.name}, полка {cp.shelf_index + 1}, {product.name}",
                "Позиция выложена вне утверждённой планограммы"))
    return out


def check_sales(store: Store) -> List[Violation]:
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
                "Товар закончился на полке (out-of-stock), продажи "
                "остановлены"))
        elif info.fill_ratio < reg.low_stock_threshold:
            out.append(Violation(
                "sales", "warning", product.name,
                f"Низкий остаток: полка заполнена на "
                f"{info.fill_ratio * 100:.0f}%"))
        elif info.days_of_supply < reg.min_days_of_supply:
            out.append(Violation(
                "sales", "warning", product.name,
                f"Запаса меньше чем на {reg.min_days_of_supply:.0f} день "
                f"продаж ({info.days_of_supply:.1f} дн.)"))
    return out


def check_compliance(store: Store) -> List[Violation]:
    """Полная проверка: регламент и контракты — по фактической выкладке,
    плюс расхождения с утверждённой планограммой и алерты по продажам."""
    planogram = store.current_planogram or store.approved_planogram
    out: List[Violation] = []
    if planogram is not None:
        out += check_regulations(store, planogram)
        out += check_contracts(store, planogram)
    out += check_against_approved(store)
    out += check_sales(store)
    severity_rank = {"critical": 0, "warning": 1}
    out.sort(key=lambda v: (severity_rank[v.severity], v.group, v.where))
    return out
