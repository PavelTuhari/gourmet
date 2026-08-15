"""Демонстрационное CLI-приложение поверх ядра ``planogram3d.core``.

Запуск::

    python -m planogram3d                     # demo-магазин → planogram_report.html
    python -m planogram3d -o out.html         # свой путь к отчёту
    python -m planogram3d --no-browser        # не открывать браузер

Отчёт содержит 3D-сцену с двумя режимами (текущее состояние продаж и
утверждённая планограмма) и таблицу нарушений регламента/контрактов.

Вся функциональность (модель данных, проверки, 3D-сцена, отчёты) живёт в
``planogram3d.core`` и может использоваться из любого другого приложения —
см. ``docs/INTEGRATION.md``.
"""

import argparse
import sys
import webbrowser

from .core import check_compliance, render_console_report, save_report
from .sample_data import build_demo_store


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="planogram3d",
        description="3D-визуализация планограммы магазина: текущее "
                    "состояние продаж и утверждённая планограмма "
                    "(регламент + контракты с поставщиками).")
    parser.add_argument("-o", "--output", default="planogram_report.html",
                        help="путь к выходному HTML-отчёту")
    parser.add_argument("--seed", type=int, default=42,
                        help="зерно генератора демо-данных о продажах")
    parser.add_argument("--no-browser", action="store_true",
                        help="не открывать отчёт в браузере")
    args = parser.parse_args(argv)

    store = build_demo_store(seed=args.seed)
    violations = check_compliance(store)

    print(f"Магазин: {store.name}")
    print(f"Стеллажей: {len(store.gondolas)}, SKU: {len(store.products)}, "
          f"поставщиков: {len(store.suppliers)}")
    print()
    print(render_console_report(violations))

    out = save_report(store, args.output, violations)
    print(f"Отчёт сохранён: {out.resolve()}")

    if not args.no_browser:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
