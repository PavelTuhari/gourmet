"""Точка входа: генерация интерактивного 3D-отчёта по планограмме.

Запуск::

    python -m planogram3d                     # demo-магазин → planogram_report.html
    python -m planogram3d -o out.html         # свой путь к отчёту
    python -m planogram3d --no-browser        # не открывать браузер

Отчёт содержит 3D-сцену с двумя режимами (текущее состояние продаж и
утверждённая планограмма) и таблицу нарушений регламента/контрактов.
"""

import argparse
import html
import sys
import webbrowser
from pathlib import Path
from typing import List

from .rules import Violation, check_compliance
from .sample_data import build_demo_store
from .viz import build_figure

GROUP_TITLES = {
    "regulation": "Внутренний регламент",
    "contract": "Контракты с поставщиками",
    "planogram": "Соответствие утверждённой планограмме",
    "sales": "Продажи и остатки",
}
SEVERITY_TITLES = {"critical": "критично", "warning": "предупреждение"}


def render_console_report(violations: List[Violation]) -> str:
    if not violations:
        return "✔ Нарушений не найдено: выкладка соответствует регламенту " \
               "и контрактам."
    lines = [f"Найдено нарушений: {len(violations)}", ""]
    for group in ("regulation", "contract", "planogram", "sales"):
        items = [v for v in violations if v.group == group]
        if not items:
            continue
        lines.append(f"── {GROUP_TITLES[group]} ({len(items)}) " + "─" * 20)
        for v in items:
            mark = "✖" if v.severity == "critical" else "⚠"
            lines.append(f"  {mark} [{SEVERITY_TITLES[v.severity]}] "
                         f"{v.where}: {v.message}")
        lines.append("")
    return "\n".join(lines)


def render_html_report(violations: List[Violation]) -> str:
    """HTML-блок с таблицей нарушений (добавляется под 3D-сценой)."""
    if not violations:
        return ('<div style="max-width:1100px;margin:1em auto;font-family:'
                'sans-serif;color:#2a7d2e"><h2>✔ Нарушений не найдено</h2>'
                "<p>Выкладка соответствует внутреннему регламенту и "
                "контрактам с поставщиками.</p></div>")

    n_crit = sum(1 for v in violations if v.severity == "critical")
    rows = []
    for group in ("regulation", "contract", "planogram", "sales"):
        items = [v for v in violations if v.group == group]
        if not items:
            continue
        rows.append(f'<tr><th colspan="3" style="background:#eef1f5;'
                    f'text-align:left;padding:8px 10px">'
                    f"{GROUP_TITLES[group]} ({len(items)})</th></tr>")
        for v in items:
            color = "#c62828" if v.severity == "critical" else "#e6a700"
            rows.append(
                "<tr>"
                f'<td style="color:{color};font-weight:bold;padding:6px 10px;'
                f'white-space:nowrap">{SEVERITY_TITLES[v.severity]}</td>'
                f'<td style="padding:6px 10px">{html.escape(v.where)}</td>'
                f'<td style="padding:6px 10px">{html.escape(v.message)}</td>'
                "</tr>")

    return (
        '<div style="max-width:1100px;margin:1em auto;font-family:sans-serif">'
        f"<h2>Отчёт о соответствии: {len(violations)} нарушений "
        f"(критичных — {n_crit})</h2>"
        '<table style="border-collapse:collapse;width:100%;font-size:14px" '
        'border="1" bordercolor="#dde1e7">'
        "<tr><th>Уровень</th><th>Где</th><th>Описание</th></tr>"
        + "".join(rows) + "</table></div>")


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

    fig = build_figure(store)
    out = Path(args.output)
    page = fig.to_html(include_plotlyjs=True, full_html=True,
                       default_height="70vh")
    page = page.replace("</body>", render_html_report(violations) + "</body>")
    out.write_text(page, encoding="utf-8")
    print(f"Отчёт сохранён: {out.resolve()}")

    if not args.no_browser:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
