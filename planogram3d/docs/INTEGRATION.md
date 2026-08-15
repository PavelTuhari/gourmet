# Интеграция planogram3d в другие приложения

Ядро `planogram3d.core` спроектировано как встраиваемая библиотека:
чистая модель данных на dataclasses, проверки и визуализация — обычные
функции без глобального состояния, единственная зависимость — `plotly`.
Справочник API — в [LIBRARY.md](LIBRARY.md).

## Установка

Из клона репозитория (каталог `planogram3d` — самостоятельный
pip-пакет со своим `pyproject.toml`):

```bash
pip install ./planogram3d
```

Прямо из git:

```bash
pip install "git+https://github.com/PavelTuhari/gourmet.git#subdirectory=planogram3d"
```

Либо просто скопируйте каталог `planogram3d/` (вендоринг) в свой проект —
внешних зависимостей, кроме `plotly>=5.0`, нет.

После установки доступны пакет `planogram3d` и консольная команда
`planogram3d` (демо-отчёт).

## Быстрый старт

```python
from planogram3d.core import check_compliance, save_report
from planogram3d.sample_data import build_demo_store   # или ваш Store

store = build_demo_store()

violations = check_compliance(store)
for v in violations:
    print(v.severity, v.group, v.where, "—", v.message)

save_report(store, "report.html")   # 3D-сцена + таблица нарушений
```

## Наполнение Store своими данными

Единственная точка входа для данных — объект `Store`. Соберите его из
своей учётной системы, БД или выгрузок; библиотеке всё равно, откуда
пришли данные. Скелет адаптера:

```python
from planogram3d.core import (Store, Gondola, Shelf, Product, Supplier,
                              Contract, Placement, Planogram, SalesInfo,
                              Regulations)

def load_store(store_id: str) -> Store:
    store = Store(store_id=store_id, name="Мой магазин",
                  regulations=Regulations(max_weight_high_shelf=6.0))

    # 1. справочники
    store.suppliers["SUP-1"] = Supplier("SUP-1", "Поставщик №1", "#4E79A7")
    store.products["SKU-1"] = Product(
        sku="SKU-1", name="Товар", category="Бакалея", supplier_id="SUP-1",
        width=0.15, height=0.25, depth=0.08, weight=0.9)

    # 2. торговый зал
    shelves = [Shelf(i, z=0.1 + i * 0.4, clearance=0.35) for i in range(5)]
    store.gondolas.append(Gondola("G1", "Стеллаж 1", x=0, y=0,
                                  width=2.4, depth=0.5, shelves=shelves))

    # 3. контракты
    store.contracts.append(Contract(
        "SUP-1", min_share_pct=20.0,
        mandatory_skus={"SKU-1": 4}, eye_level_skus=["SKU-1"]))

    # 4. планограммы: утверждённая и фактическая
    store.approved_planogram = Planogram("Планограмма v1", [
        Placement("SKU-1", "G1", shelf_index=3, offset=0.1, facings=4)])
    store.current_planogram = load_realogram_from_db(store_id)  # ваша функция

    # 5. продажи/остатки
    store.sales["SKU-1"] = SalesInfo("SKU-1", stock=7, capacity=12,
                                     sold_today=5, sales_rate=6.5)
    return store
```

### Пример: загрузка из CSV (pandas)

```python
import pandas as pd
from planogram3d.core import Placement, Planogram

def planogram_from_csv(path: str, name: str) -> Planogram:
    df = pd.read_csv(path)  # колонки: sku,gondola_id,shelf_index,offset,facings
    return Planogram(name, [
        Placement(r.sku, r.gondola_id, int(r.shelf_index),
                  float(r.offset), int(r.facings))
        for r in df.itertuples()])
```

## Собственные правила проверки

`check_compliance` принимает `extra_checks` — список ваших функций
`Store -> List[Violation]`. Так добавляются правила конкретной сети,
не трогая код библиотеки:

```python
from planogram3d.core import Violation, check_compliance

def check_snack_share(store):
    """Регламент сети: снеки — не более 25% фейсингов."""
    out = []
    placements = store.current_planogram.placements
    total = sum(p.facings for p in placements)
    snacks = sum(p.facings for p in placements
                 if store.product(p.sku).category == "Снеки")
    if total and snacks / total > 0.25:
        out.append(Violation(
            "regulation", "warning", "Категория «Снеки»",
            f"Доля снеков {100 * snacks / total:.0f}% превышает 25%"))
    return out

violations = check_compliance(store, extra_checks=[check_snack_share])
```

