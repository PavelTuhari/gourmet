"""Демонстрационный магазин: 3 стеллажа, 4 поставщика, контракты и продажи.

Фактическая выкладка намеренно содержит отклонения от утверждённой
планограммы и нарушения регламента/контрактов, чтобы продемонстрировать
работу модуля проверки соответствия.
"""

import copy
import random

from .core import (Contract, Gondola, Placement, Planogram, Product,
                   Regulations, SalesInfo, Shelf, Store, Supplier)


def _standard_shelves() -> list:
    """Пять полок: 0.1, 0.5, 0.9, 1.3, 1.7 м от пола, просвет 0.35 м."""
    return [Shelf(index=i, z=0.1 + i * 0.4, clearance=0.35) for i in range(5)]


def build_demo_store(seed: int = 42) -> Store:
    rng = random.Random(seed)

    suppliers = {
        "SUP-ALPHA": Supplier("SUP-ALPHA", "ООО «Альфа Фудс»", "#4E79A7"),
        "SUP-BREW": Supplier("SUP-BREW", "АО «БрюМастер»", "#F28E2B"),
        "SUP-DAIRY": Supplier("SUP-DAIRY", "ГК «МолПром»", "#59A14F"),
        "SUP-SNACK": Supplier("SUP-SNACK", "ИП Снэков", "#B07AA1"),
    }

    products = {p.sku: p for p in [
        # sku, name, category, supplier, w, h, d, weight
        Product("ALP-001", "Мюсли «Утро» 750 г", "Бакалея", "SUP-ALPHA",
                0.16, 0.24, 0.08, 0.8, is_priority=True),
        Product("ALP-002", "Хлопья овсяные 500 г", "Бакалея", "SUP-ALPHA",
                0.14, 0.22, 0.07, 0.55),
        Product("ALP-003", "Масло оливковое 1 л", "Бакалея", "SUP-ALPHA",
                0.09, 0.30, 0.09, 1.0),
        Product("BRW-001", "Квас «Традиция» 2 л", "Напитки", "SUP-BREW",
                0.11, 0.33, 0.11, 2.1),
        Product("BRW-002", "Лимонад «Дюшес» 1.5 л", "Напитки", "SUP-BREW",
                0.10, 0.32, 0.10, 1.6, is_priority=True),
        Product("BRW-003", "Вода минеральная 5 л", "Напитки", "SUP-BREW",
                0.19, 0.31, 0.15, 5.2),
        Product("DRY-001", "Молоко 3.2% 1 л", "Молочные продукты",
                "SUP-DAIRY", 0.07, 0.25, 0.07, 1.05, is_priority=True),
        Product("DRY-002", "Кефир 1% 0.9 л", "Молочные продукты",
                "SUP-DAIRY", 0.07, 0.24, 0.07, 0.95),
        Product("DRY-003", "Сыр «Гурман» 300 г", "Молочные продукты",
                "SUP-DAIRY", 0.12, 0.08, 0.10, 0.3),
        Product("SNK-001", "Чипсы «Хруст» 150 г", "Снеки", "SUP-SNACK",
                0.20, 0.28, 0.09, 0.16, is_priority=True),
        Product("SNK-002", "Орехи микс 200 г", "Снеки", "SUP-SNACK",
                0.12, 0.18, 0.06, 0.21),
        Product("SNK-003", "Сухарики ржаные 100 г", "Снеки", "SUP-SNACK",
                0.11, 0.16, 0.05, 0.11),
    ]}

    gondolas = [
        Gondola("G1", "Стеллаж 1 (Бакалея)", x=0.0, y=0.0,
                width=2.4, depth=0.5, shelves=_standard_shelves()),
        Gondola("G2", "Стеллаж 2 (Напитки)", x=0.0, y=2.0,
                width=2.4, depth=0.5, shelves=_standard_shelves()),
        Gondola("G3", "Стеллаж 3 (Молочка и снеки)", x=0.0, y=4.0,
                width=2.4, depth=0.5, shelves=_standard_shelves()),
    ]

    contracts = [
        # «Альфа Фудс»: не менее 20% фронта, мюсли — на уровне глаз
        Contract("SUP-ALPHA", min_share_pct=20.0,
                 mandatory_skus={"ALP-001": 4, "ALP-002": 3},
                 eye_level_skus=["ALP-001"]),
        # «БрюМастер»: лимонад обязателен и на уровне глаз
        Contract("SUP-BREW", min_share_pct=15.0,
                 mandatory_skus={"BRW-002": 5},
                 eye_level_skus=["BRW-002"]),
        # «МолПром»: молоко минимум 6 фейсингов
        Contract("SUP-DAIRY", mandatory_skus={"DRY-001": 6}),
    ]

    # ----- утверждённая планограмма -------------------------------------
    approved = Planogram("Утверждённая планограмма v2.3", [
        # Стеллаж 1 — бакалея «Альфа Фудс»
        Placement("ALP-003", "G1", 0, offset=0.05, facings=8),
        Placement("ALP-002", "G1", 2, offset=0.10, facings=6),
        Placement("ALP-001", "G1", 3, offset=0.10, facings=5),   # уровень глаз
        Placement("SNK-002", "G1", 4, offset=0.20, facings=5),

        # Стеллаж 2 — напитки «БрюМастер»
        Placement("BRW-003", "G2", 0, offset=0.05, facings=6),   # тяжёлое — низ
        Placement("BRW-001", "G2", 1, offset=0.10, facings=9),
        Placement("BRW-002", "G2", 3, offset=0.10, facings=6),   # уровень глаз
        Placement("SNK-003", "G2", 4, offset=0.15, facings=8),

        # Стеллаж 3 — молочка и снеки
        Placement("DRY-001", "G3", 1, offset=0.05, facings=7),
        Placement("DRY-002", "G3", 1, offset=0.60, facings=6),
        Placement("DRY-003", "G3", 2, offset=0.10, facings=8),
        Placement("SNK-001", "G3", 3, offset=0.10, facings=6),
        Placement("SNK-002", "G3", 4, offset=0.10, facings=4),
    ])

    # ----- фактическая выкладка (с отклонениями) ------------------------
    current = Planogram("Фактическая выкладка", copy.deepcopy(
        approved.placements))
    by_key = {(p.sku, p.gondola_id, p.shelf_index): p
              for p in current.placements}

    # 1) мюсли переставили с уровня глаз на нижнюю полку и урезали фейсинги
    musli = by_key[("ALP-001", "G1", 3)]
    current.placements.remove(musli)
    current.placements.append(Placement("ALP-001", "G1", 1,
                                        offset=0.10, facings=3))
    # 2) лимонад сократили до 4 фейсингов (контракт требует 5)
    by_key[("BRW-002", "G2", 3)].facings = 4
    # 3) воду 5 л (5.2 кг) кто-то поставил на верхнюю полку — нарушение
    #    весового регламента
    current.placements.append(Placement("BRW-003", "G2", 4,
                                        offset=1.20, facings=2))
    # 4) сухарики исчезли с полки вовсе
    current.placements.remove(by_key[("SNK-003", "G2", 4)])
    # 5) на освободившееся место выложили не согласованные планограммой чипсы
    current.placements.append(Placement("SNK-001", "G2", 4,
                                        offset=0.15, facings=4))

    # ----- текущее состояние продаж -------------------------------------
    facings_by_sku = {}
    for p in current.placements:
        facings_by_sku[p.sku] = facings_by_sku.get(p.sku, 0) + p.facings

    rows_deep = 3  # единиц товара в глубину полки
    sales = {}
    for sku, facings in facings_by_sku.items():
        capacity = facings * rows_deep
        fill = rng.uniform(0.15, 1.0)
        stock = round(capacity * fill)
        rate = rng.uniform(2.0, 14.0)
        sales[sku] = SalesInfo(sku=sku, stock=stock, capacity=capacity,
                               sold_today=int(rate * rng.uniform(0.5, 1.2)),
                               sales_rate=rate)
    # демонстративный out-of-stock по кефиру
    sales["DRY-002"].stock = 0
    sales["DRY-002"].sold_today = 11

    return Store(
        store_id="ST-017",
        name="Магазин №17 «Гурман», г. Кишинёв",
        gondolas=gondolas,
        products=products,
        suppliers=suppliers,
        contracts=contracts,
        regulations=Regulations(),
        approved_planogram=approved,
        current_planogram=current,
        sales=sales,
    )
