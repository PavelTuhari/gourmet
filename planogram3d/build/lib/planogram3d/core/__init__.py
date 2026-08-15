"""Ядро библиотеки planogram3d: публичный API для интеграции.

Всё, что нужно стороннему приложению, импортируется отсюда::

    from planogram3d.core import (
        Store, Gondola, Shelf, Product, Supplier, Contract,
        Placement, Planogram, SalesInfo, Regulations,
        check_compliance, Violation,
        build_figure, build_report_page, save_report,
    )

Подробнее — в ``docs/LIBRARY.md`` (справочник API) и
``docs/INTEGRATION.md`` (руководство по интеграции).
"""

from .models import (Contract, Gondola, Placement, Planogram, Product,
                     Regulations, SalesInfo, Shelf, Store, Supplier)
from .report import (build_report_page, render_console_report,
                     render_html_report, save_report)
from .rules import (Violation, check_against_approved, check_compliance,
                    check_contracts, check_regulations, check_sales)
from .viz import build_figure, cuboid, fill_color

__all__ = [
    # модель данных
    "Store", "Gondola", "Shelf", "Product", "Supplier", "Contract",
    "Placement", "Planogram", "SalesInfo", "Regulations",
    # проверка соответствия
    "Violation", "check_compliance", "check_regulations", "check_contracts",
    "check_against_approved", "check_sales",
    # 3D-визуализация
    "build_figure", "cuboid", "fill_color",
    # отчёты
    "build_report_page", "save_report", "render_console_report",
    "render_html_report",
]
