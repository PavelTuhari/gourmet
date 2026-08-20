"""3D-планограмма заправки: колонки, подземные цистерны, слив бензовоза.

Дух тот же, что у ``core/viz.py`` (планограмма магазина): кубоиды,
контурные рёбра, глубина/высота заливки как индикатор остатка. Разница —
здесь ``webapp``, а не ``core``: сцена читает данные топливного контура
(``peco_fuel.FuelNetwork``), которого core не знает и не должен знать
(направление зависимостей «контроллер → модель», см. ``docs/HANDOFF.md``).

Композиция сцены (важно для читаемости с первого взгляда):

* **z = 0 — уровень земли.** Площадка (асфальт) непрозрачна и лежит
  строго на этой отметке; всё, что ниже — подземное, всё выше —
  наземное оборудование.
* **Колонки (ТРК)** стоят на площадке (z ≥ 0), у каждой видны марки,
  которые она отпускает (маленькие цветные плашки на корпусе), общий
  навес объединяет их визуально в один островок раздачи.
* **Цистерны** — под грунтом (z < 0): полупрозрачный грунтовой блок
  «даёт заглянуть» внутрь, сама цистерна — контурная «стеклянная»
  оболочка с непрозрачной заливкой марки топлива внутри, высота заливки
  = остаток (тот же приём, что глубина стопки товара на полке
  в ``core/viz.product_traces``). От горловины цистерны вверх до земли
  идёт цветной пилон-люк — по нему бензовоз сливает топливо.
* **Бензовоз** (только когда идёт слив) стоит у люка нужной цистерны,
  рукав — линия от кузова до люка; прогресс слива подписан в hover.
"""

from typing import List, Optional

import plotly.graph_objects as go

from ..core.viz import cuboid, cuboid_edges, edges_trace
from .i18n import DEFAULT_LANG, t
from .peco_fuel import FUEL_GRADES, station_tanks

ASPHALT_COLOR = "#b7bbc3"
SOIL_COLOR = "#8a6a49"
CANOPY_COLOR = "#2f4b68"
COLUMN_COLOR = "#5a6b7f"
SHELL_COLOR = "#c7ccd1"
TRUCK_COLOR = "#eceff1"
HOSE_COLOR = "#26323d"

# ---- геометрия сцены (метры, локальная система координат станции) --------
#
# Раньше подземный контур рисовался сплошным полупрозрачным «грунтовым»
# кубоидом поверх цистерн — при обзоре сверху-сбоку (типичный ракурс
# читаемой 3D-сцены, см. `core/viz.build_figure`) верхняя грань этого
# кубоида визуально закрывала цистерны под собой почти полностью, хотя
# opacity была низкой (Mesh3d рисует грань как заливку, не как дымку).
# Поэтому «подземность» здесь показана иначе — приёмом технического
# чертежа-разреза: цистерны рисуются как есть (без всего, что могло бы
# их закрыть), а «это раскоп» читается по (1) каркасу котлована
# (вертикальные рёбра от нулевой отметки вниз до дна и рамка понизу —
# `_pit_wireframe`), (2) отметке 0 на оси высоты и линии нулевого уровня,
# (3) пилонам-горловинам, которые физически поднимаются от цистерны к
# земле. Тот же принцип, что и в сцене магазина: только те примитивы,
# что реально помогают прочитать сцену, без декоративной заливки.
GROUND_Z = 0.0
FORECOURT = (-1.5, -1.2, 12.0, 3.6)     # x0, y0, x1, y1 — площадка колонок
TANKYARD = (-1.5, 7.0, 12.0, 13.7)      # x0, y0, x1, y1 — котлован цистерн
TANK_DEPTH_TOP = -1.7                    # верх цистерны — глубина укрытия
TANK_DZ = 1.5                            # диаметр (по высоте) цистерны
TANK_DY = 4.2                            # длина цистерны (вдоль y — вглубь
                                          # котлована, как в реальном ряду
                                          # подземных резервуаров АЗС)
TANK_DX = 1.4                            # ширина цистерны (по x)
TANK_GAP_X = 0.7                         # промежуток между цистернами —
                                          # обязателен, иначе 4 цветные
                                          # заливки сливаются в одну полосу
DISPENSER_XS = (1.4, 5.2, 9.0)           # 3 колонки под общим навесом
DISPENSER_Y = 1.8
CANOPY_Z = 3.3


