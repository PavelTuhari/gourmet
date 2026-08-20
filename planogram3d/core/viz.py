"""Трёхмерная визуализация планограммы (Plotly).

Два режима раскраски товара:

* ``approved`` — цвет поставщика (визуализация утверждённой планограммы);
* ``sales``    — теплокарта по заполненности полки (текущее состояние
  продаж): зелёный — полная выкладка, красный — пусто/out-of-stock.
"""

from typing import List, Optional

import plotly.graph_objects as go

from .i18n import DEFAULT_LANG, t
from .models import Planogram, SalesInfo, Store

FRAME_COLOR = "#9aa1ab"       # каркас стеллажа
SHELF_COLOR = "#d4d9e0"       # полки
EDGE_COLOR = "#6b727c"        # контурные линии каркаса
FLOOR_COLOR = "#e9e5dc"       # пол торгового зала
OOS_COLOR = "#d62728"         # out-of-stock


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _shade(hex_or_rgb: str, factor: float) -> str:
    """Осветлить (>1) или затемнить (<1) цвет '#rrggbb' / 'rgb(r,g,b)'."""
    if hex_or_rgb.startswith("#"):
        r, g, b = (int(hex_or_rgb[i:i + 2], 16) for i in (1, 3, 5))
    else:
        r, g, b = (int(v) for v in
                   hex_or_rgb[hex_or_rgb.index("(") + 1:-1].split(","))
    clamp = lambda v: max(0, min(255, int(v * factor)))
    return f"rgb({clamp(r)},{clamp(g)},{clamp(b)})"


def fill_color(fill_ratio: float) -> str:
    """Красный (0, пусто) → жёлтый (0.5) → зелёный (1, полная выкладка)."""
    t = max(0.0, min(1.0, fill_ratio))
    if t < 0.5:
        r, g, b = 214, _lerp(39, 191, t * 2), 40
    else:
        r, g, b = _lerp(230, 44, (t - 0.5) * 2), _lerp(191, 160, (t - 0.5) * 2), 44
    return f"rgb({int(r)},{int(g)},{int(b)})"


def cuboid(x: float, y: float, z: float,
           dx: float, dy: float, dz: float,
           color: str, name: str = "", hover: Optional[str] = None,
           opacity: float = 1.0) -> go.Mesh3d:
    """Параллелепипед с углом (x, y, z) и размерами (dx, dy, dz)."""
    xs = [x, x + dx, x + dx, x, x, x + dx, x + dx, x]
    ys = [y, y, y + dy, y + dy, y, y, y + dy, y + dy]
    zs = [z, z, z, z, z + dz, z + dz, z + dz, z + dz]
    return go.Mesh3d(
        x=xs, y=ys, z=zs,
        i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3],
        j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4],
        k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
        color=color, opacity=opacity, flatshading=True,
        name=name, text=hover or name,
        hovertemplate="%{text}<extra></extra>",
        showlegend=False,
        lighting=dict(ambient=0.48, diffuse=0.62, specular=0.28,
                      roughness=0.55, fresnel=0.12),
        lightposition=dict(x=3, y=-6, z=8),
    )


def cuboid_edges(x: float, y: float, z: float,
                 dx: float, dy: float, dz: float, segments: list) -> None:
    """Добавить 12 рёбер параллелепипеда в список сегментов (для контура)."""
    p = [(x, y, z), (x + dx, y, z), (x + dx, y + dy, z), (x, y + dy, z),
         (x, y, z + dz), (x + dx, y, z + dz), (x + dx, y + dy, z + dz),
         (x, y + dy, z + dz)]
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7),
                 (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)):
        segments.append((p[a], p[b]))


def edges_trace(segments: list, color: str = EDGE_COLOR,
                width: float = 1.6) -> go.Scatter3d:
    """Единый трейс контурных линий (сегменты разделяются None)."""
    xs, ys, zs = [], [], []
    for a, b in segments:
        xs += [a[0], b[0], None]
        ys += [a[1], b[1], None]
        zs += [a[2], b[2], None]
    return go.Scatter3d(x=xs, y=ys, z=zs, mode="lines",
                        line=dict(color=color, width=width),
                        hoverinfo="skip", showlegend=False)


