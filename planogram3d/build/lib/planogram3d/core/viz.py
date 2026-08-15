"""Трёхмерная визуализация планограммы (Plotly).

Два режима раскраски товара:

* ``approved`` — цвет поставщика (визуализация утверждённой планограммы);
* ``sales``    — теплокарта по заполненности полки (текущее состояние
  продаж): зелёный — полная выкладка, красный — пусто/out-of-stock.
"""

from typing import List, Optional

import plotly.graph_objects as go

from .models import Planogram, SalesInfo, Store

FRAME_COLOR = "#8a8f98"       # каркас стеллажа
SHELF_COLOR = "#c7ccd4"       # полки
OOS_COLOR = "#d62728"         # out-of-stock


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


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
        lighting=dict(ambient=0.55, diffuse=0.7, specular=0.15,
                      roughness=0.9),
        lightposition=dict(x=2, y=-4, z=6),
    )


def gondola_traces(store: Store) -> List[go.Mesh3d]:
    """Каркасы стеллажей: боковины, задняя стенка, полки."""
    traces: List[go.Mesh3d] = []
    panel = 0.03  # толщина панелей
    for g in store.gondolas:
        top = max(s.z + s.clearance for s in g.shelves) + 0.05
        hover = f"<b>{g.name}</b><br>{g.width:.1f} × {g.depth:.1f} м"
        # боковины
        traces.append(cuboid(g.x - panel, g.y, 0, panel, g.depth, top,
                             FRAME_COLOR, g.name, hover))
        traces.append(cuboid(g.x + g.width, g.y, 0, panel, g.depth, top,
                             FRAME_COLOR, g.name, hover))
        # задняя стенка
        traces.append(cuboid(g.x - panel, g.y + g.depth, 0,
                             g.width + 2 * panel, panel, top,
                             FRAME_COLOR, g.name, hover, opacity=0.55))
        # полки
        for s in g.shelves:
            traces.append(cuboid(
                g.x, g.y, s.z - panel, g.width, g.depth, panel,
                SHELF_COLOR, g.name,
                f"<b>{g.name}</b><br>Полка {s.index + 1} "
                f"(h={s.z:.2f} м)"))
    return traces


def _product_hover(store: Store, sku: str, facings: int,
                   mode: str, sales: Optional[SalesInfo]) -> str:
    product = store.product(sku)
    supplier = store.supplier_of(sku)
    lines = [
        f"<b>{product.name}</b>",
        f"SKU: {product.sku} · {product.category}",
        f"Поставщик: {supplier.name}",
        f"Фейсингов: {facings}",
    ]
    if mode == "sales" and sales is not None:
        dos = ("∞" if sales.days_of_supply == float("inf")
               else f"{sales.days_of_supply:.1f}")
        lines += [
            f"Остаток: {sales.stock} из {sales.capacity} шт. "
            f"({sales.fill_ratio * 100:.0f}%)",
            f"Продано сегодня: {sales.sold_today} шт.",
            f"Скорость продаж: {sales.sales_rate:.1f} шт./день",
            f"Запас: {dos} дн.",
        ]
        if sales.stock == 0:
            lines.append("⚠ OUT-OF-STOCK")
    return "<br>".join(lines)


def product_traces(store: Store, planogram: Planogram,
                   mode: str) -> List[go.Mesh3d]:
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

        hover = _product_hover(store, p.sku, p.facings, mode, sales)
        depth = min(product.depth * 3, gondola.depth) * depth_ratio
        for i in range(p.facings):
            traces.append(cuboid(
                x=gondola.x + p.offset + i * product.width + gap,
                y=gondola.y + 0.02,
                z=shelf.z,
                dx=product.width - 2 * gap,
                dy=depth,
                dz=product.height,
                color=color, name=product.name, hover=hover,
                opacity=opacity))
    return traces


def _legend_traces(store: Store, mode: str) -> List[go.Scatter3d]:
    """Фиктивные точки для легенды."""
    traces = []
    if mode == "approved":
        for s in store.suppliers.values():
            traces.append(go.Scatter3d(
                x=[None], y=[None], z=[None], mode="markers",
                marker=dict(size=9, color=s.color, symbol="square"),
                name=s.name, showlegend=True))
    else:
        for label, val in [("Полная выкладка (≥90%)", 1.0),
                           ("Средний остаток (~50%)", 0.5),
                           ("Низкий остаток (≤30%)", 0.25)]:
            traces.append(go.Scatter3d(
                x=[None], y=[None], z=[None], mode="markers",
                marker=dict(size=9, color=fill_color(val), symbol="square"),
                name=label, showlegend=True))
        traces.append(go.Scatter3d(
            x=[None], y=[None], z=[None], mode="markers",
            marker=dict(size=9, color=OOS_COLOR, symbol="x"),
            name="Out-of-stock", showlegend=True))
    return traces


def build_figure(store: Store) -> go.Figure:
    """Единая 3D-сцена с переключением режимов кнопками:

    1. Текущее состояние продаж (фактическая выкладка, теплокарта остатков);
    2. Утверждённая планограмма (раскраска по поставщикам).
    """
    fig = go.Figure()

    frame = gondola_traces(store)
    for tr in frame:
        fig.add_trace(tr)
    n_frame = len(frame)

    sales_traces = (product_traces(store, store.current_planogram, "sales")
                    + _legend_traces(store, "sales"))
    for tr in sales_traces:
        fig.add_trace(tr)
    n_sales = len(sales_traces)

    approved_traces = (product_traces(store, store.approved_planogram,
                                      "approved")
                       + _legend_traces(store, "approved"))
    for tr in approved_traces:
        tr.visible = False
        fig.add_trace(tr)
    n_approved = len(approved_traces)

    vis_sales = ([True] * n_frame + [True] * n_sales + [False] * n_approved)
    vis_approved = ([True] * n_frame + [False] * n_sales
                    + [True] * n_approved)

    title_sales = (f"{store.name} — текущее состояние продаж "
                   f"(фактическая выкладка)")
    title_approved = (f"{store.name} — {store.approved_planogram.name} "
                      f"(регламент + контракты с поставщиками)")

    fig.update_layout(
        title=dict(text=title_sales, x=0.5, y=0.93),
        updatemenus=[dict(
            type="buttons", direction="right",
            x=0.0, xanchor="left", y=1.18, yanchor="top",
            buttons=[
                dict(label="📊 Текущее состояние продаж",
                     method="update",
                     args=[{"visible": vis_sales},
                           {"title.text": title_sales}]),
                dict(label="📋 Утверждённая планограмма",
                     method="update",
                     args=[{"visible": vis_approved},
                           {"title.text": title_approved}]),
            ])],
        scene=dict(
            xaxis=dict(title="X, м", range=[-0.5, 3.5]),
            yaxis=dict(title="Y, м", range=[-1.0, 5.5]),
            zaxis=dict(title="Высота, м", range=[0, 2.4]),
            aspectmode="data",
            camera=dict(eye=dict(x=1.9, y=-1.9, z=0.9)),
        ),
        legend=dict(x=1.0, y=0.9),
        margin=dict(l=0, r=0, t=90, b=0),
        template="plotly_white",
    )
    return fig