def _tank_position(i: int) -> tuple:
    """Координаты угла (x, y, z-верх) i-й цистерны в ряду под грунтом.

    Ряд разнесён по x (ширина станции), не по y (глубина котлована) —
    так все 4 цистерны видны раздельно на типичном ракурсе сцены; вдоль
    y все они выстроены на одном уровне (реальная компоновка АЗС: ряд
    цистерн параллелен фасаду, перпендикулярен проезду к колонкам)."""
    step = TANK_DX + TANK_GAP_X
    total = 4 * TANK_DX + 3 * TANK_GAP_X
    x0 = (TANKYARD[0] + TANKYARD[2]) / 2 - total / 2 + i * step
    y0 = TANKYARD[1] + 1.4
    return x0, y0, TANK_DEPTH_TOP


def _pit_wireframe(edges: list) -> None:
    """Каркас котлована: рамка по нулевой отметке, рамка по дну, вертикали
    по углам — читается как «здесь земля вырыта», не закрывая цистерны."""
    tx0, ty0, tx1, ty1 = TANKYARD
    bottom = TANK_DEPTH_TOP - TANK_DZ - 0.5
    corners_top = [(tx0, ty0, GROUND_Z), (tx1, ty0, GROUND_Z),
                   (tx1, ty1, GROUND_Z), (tx0, ty1, GROUND_Z)]
    corners_bot = [(tx0, ty0, bottom), (tx1, ty0, bottom),
                  (tx1, ty1, bottom), (tx0, ty1, bottom)]
    for i in range(4):
        edges.append((corners_top[i], corners_top[(i + 1) % 4]))
        edges.append((corners_bot[i], corners_bot[(i + 1) % 4]))
        edges.append((corners_top[i], corners_bot[i]))


def _ground_traces(lang: str, station_name: str) -> List:
    """Площадка (непрозрачный асфальт) + каркас котлована цистерн."""
    traces: List = []
    edges: list = []
    fx0, fy0, fx1, fy1 = FORECOURT
    traces.append(cuboid(fx0, fy0, -0.12, fx1 - fx0, fy1 - fy0, 0.12,
                         ASPHALT_COLOR, t(lang, "fuelviz.ground_hover",
                                          name=station_name)))
    _pit_wireframe(edges)
    traces.append(edges_trace(edges, color="#5b4632", width=2.6))
    return traces


def _dispenser_traces(lang: str, grades: List[dict]) -> List:
    """Колонки (ТРК) на площадке под общим навесом — каждая отпускает
    все марки станции, что видно по цветным плашкам на корпусе (то,
    что видит покупатель, п.1 требования владельца)."""
    traces: List = []
    edges: list = []
    fx0 = min(DISPENSER_XS) - 1.0
    fx1 = max(DISPENSER_XS) + 1.0
    # навес на 4 колоннах
    for cx in (fx0 + 0.3, fx1 - 0.3):
        for cy in (DISPENSER_Y - 0.6, DISPENSER_Y + 0.6):
            traces.append(cuboid(cx, cy, 0, 0.18, 0.18, CANOPY_Z,
                                 COLUMN_COLOR, t(lang, "fuelviz.canopy_hover")))
    # навес нарочно короче в глубину (y), чем площадка колонок: с этим
    # ракурсом сцены (см. камеру ниже) слишком глубокий навес проецируется
    # своим дальним краем поверх цистерн и закрывает их — навес обязан
    # накрывать только сами колонки, не тянуться к котловану
    traces.append(cuboid(fx0, DISPENSER_Y - 0.9, CANOPY_Z,
                         fx1 - fx0, 1.8, 0.18, CANOPY_COLOR,
                         t(lang, "fuelviz.canopy_hover"), opacity=0.92))
    for dx in DISPENSER_XS:
        # тумба-остров
        traces.append(cuboid(dx - 0.65, DISPENSER_Y - 0.45, 0, 1.3, 0.9,
                             0.14, "#9aa1ab", t(lang, "fuelviz.dispenser_hover")))
        # корпус колонки
        traces.append(cuboid(dx - 0.32, DISPENSER_Y - 0.16, 0.14, 0.64,
                             0.32, 1.35, "#e8eaed",
                             t(lang, "fuelviz.dispenser_hover",
                               grades=", ".join(g["grade"] for g in grades))))
        cuboid_edges(dx - 0.32, DISPENSER_Y - 0.16, 0.14, 0.64, 0.32, 1.35,
                    edges)
        # плашки марок — видно, какое топливо отпускает колонка
        for gi, g in enumerate(grades):
            traces.append(cuboid(dx - 0.28, DISPENSER_Y - 0.15
                                 + gi * 0.09, 0.35 + gi * 0.26, 0.56, 0.05,
                                 0.18, g["color"],
                                 t(lang, "fuelviz.dispenser_grade_hover",
                                   grade=g["grade"])))
    traces.append(edges_trace(edges))
    return traces