def gondola_traces(store: Store, lang: str = DEFAULT_LANG) -> List:
    """Каркасы стеллажей: пол зала, боковины, задняя стенка, полки,
    контурные рёбра для чёткости."""
    traces: List = []
    panel = 0.03  # толщина панелей
    edges: list = []

    # пол торгового зала под всеми стеллажами
    if store.gondolas:
        x0 = min(g.x for g in store.gondolas) - 0.7
        x1 = max(g.x + g.width for g in store.gondolas) + 0.7
        y0 = min(g.y for g in store.gondolas) - 0.9
        y1 = max(g.y + g.depth for g in store.gondolas) + 0.6
        traces.append(cuboid(x0, y0, -0.025, x1 - x0, y1 - y0, 0.025,
                             FLOOR_COLOR, t(lang, "viz.floor"),
                             f"<b>{store.name}</b>"))

    for g in store.gondolas:
        top = max(s.z + s.clearance for s in g.shelves) + 0.05
        hover = t(lang, "viz.gondola_hover", name=g.name, width=g.width,
                 depth=g.depth)
        # боковины
        traces.append(cuboid(g.x - panel, g.y, 0, panel, g.depth, top,
                             FRAME_COLOR, g.name, hover))
        traces.append(cuboid(g.x + g.width, g.y, 0, panel, g.depth, top,
                             FRAME_COLOR, g.name, hover))
        cuboid_edges(g.x - panel, g.y, 0, panel, g.depth, top, edges)
        cuboid_edges(g.x + g.width, g.y, 0, panel, g.depth, top, edges)
        # задняя стенка
        traces.append(cuboid(g.x - panel, g.y + g.depth, 0,
                             g.width + 2 * panel, panel, top,
                             _shade(FRAME_COLOR, 1.06), g.name, hover,
                             opacity=0.6))
        # полки
        for s in g.shelves:
            traces.append(cuboid(
                g.x, g.y, s.z - panel, g.width, g.depth, panel,
                SHELF_COLOR, g.name,
                t(lang, "viz.shelf_hover", gondola=g.name,
                  n=s.index + 1, z=s.z)))
            # передняя кромка полки — контур для чёткости
            edges.append(((g.x, g.y, s.z), (g.x + g.width, g.y, s.z)))
            edges.append(((g.x, g.y, s.z - panel),
                          (g.x + g.width, g.y, s.z - panel)))
    traces.append(edges_trace(edges))
    return traces


def _product_hover(store: Store, sku: str, facings: int,
                   mode: str, sales: Optional[SalesInfo],
                   lang: str = DEFAULT_LANG) -> str:
    product = store.product(sku)
    supplier = store.supplier_of(sku)
    lines = [
        f"<b>{product.name}</b>",
        t(lang, "viz.hover.sku", sku=product.sku, category=product.category),
        t(lang, "viz.hover.supplier", name=supplier.name),
        t(lang, "viz.hover.facings", n=facings),
    ]
    if mode == "sales" and sales is not None:
        dos = ("∞" if sales.days_of_supply == float("inf")
               else f"{sales.days_of_supply:.1f}")
        lines += [
            t(lang, "viz.hover.stock", stock=sales.stock,
              capacity=sales.capacity, pct=sales.fill_ratio * 100),
            t(lang, "viz.hover.sold_today", n=sales.sold_today),
            t(lang, "viz.hover.sales_rate", rate=sales.sales_rate),
            t(lang, "viz.hover.days_of_supply", dos=dos),
        ]
        if sales.stock == 0:
            lines.append(t(lang, "viz.hover.out_of_stock"))
    return "<br>".join(lines)


def product_traces(store: Store, planogram: Planogram,
                   mode: str, lang: str = DEFAULT_LANG) -> List[go.Mesh3d]:
    """Фейсинги товара на полках.

    ``mode='approved'`` — цвет поставщика; ``mode='sales'`` — цвет по
    заполненности, при этом глубина стопки товара пропорциональна остатку.
    """
    traces: List[go.Mesh3d] = []
    gap = 0.005
    for p in planogram.placements:
        product = store.product(p.sku)
        gondola = store.gondola(p.gondola_id)
        shelf = gondola.shelf(p.shelf_index)
        sales = store.sales.get(p.sku)

        if mode == "sales" and sales is not None:
            color = (OOS_COLOR if sales.stock == 0
                     else fill_color(sales.fill_ratio))
            depth_ratio = max(0.18, sales.fill_ratio)  # видно и пустую полку
            opacity = 0.35 if sales.stock == 0 else 1.0
        else:
            color = store.supplier_of(p.sku).color
            depth_ratio = 1.0
            opacity = 1.0

        hover = _product_hover(store, p.sku, p.facings, mode, sales, lang)
        depth = min(product.depth * 3, gondola.depth) * depth_ratio
        for i in range(p.facings):
            # лёгкая вариация тона между фейсингами — объёмнее выкладка
            facing_color = _shade(color, 0.96 + 0.08 * ((i * 7 + 3) % 3) / 2)
            traces.append(cuboid(
                x=gondola.x + p.offset + i * product.width + gap,
                y=gondola.y + 0.02,
                z=shelf.z,
                dx=product.width - 2 * gap,
                dy=depth,
                dz=product.height,
                color=facing_color, name=product.name, hover=hover,
                opacity=opacity))
    return traces


