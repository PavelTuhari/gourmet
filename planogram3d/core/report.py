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

from .i18n import DEFAULT_LANG, t
from .models import Store
from .rules import Violation, check_compliance
from .viz import build_figure

GROUP_ORDER = ("regulation", "contract", "planogram", "sales")
#: заголовки групп/уровней важности переведены через `core/i18n.py`
#: (`report.group.*`, `report.severity.*`) — держим здесь только
#: соответствие группа → ключ, готовые строки собираются на лету под
#: нужный ``lang``, см. `_group_title`/`_severity_title` ниже.
_GROUP_KEYS = {
    "regulation": "report.group.regulation",
    "contract": "report.group.contract",
    "planogram": "report.group.planogram",
    "sales": "report.group.sales",
}
_SEVERITY_KEYS = {
    "critical": "report.severity.critical",
    "warning": "report.severity.warning",
}


def render_console_report(violations: List[Violation],
                          lang: str = DEFAULT_LANG) -> str:
    """Текстовый отчёт о нарушениях для консоли или лога."""
    if not violations:
        return t(lang, "report.console.none")
    lines = [t(lang, "report.console.found", n=len(violations)), ""]
    for group in GROUP_ORDER:
        items = [v for v in violations if v.group == group]
        if not items:
            continue
        group_title = t(lang, _GROUP_KEYS[group])
        lines.append(f"── {group_title} ({len(items)}) " + "─" * 20)
        for v in items:
            mark = "✖" if v.severity == "critical" else "⚠"
            sev_title = t(lang, _SEVERITY_KEYS[v.severity])
            lines.append(f"  {mark} [{sev_title}] "
                         f"{v.where}: {v.message}")
        lines.append("")
    return "\n".join(lines)


def render_html_report(violations: List[Violation],
                       lang: str = DEFAULT_LANG) -> str:
    """HTML-блок с таблицей нарушений (для встраивания в свою страницу)."""
    if not violations:
        return ('<div style="max-width:1100px;margin:1em auto;font-family:'
                f'sans-serif;color:#2a7d2e"><h2>{t(lang, "report.html.none_title")}'
                f'</h2><p>{t(lang, "report.html.none_text")}</p></div>')

    n_crit = sum(1 for v in violations if v.severity == "critical")
    rows = []
    for group in GROUP_ORDER:
        items = [v for v in violations if v.group == group]
        if not items:
            continue
        group_title = t(lang, _GROUP_KEYS[group])
        rows.append(f'<tr><th colspan="3" style="background:#eef1f5;'
                    f'text-align:left;padding:8px 10px">'
                    f"{group_title} ({len(items)})</th></tr>")
        for v in items:
            color = "#c62828" if v.severity == "critical" else "#e6a700"
            sev_title = t(lang, _SEVERITY_KEYS[v.severity])
            rows.append(
                "<tr>"
                f'<td style="color:{color};font-weight:bold;padding:6px 10px;'
                f'white-space:nowrap">{sev_title}</td>'
                f'<td style="padding:6px 10px">{html.escape(v.where)}</td>'
                f'<td style="padding:6px 10px">{html.escape(v.message)}</td>'
                "</tr>")

    return (
        '<div style="max-width:1100px;margin:1em auto;font-family:sans-serif">'
        f"<h2>{t(lang, 'report.html.title', n=len(violations), crit=n_crit)}</h2>"
        '<table style="border-collapse:collapse;width:100%;font-size:14px" '
        'border="1" bordercolor="#dde1e7">'
        f"<tr><th>{t(lang, 'report.html.col_level')}</th>"
        f"<th>{t(lang, 'report.html.col_where')}</th>"
        f"<th>{t(lang, 'report.html.col_desc')}</th></tr>"
        + "".join(rows) + "</table></div>")


def build_report_page(store: Store,
                      violations: Optional[List[Violation]] = None,
                      include_plotlyjs=True,
                      default_height: str = "70vh",
                      lang: str = DEFAULT_LANG) -> str:
    """Полная автономная HTML-страница: 3D-сцена + таблица нарушений.

    ``violations=None`` — проверка выполняется автоматически
    (:func:`~planogram3d.core.rules.check_compliance`), на том же
    ``lang``, что и сама страница.
    ``include_plotlyjs`` передаётся в ``plotly`` как есть: ``True`` —
    встроить библиотеку в страницу (автономный файл ~4 МБ), ``"cdn"`` —
    подключить с CDN (лёгкая страница, нужен интернет).
    """
    if violations is None:
        violations = check_compliance(store, lang=lang)
    fig = build_figure(store, lang)
    page = fig.to_html(include_plotlyjs=include_plotlyjs, full_html=True,
                       default_height=default_height)
    return page.replace("</body>",
                        render_html_report(violations, lang) + "</body>")


def save_report(store: Store, path="planogram_report.html",
                violations: Optional[List[Violation]] = None,
                include_plotlyjs=True, lang: str = DEFAULT_LANG) -> Path:
    """Сохранить HTML-отчёт в файл и вернуть путь к нему."""
    out = Path(path)
    out.write_text(build_report_page(store, violations,
                                     include_plotlyjs=include_plotlyjs,
                                     lang=lang),
                   encoding="utf-8")
    return out