Группы (`regulation`, `contract`, `planogram`, `sales`) и уровни
(`critical`, `warning`) лучше переиспользовать — тогда нарушения
автоматически попадут в нужные секции готовых отчётов.

## Сценарии встраивания визуализации

### Веб-приложение (Flask, Django, FastAPI)

Готовую страницу отдаёт `build_report_page`; для страницы полегче
подключайте plotly из CDN:

```python
from flask import Flask
from planogram3d.core import build_report_page

app = Flask(__name__)

@app.get("/planogram/<store_id>")
def planogram(store_id):
    store = load_store(store_id)
    return build_report_page(store, include_plotlyjs="cdn")
```

Если у вас свой шаблон страницы, встраивайте части по отдельности:
`build_figure(store).to_html(full_html=False)` — только div со сценой,
`render_html_report(violations)` — только таблица нарушений.

### Jupyter / ноутбуки

```python
from planogram3d.core import build_figure
build_figure(store).show()
```

### Dash

```python
from dash import Dash, dcc
from planogram3d.core import build_figure

app = Dash(__name__)
app.layout = dcc.Graph(figure=build_figure(store), style={"height": "80vh"})
```

### Статичные изображения (PNG/SVG для писем и презентаций)

```python
pip install kaleido
```

```python
build_figure(store).write_image("planogram.png", width=1400, height=900)
```

### Zabbix: активные проблемы магазинов на карте

Веб-режим (`planogram3d.webapp`) умеет показывать на маркере каждого
магазина число активных проблем из Zabbix (бейдж с цветом по максимальной
severity) и их список в карточке. Провайдер выбирается автоматически:

* заданы `ZABBIX_URL` и `ZABBIX_TOKEN` → реальный Zabbix API
  (JSON-RPC `problem.get`, аутентификация API-токеном, Zabbix ≥ 5.4);
  соответствие «магазин → хост Zabbix» задаётся через
  `ZABBIX_HOSTS="st17=store-17.local,st03=store-03.local"`
  (по умолчанию имя хоста совпадает с id магазина);
* переменные не заданы → встроенный эмулятор торгового мониторинга.

Модуль `planogram3d.webapp.zabbix` можно использовать и отдельно:

```python
from planogram3d.webapp.zabbix import ZabbixClient

client = ZabbixClient("https://zabbix.example.com", token,
                      host_map={"st17": "store-17.local"})
print(client.problems())
# {"st17": {"active": 2, "worst": 4, "problems": [
#     {"name": "Касса №2: нет связи", "severity": 4, "age_sec": 512}, ...]}}
```

При недоступности Zabbix карта продолжает работать — счётчики проблем
просто обнуляются, ошибка пишется в лог сервера.

### Мониторинг и алерты (без визуализации)

Ядро можно использовать и headless — например, в кроне/воркере,
рассылающем алерты только по критичным нарушениям:

```python
from planogram3d.core import check_compliance, render_console_report

violations = [v for v in check_compliance(store) if v.severity == "critical"]
if violations:
    notify_manager(render_console_report(violations))  # ваша доставка
```

## Собственные 3D-сцены

`build_figure` покрывает типовой случай «два режима + легенда». Если
нужна своя компоновка (одна планограмма, свой цветовой код, свои
подписи), собирайте сцену из низкоуровневых блоков:

```python
import plotly.graph_objects as go
from planogram3d.core.viz import gondola_traces, product_traces

fig = go.Figure()
for tr in gondola_traces(store):                       # каркасы стеллажей
    fig.add_trace(tr)
for tr in product_traces(store, store.approved_planogram, "approved"):
    fig.add_trace(tr)
fig.update_layout(scene=dict(aspectmode="data"))
```

`cuboid(...)` из того же модуля строит произвольный параллелепипед
(`Mesh3d`) — им можно дорисовать кассы, паллеты, промо-зоны.

## Что важно знать

* Все размеры — в метрах, вес — в килограммах; полки нумеруются снизу
  с нуля (см. «Соглашения» в LIBRARY.md).
* Регламент и контракты проверяются по `current_planogram`; если она не
  задана — по `approved_planogram`. Расхождения «факт vs утверждённая»
  считаются только когда заданы обе.
* `SalesInfo` привязана к SKU (не к конкретной полке): остаток и
  скорость продаж агрегируются по всем выкладкам SKU в магазине.
* Библиотека не тянет БД и веб-фреймворков — только `plotly`; модель
  данных (`core/models.py`) вообще не имеет внешних зависимостей и
  безопасна для импорта в любом окружении.