def _legend_traces(store: Store, mode: str,
                   lang: str = DEFAULT_LANG) -> List[go.Scatter3d]:
    """Фиктивные точки для легенды."""
    traces = []
    if mode == "approved":
        for s in store.suppliers.values():
            traces.append(go.Scatter3d(
                x=[None], y=[None], z=[None], mode="markers",
                marker=dict(size=9, color=s.color, symbol="square"),
                name=s.name, showlegend=True))
    else:
        for key, val in [("viz.legend.full", 1.0),
                         ("viz.legend.medium", 0.5),
                         ("viz.legend.low", 0.25)]:
            traces.append(go.Scatter3d(
                x=[None], y=[None], z=[None], mode="markers",
                marker=dict(size=9, color=fill_color(val), symbol="square"),
                name=t(lang, key), showlegend=True))
        traces.append(go.Scatter3d(
            x=[None], y=[None], z=[None], mode="markers",
            marker=dict(size=9, color=OOS_COLOR, symbol="x"),
            name=t(lang, "viz.legend.oos"), showlegend=True))
    return traces


def build_figure(store: Store, lang: str = DEFAULT_LANG) -> go.Figure:
    """Единая 3D-сцена с переключением режимов кнопками:

    1. Текущее состояние продаж (фактическая выкладка, теплокарта остатков);
    2. Утверждённая планограмма (раскраска по поставщикам).
    """
    fig = go.Figure()

    frame = gondola_traces(store, lang)
    for tr in frame:
        fig.add_trace(tr)
    n_frame = len(frame)

    sales_traces = (product_traces(store, store.current_planogram, "sales",
                                   lang)
                    + _legend_traces(store, "sales", lang))
    for tr in sales_traces:
        fig.add_trace(tr)
    n_sales = len(sales_traces)

    approved_traces = (product_traces(store, store.approved_planogram,
                                      "approved", lang)
                       + _legend_traces(store, "approved", lang))
    for tr in approved_traces:
        tr.visible = False
        fig.add_trace(tr)
    n_approved = len(approved_traces)

    vis_sales = ([True] * n_frame + [True] * n_sales + [False] * n_approved)
    vis_approved = ([True] * n_frame + [False] * n_sales
                    + [True] * n_approved)

    title_sales = t(lang, "viz.title.sales", store=store.name)
    title_approved = t(lang, "viz.title.approved", store=store.name,
                       planogram=store.approved_planogram.name)

    fig.update_layout(
        title=dict(text=title_sales, x=0.5, y=0.93),
        updatemenus=[dict(
            type="buttons", direction="right",
            x=0.0, xanchor="left", y=1.18, yanchor="top",
            buttons=[
                dict(label=t(lang, "viz.button.sales"),
                     method="update",
                     args=[{"visible": vis_sales},
                           {"title.text": title_sales}]),
                dict(label=t(lang, "viz.button.approved"),
                     method="update",
                     args=[{"visible": vis_approved},
                           {"title.text": title_approved}]),
            ])],
        scene=dict(
            xaxis=dict(title="", range=[-0.8, 3.6], showbackground=False,
                       gridcolor="rgba(0,0,0,0.07)", zeroline=False,
                       tickfont=dict(size=10, color="#9aa1ab")),
            yaxis=dict(title="", range=[-1.2, 5.6], showbackground=False,
                       gridcolor="rgba(0,0,0,0.07)", zeroline=False,
                       tickfont=dict(size=10, color="#9aa1ab")),
            zaxis=dict(title=t(lang, "viz.axis.height"), range=[-0.03, 2.4],
                       showbackground=False,
                       gridcolor="rgba(0,0,0,0.05)", zeroline=False,
                       tickfont=dict(size=10, color="#9aa1ab"),
                       title_font=dict(size=11, color="#9aa1ab")),
            aspectmode="data",
            camera=dict(eye=dict(x=1.75, y=-1.65, z=0.75),
                        center=dict(x=0, y=0, z=-0.12)),
        ),
        legend=dict(x=1.0, y=0.9),
        margin=dict(l=0, r=0, t=90, b=0),
        template="plotly_white",
        paper_bgcolor="#f7f5f1",
    )
    return fig