def _tank_traces(lang: str, tanks: List[dict], unload_target: Optional[int]
                 ) -> List:
    """Подземные цистерны: контурная оболочка + заливка по марке/уровню
    (высота = остаток — тот же принцип, что глубина стопки товара на
    полке магазина), плюс пилон-люк до земли."""
    traces: List = []
    edges: list = []
    for i, tank in enumerate(tanks):
        x0, y0, ztop = _tank_position(i)
        zbot = ztop - TANK_DZ
        hover = t(lang, "fuelviz.tank_hover", grade=tank["grade"],
                  cur=tank["current_l"], cap=tank["capacity_l"],
                  pct=round(tank["fill_ratio"] * 100))
        # оболочка цистерны — полупрозрачная «стеклянная», чтобы был
        # виден уровень внутри
        traces.append(cuboid(x0, y0, zbot, TANK_DX, TANK_DY, TANK_DZ,
                             SHELL_COLOR, hover, opacity=0.24))
        cuboid_edges(x0, y0, zbot, TANK_DX, TANK_DY, TANK_DZ, edges)
        # заливка: высота пропорциональна остатку, цвет — марка топлива
        fill_h = max(0.05, TANK_DZ * tank["fill_ratio"])
        traces.append(cuboid(x0 + 0.08, y0 + 0.08, zbot + 0.04,
                             TANK_DX - 0.16, TANK_DY - 0.16, fill_h - 0.08,
                             tank["color"], hover, opacity=0.94))
        # пилон-люк от горловины цистерны до земли — по нему сливает бензовоз
        hx, hy = x0 + TANK_DX / 2, y0 + TANK_DY / 2
        traces.append(cuboid(hx - 0.13, hy - 0.13, ztop, 0.26, 0.26,
                             -ztop, tank["color"],
                             t(lang, "fuelviz.hatch_hover", grade=tank["grade"]),
                             opacity=0.85 if i == unload_target else 0.55))
    traces.append(edges_trace(edges))
    return traces


def _truck_traces(lang: str, tanks: List[dict], target_idx: int,
                  info: dict) -> List:
    """Бензовоз у горловины нужной цистерны + сливной рукав — разгрузка
    видна как процесс (прогресс в hover и высотой заливки цистерны,
    которая уже растёт вместе с ним, см. ``peco_fuel._evolve_trips``)."""
    traces: List = []
    edges: list = []
    x0, y0, ztop = _tank_position(target_idx)
    hx, hy = x0 + TANK_DX / 2, y0 + TANK_DY / 2
    truck_y = TANKYARD[1] - 0.7        # у края котлована, рукав тянется к люку
    hover = t(lang, "fuelviz.truck_hover", driver=info["driver"],
             liters=info["liters"], pct=round(info["frac"] * 100))
    # кабина
    traces.append(cuboid(hx - 0.6, truck_y - 1.9, 0, 1.1, 1.7, 1.55,
                         TRUCK_COLOR, hover))
    # цистерна на шасси
    traces.append(cuboid(hx - 0.55, truck_y - 0.15, 0.35, 1.05, 3.1, 1.35,
                         "#78909c", hover, opacity=0.95))
    cuboid_edges(hx - 0.55, truck_y - 0.15, 0.35, 1.05, 3.1, 1.35, edges)
    traces.append(edges_trace(edges, color="#37474f"))
    # рукав: от кузова к люку цистерны — виден как процесс, не просто
    # «машина стоит рядом» (требование владельца, п.3)
    hose = [((hx, truck_y - 0.15, 1.0), (hx, y0 + TANK_DY / 2, 1.0)),
           ((hx, y0 + TANK_DY / 2, 1.0), (hx, hy, 0.15)),
           ((hx, hy, 0.15), (hx, hy, ztop))]
    traces.append(edges_trace(hose, color=HOSE_COLOR, width=5.0))
    # маркер прогресса слива — виден в hover и подписан прямо на сцене
    traces.append(go.Scatter3d(
        x=[hx], y=[truck_y - 1.5], z=[2.1], mode="markers+text",
        marker=dict(size=7, color="#ffb300", symbol="diamond"),
        text=[t(lang, "fuelviz.truck_label", pct=round(info["frac"] * 100))],
        textposition="top center", textfont=dict(size=11, color="#c62828"),
        hovertext=hover, hoverinfo="text", showlegend=False))
    return traces


