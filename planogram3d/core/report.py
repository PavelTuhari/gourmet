"""Формирование отчётов: консольный текст и автономная HTML-страница.

Главные функции для интеграции:

* :func:`build_report_page` — вернуть готовую HTML-страницу (3D-сцена +
  таблица нарушений) строкой, например для отдачи из веб-приложения;
* :func:`save_report` — сохранить страницу в файл;
* :func:`render_console_report` — текстовый отчёт для логов/консоли;
* :func:`render_html_report` — только HTML-блок с таблицей нарушений
  (для встраивания в собственную страницу).
"""

import html
from pathlib import Path
from typing import List, Optional

from .models import Store
from .rules import Violation, check_compliance
from .viz import build_figure

GROUP_TITLES = {
    "regulation": "Внутренний регламент",
    "contract": "Контракты с поставщиками",
    "planogram": "Соответствие утверждённой планограмме",
    "sales": "Продажи и остатки",
}
GROUP_ORDER = ("regulation", "contract", "planogram", "sales")
SEVERITY_TITLES = {"critical": "критично", "warning": "предупреждение"}


def render_console_report(violations: List[Violation]) -> str:
    """Текстовый отчёт о нарушениях для консоли или лога."""
    if not violations:
        return "✔ Нарушений не найдено: выкладка соответствует регламенту " \
               "и контрактам."
    lines = [f"Найдено нарушений: {len(violations)}", ""]
    for group in GROUP_ORDER:
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
    """HTML-блок с таблицей нарушений (для встраивания в свою страницу)."""
    if not violations:
        return ('<div style="max-width:1100px;margin:1em auto;font-family:'
                'sans-serif;color:#2a7d2e"><h2>✔ Нарушений не найдено</h2>'
                "<p>Выкладка соответствует внутреннему регламенту и "
                "контрактам с поставщиками.</p></div>")

    n_crit = sum(1 for v in violations if v.severity == "critical")
    rows = []
    for group in GROUP_ORDER:
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


def build_report_page(store: Store,
                      violations: Optional[List[Violation]] = None,
                      include_plotlyjs=True,
                      default_height: str = "70vh") -> str:
    """Полная автономная HTML-страница: 3D-сцена + таблица нарушений.

    ``violations=None`` — проверка выполняется автоматически
    (:func:`~planogram3d.core.rules.check_compliance`).
    ``include_plotlyjs`` передаётся в ``plotly`` как есть: ``True`` —
    встроить библиотеку в страницу (автономный файл ~4 МБ), ``"cdn"`` —
    подключить с CDN (лёгкая страница, нужен интернет).
    """
    if violations is None:
        violations = check_compliance(store)
    fig = build_figure(store)
    page = fig.to_html(include_plotlyjs=include_plotlyjs, full_html=True,
                       default_height=default_height)
    return page.replace("</body>", render_html_report(violations) + "</body>")


def save_report(store: Store, path="planogram_report.html",
                violations: Optional[List[Violation]] = None,
                include_plotlyjs=True) -> Path:
    """Сохранить HTML-отчёт в файл и вернуть путь к нему."""
    out = Path(path)
    out.write_text(build_report_page(store, violations,
                                     include_plotlyjs=include_plotlyjs),
                   encoding="utf-8")
    return out
