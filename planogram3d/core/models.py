"""Модель данных планограммы: товары, поставщики, контракты, стеллажи, выкладка.

Все размеры — в метрах, вес — в килограммах.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Supplier:
    """Поставщик товара."""
    supplier_id: str
    name: str
    color: str  # цвет для раскраски утверждённой планограммы (hex)


@dataclass
class Product:
    """Товарная позиция (SKU)."""
    sku: str
    name: str
    category: str
    supplier_id: str
    width: float    # ширина одного фейсинга
    height: float   # высота упаковки
    depth: float    # глубина упаковки
    weight: float   # вес одной единицы, кг
    is_priority: bool = False  # приоритетный (высокомаржинальный) товар


@dataclass
class Shelf:
    """Полка стеллажа."""
    index: int          # номер полки снизу вверх, начиная с 0
    z: float            # высота нижней плоскости полки от пола
    clearance: float    # полезная высота (просвет до следующей полки)


@dataclass
class Gondola:
    """Стеллаж (гондола) в торговом зале."""
    gondola_id: str
    name: str
    x: float            # положение левого края в зале
    y: float            # положение переднего края в зале
    width: float        # длина стеллажа (по оси X)
    depth: float        # глубина стеллажа (по оси Y)
    shelves: List[Shelf] = field(default_factory=list)

    def shelf(self, index: int) -> Shelf:
        return self.shelves[index]


@dataclass
class Placement:
    """Выкладка одного SKU на конкретной полке.

    ``offset`` — смещение первого фейсинга от левого края полки,
    ``facings`` — число фейсингов (единиц товара в ряд по фронту).
    """
    sku: str
    gondola_id: str
    shelf_index: int
    offset: float
    facings: int


@dataclass
class Planogram:
    """Планограмма: набор выкладок на стеллажах магазина."""
    name: str
    placements: List[Placement] = field(default_factory=list)

    def by_gondola(self, gondola_id: str) -> List[Placement]:
        return [p for p in self.placements if p.gondola_id == gondola_id]

    def find(self, sku: str, gondola_id: str,
             shelf_index: int) -> Optional[Placement]:
        for p in self.placements:
            if (p.sku == sku and p.gondola_id == gondola_id
                    and p.shelf_index == shelf_index):
                return p
        return None


@dataclass
class SalesInfo:
    """Текущее состояние продаж/остатков по SKU."""
    sku: str
    stock: int          # текущий остаток на полке, шт.
    capacity: int       # ёмкость выкладки (полная загрузка), шт.
    sold_today: int     # продано за сегодня, шт.
    sales_rate: float   # средняя скорость продаж, шт./день

    @property
    def fill_ratio(self) -> float:
        """Заполненность выкладки от 0 (пусто) до 1 (полная)."""
        if self.capacity <= 0:
            return 0.0
        return max(0.0, min(1.0, self.stock / self.capacity))

    @property
    def days_of_supply(self) -> float:
        """На сколько дней хватит остатка при текущей скорости продаж."""
        if self.sales_rate <= 0:
            return float("inf")
        return self.stock / self.sales_rate


@dataclass
class Contract:
    """Контракт с поставщиком: обязательства ритейлера по выкладке."""
    supplier_id: str
    min_share_pct: float = 0.0          # мин. доля полки (по фронту), %
    mandatory_skus: Dict[str, int] = field(default_factory=dict)
    # обязательные SKU -> минимальное число фейсингов
    eye_level_skus: List[str] = field(default_factory=list)
    # SKU, которые по контракту должны стоять на уровне глаз


@dataclass
class Regulations:
    """Внутренний регламент выкладки торговой сети."""
    max_weight_high_shelf: float = 5.0   # тяжелее — только на нижние полки
    heavy_shelf_max_z: float = 0.6       # «нижние полки» — ниже этой высоты
    eye_level_range: tuple = (1.2, 1.6)  # диапазон «уровня глаз», м
    min_days_of_supply: float = 1.0      # мин. запас в днях продаж
    low_stock_threshold: float = 0.3     # доля заполненности для алерта


@dataclass
class Store:
    """Магазин: зал, ассортимент, поставщики, контракты, планограммы."""
    store_id: str
    name: str
    gondolas: List[Gondola] = field(default_factory=list)
    products: Dict[str, Product] = field(default_factory=dict)
    suppliers: Dict[str, Supplier] = field(default_factory=dict)
    contracts: List[Contract] = field(default_factory=list)
    regulations: Regulations = field(default_factory=Regulations)
    approved_planogram: Optional[Planogram] = None   # утверждённая
    current_planogram: Optional[Planogram] = None    # фактическая выкладка
    sales: Dict[str, SalesInfo] = field(default_factory=dict)

    def gondola(self, gondola_id: str) -> Gondola:
        for g in self.gondolas:
            if g.gondola_id == gondola_id:
                return g
        raise KeyError(gondola_id)

    def product(self, sku: str) -> Product:
        return self.products[sku]

    def supplier_of(self, sku: str) -> Supplier:
        return self.suppliers[self.products[sku].supplier_id]