def _legend_traces(lang: str) -> List[go.Scatter3d]:
    traces = []
    for grade, color, _ in FUEL_GRADES:
        traces.append(go.Scatter3d(
            x=[None], y=[None], z=[None], mode="markers",
            marker=dict(size=9, color=color, symbol="square"),
            name=grade, showlegend=True))
    return traces


def build_station_figure(station: dict, unload: Optional[dict],
                         lang: str = DEFAULT_LANG,
                         compact: bool = False) -> go.Figure:
    """Собрать 3D-сцену станции.

    ``station`` — запись из ``FuelNetwork.state()["stations"]`` (id,
    name, capacity_l, current_l, ...). ``unload`` — ``None``, если
    сейчас никто не сливает, иначе ``{"driver", "liters", "frac"}`` —
    какая цистерна получит топливо, выбирается как наименее заполненная
    (правдоподобный адресат реальной доливки; per-марочный адрес рейса
    контур не хранит — см. docstring ``station_tanks``).

    ``compact`` — режим для маленького демонстрационного окна (владелец
    проверил: в окне ~720×520 обычная сцена занимает треть кадра, а
    подписи осей съедают место): камера ближе (сцена заполняет кадр),
    подписи осей и легенда убраны, поля минимальны.
    """
    tanks = station_tanks(station)
    fig = go.Figure()
    for tr in _ground_traces(lang, station["name"]):
        fig.add_trace(tr)
    for tr in _dispenser_traces(lang, tanks):
        fig.add_trace(tr)

    target_idx = min(range(len(tanks)), key=lambda i: tanks[i]["fill_ratio"])
    for tr in _tank_traces(lang, tanks, target_idx if unload else None):
        fig.add_trace(tr)
    if unload:
        for tr in _truck_traces(lang, tanks, target_idx, unload):
            fig.add_trace(tr)
    if not compact:
        for tr in _legend_traces(lang):
            fig.add_trace(tr)

    # В компактном режиме страница рисует свою плашку с названием станции
    # поверх сцены, поэтому заголовок самой фигуры убираем — иначе две
    # подписи накладываются друг на друга и обе становятся нечитаемыми.
    title = "" if compact else t(lang, "fuelviz.title", name=station["name"])
    axis_common = dict(showbackground=False, zeroline=False,
                       showticklabels=not compact,
                       tickfont=dict(size=10, color="#9aa1ab"))
    fig.update_layout(
        title=dict(text=title, x=0.5, y=0.95, font=dict(size=13)),
        scene=dict(
            xaxis=dict(title="", range=[-3, 14],
                      gridcolor="rgba(0,0,0,0.06)", **axis_common),
            yaxis=dict(title="", range=[-4, 14],
                      gridcolor="rgba(0,0,0,0.06)", **axis_common),
            zaxis=dict(title="" if compact else t(lang, "fuelviz.axis.height"),
                      range=[-4.4, 4.2],
                      gridcolor="rgba(0,0,0,0.05)", zeroline=True,
                      zerolinecolor="#5b4632", zerolinewidth=2,
                      showbackground=False,
                      showticklabels=not compact,
                      tickfont=dict(size=10, color="#9aa1ab"),
                      title_font=dict(size=11, color="#9aa1ab")),
            aspectmode="data",
            # ортографическая проекция — без неё перспектива с таким
            # разбросом глубины (площадка + котлован ~17 м по y) сильно
            # сжимает дальние цистерны к линии горизонта, и они
            # визуально «слипаются» у края котлована вместо читаемого
            # ряда с равными промежутками. В компакте камера придвинута
            # ближе — сцена заполняет маленький кадр, а не треть его.
            camera=dict(eye=(dict(x=0.82, y=-1.35, z=1.55) if compact
                             else dict(x=1.1, y=-1.9, z=2.15)),
                       center=dict(x=0.08, y=0.1, z=-0.1),
                       projection=dict(type="orthographic")),
        ),
        showlegend=not compact,
        legend=dict(x=1.0, y=0.9, title=dict(
            text=t(lang, "fuelviz.legend_title"))),
        margin=(dict(l=0, r=0, t=40, b=0) if compact
               else dict(l=0, r=0, t=90, b=0)),
        template="plotly_white",
        paper_bgcolor="#f7f5f1",
    )
    return fig


def build_station_page(station: dict, unload: Optional[dict],
                       back_url: str, lang: str = DEFAULT_LANG,
                       include_plotlyjs=True, compact: bool = False,
                       demo: bool = False) -> str:
    """Автономная HTML-страница сцены + шапка со сводкой по станции.

    ``compact`` — компактная демонстрационная вёрстка (см.
    ``build_station_figure``): сцена почти во весь кадр, вместо таблицы
    цистерн и ссылок — одна крупная строка-подпись фазы наверху, чтобы
    в маленьком окне сразу было видно, что происходит."""
    fig = build_station_figure(station, unload, lang, compact=compact)
    page = fig.to_html(include_plotlyjs=include_plotlyjs, full_html=True,
                       default_height=("94vh" if compact else "78vh"))
    tanks = station_tanks(station)

    if compact:
        caption = (
            f'🚛 {t(lang, "fuelviz.panel.unloading", driver=unload["driver"], liters=unload["liters"], pct=round(unload["frac"] * 100))}'
            if unload else f'⛽ {station["name"]}')
        panel = (
            '<div style="position:fixed;top:0;left:0;right:0;z-index:9;'
            'padding:6px 14px;font-family:sans-serif;font-size:15px;'
            'font-weight:700;color:#8a4b00;background:rgba(255,243,224,.94);'
            'border-bottom:2px solid #ffcc80;text-align:center">'
            f'{caption}</div>')
        if demo:
            # Сценарный обход: досмотрев слив, страница сама возвращается
            # на карту, чтобы показ поехал к следующей остановке рейса.
            # Слив в эмуляторе короткий, поэтому ждём не «конца слива» по
            # состоянию, а фиксированной паузы: иначе на быстрых станциях
            # страница успевала бы моргнуть и уйти обратно мгновенно.
            panel += (
                '<script>setTimeout(function () { location.href = '
                f'{back_url!r}; }}, 6500);</script>')
        return page.replace("</body>", panel + "</body>")

    rows = "".join(
        f'<tr><td style="padding:4px 10px"><span style="display:inline-block;'
        f'width:10px;height:10px;border-radius:2px;background:{tk["color"]};'
        f'margin-right:6px"></span>{tk["grade"]}</td>'
        f'<td style="padding:4px 10px;text-align:right">{tk["current_l"]:,}'
        f' / {tk["capacity_l"]:,} {t(lang, "unit.liters_short")}</td>'
        f'<td style="padding:4px 10px;text-align:right">'
        f'{round(tk["fill_ratio"] * 100)}%</td></tr>'
        for tk in tanks).replace(",", " ")
    unload_html = ""
    if unload:
        unload_html = (
            '<div style="margin-top:10px;padding:8px 12px;background:'
            '#fff3e0;border:1px solid #ffcc80;border-radius:8px;'
            'font-family:sans-serif;font-size:13px;color:#8a4b00">'
            f'🚛 {t(lang, "fuelviz.panel.unloading", driver=unload["driver"], liters=unload["liters"], pct=round(unload["frac"] * 100))}'
            '</div>')
    panel = (
        '<div style="max-width:640px;margin:0 auto 1em;font-family:sans-serif">'
        f'<p><a href="{back_url}">{t(lang, "fuelviz.back_to_map")}</a></p>'
        f'<h3 style="margin:4px 0">{station["name"]} '
        f'<span style="font-weight:400;color:#5b6672;font-size:13px">'
        f'({station.get("code", "")}, {station.get("region", "")})</span></h3>'
        '<table style="border-collapse:collapse;font-size:13.5px">'
        f'{rows}</table>'
        f'{unload_html}'
        '</div>')
    return page.replace("</body>", panel + "</body>")
