# planogram3d.core — справочник по библиотеке

Переиспользуемое ядро для 3D-визуализации планограмм магазина и проверки
выкладки на соответствие внутреннему регламенту и контрактам с
поставщиками. Единственная внешняя зависимость — `plotly`.

Как встроить библиотеку в своё приложение — см.
[INTEGRATION.md](INTEGRATION.md).

## Архитектура

```
planogram3d
├── core/                ← ядро (переиспользуемая библиотека)
│   ├── models.py        ← модель данных (dataclasses, без зависимостей)
│   ├── rules.py         ← движок проверки соответствия
│   ├── viz.py           ← построение 3D-сцены (plotly)
│   └── report.py        ← отчёты: консоль, HTML-блок, полная страница
├── sample_data.py       ← демонстрационный магазин
└── app.py               ← демонстрационное CLI поверх ядра
```

Зависимости между модулями ядра направлены строго вниз:
`report → rules, viz → models`. Модель данных не знает ни о проверках,
ни о визуализации, поэтому её можно наполнять из любого источника
(БД, API учётной системы, CSV-выгрузки).

Весь публичный API реэкспортируется из `planogram3d.core` (и продублирован
в корне пакета `planogram3d`):

```python
from planogram3d.core import (
    # модель данных
    Store, Gondola, Shelf, Product, Supplier, Contract,
    Placement, Planogram, SalesInfo, Regulations,
    # проверка соответствия
    Violation, check_compliance, check_regulations, check_contracts,
    check_against_approved, check_sales,
    # 3D-визуализация
    build_figure, cuboid, fill_color,
    # отчёты
    build_report_page, save_report,
    render_console_report, render_html_report,
)
```

## Соглашения

* Все размеры и координаты — в **метрах**, вес — в **килограммах**.
* Система координат зала: **X** — вдоль стеллажа (ширина), **Y** — вглубь
  зала, **Z** — высота от пола. Начало координат — угол торгового зала.
* Полки нумеруются **снизу вверх с нуля** (`Shelf.index`); в текстах
  отчётов номер полки выводится с единицы («полка 1» — нижняя).
* «Фейсинг» — одна единица товара, видимая с фронта полки;
  фронт выкладки SKU = `facings × Product.width`.

## Модель данных (`core.models`)

### `Supplier`

| Поле | Тип | Описание |
|---|---|---|
| `supplier_id` | `str` | идентификатор поставщика |
| `name` | `str` | название |
| `color` | `str` | hex-цвет для режима «утверждённая планограмма» |

### `Product`

| Поле | Тип | Описание |
|---|---|---|
| `sku` | `str` | код товарной позиции |
| `name` | `str` | наименование |
| `category` | `str` | товарная категория |
| `supplier_id` | `str` | ссылка на `Supplier` |
| `width, height, depth` | `float` | габариты одной упаковки, м |
| `weight` | `float` | вес единицы, кг |
| `is_priority` | `bool` | приоритетный (высокомаржинальный) товар |

### `Gondola` и `Shelf`

`Gondola` — стеллаж в зале: `gondola_id`, `name`, положение `x, y`,
габариты `width, depth` и список полок `shelves`. Метод
`shelf(index)` возвращает полку по номеру.

`Shelf`: `index` (номер снизу, с 0), `z` (высота нижней плоскости от
пола), `clearance` (полезный просвет до следующей полки).

### `Placement` и `Planogram`

`Placement` — выкладка одного SKU на конкретной полке: `sku`,
`gondola_id`, `shelf_index`, `offset` (смещение от левого края полки, м),
`facings` (число фейсингов).

`Planogram` — именованный набор выкладок. Методы: `by_gondola(id)`,
`find(sku, gondola_id, shelf_index)`.

В `Store` хранятся **две** планограммы: `approved_planogram`
(утверждённая) и `current_planogram` (фактическая выкладка); их
расхождения находит `check_against_approved`.

### `SalesInfo`

Текущее состояние продаж по SKU: `stock` (остаток на полке, шт.),
`capacity` (ёмкость выкладки), `sold_today`, `sales_rate` (шт./день).

Вычисляемые свойства: `fill_ratio` (заполненность 0..1) и
`days_of_supply` (на сколько дней хватит остатка; `inf` при нулевой
скорости продаж).

### `Contract`

Обязательства ритейлера перед поставщиком:

| Поле | Тип | Описание |
|---|---|---|
| `supplier_id` | `str` | к кому относится контракт |
| `min_share_pct` | `float` | минимальная доля полки по фронту, % (0 — не проверять) |
| `mandatory_skus` | `Dict[str, int]` | обязательные SKU → минимум фейсингов |
| `eye_level_skus` | `List[str]` | SKU, обязанные стоять на уровне глаз |

### `Regulations`

Параметры внутреннего регламента сети (все имеют значения по умолчанию):

| Поле | По умолчанию | Смысл |
|---|---|---|
| `max_weight_high_shelf` | `5.0` | тяжелее — только на нижние полки |
| `heavy_shelf_max_z` | `0.6` | «нижние полки» — ниже этой высоты, м |
| `eye_level_range` | `(1.2, 1.6)` | диапазон «уровня глаз», м |
| `min_days_of_supply` | `1.0` | минимальный запас в днях продаж |
| `low_stock_threshold` | `0.3` | заполненность, ниже которой алерт |

### `Store`

Корневой агрегат — всё, что нужно ядру для работы: `store_id`, `name`,
`gondolas`, `products` (словарь по SKU), `suppliers` (словарь по id),
`contracts`, `regulations`, `approved_planogram`, `current_planogram`,
`sales` (словарь `sku → SalesInfo`).

Хелперы: `gondola(id)`, `product(sku)`, `supplier_of(sku)`.

## Проверка соответствия (`core.rules`)

Каждая проверка возвращает список `Violation`:

| Поле | Значения |
|---|---|
| `group` | `regulation` \| `contract` \| `planogram` \| `sales` |
| `severity` | `critical` \| `warning` |
| `where` | человекочитаемое место (стеллаж/полка/SKU) |
| `message` | описание нарушения |

Функции:

* `check_regulations(store, planogram)` — внутренний регламент: тяжёлый
  товар на высокой полке, товар не помещается в просвет, выкладка
  выходит за край полки, пересечение выкладок.
* `check_contracts(store, planogram)` — контракты: доля полки по фронту,
  обязательные SKU и минимум фейсингов, размещение на уровне глаз.
* `check_against_approved(store)` — расхождения `current_planogram` с
  `approved_planogram`: отсутствующие позиции, лишние позиции,
  несовпадение фейсингов.
* `check_sales(store)` — алерты по продажам: out-of-stock, низкая
  заполненность, запас меньше `min_days_of_supply`.
* `check_compliance(store, extra_checks=None)` — всё вместе,
  отсортировано по важности. `extra_checks` — ваши собственные проверки
  (`Callable[[Store], List[Violation]]`), см. INTEGRATION.md.

Регламент и контракты проверяются по **фактической** выкладке
(`current_planogram`); если её нет — по утверждённой.

## 3D-визуализация (`core.viz`)

* `build_figure(store) -> plotly.graph_objects.Figure` — готовая сцена с
  двумя режимами, переключаемыми кнопками:
  * **«Текущее состояние продаж»** — фактическая выкладка, цвет по
    заполненности (зелёный → жёлтый → красный), out-of-stock —
    полупрозрачный красный; глубина стопки товара пропорциональна
    остатку;
  * **«Утверждённая планограмма»** — согласованная выкладка, цвет
    поставщика.

  С `Figure` дальше можно делать всё, что умеет plotly: `fig.show()`,
  `fig.to_html()`, `fig.write_image("plan.png")` (нужен `kaleido`),
  встраивание в Dash и т. д.
* `cuboid(x, y, z, dx, dy, dz, color, ...) -> Mesh3d` — низкоуровневый
  строительный блок (параллелепипед) для собственных сцен.
* `fill_color(ratio) -> str` — цвет теплокарты заполненности (0..1).

## Отчёты (`core.report`)

* `render_console_report(violations) -> str` — текст для консоли/лога.
* `render_html_report(violations) -> str` — HTML-блок с таблицей
  нарушений для встраивания в собственную страницу.
* `build_report_page(store, violations=None, include_plotlyjs=True,
  default_height="70vh") -> str` — полная автономная HTML-страница
  (3D-сцена + таблица). `violations=None` — проверка выполнится
  автоматически. `include_plotlyjs="cdn"` даёт лёгкую страницу с
  подгрузкой plotly из CDN.
* `save_report(store, path, violations=None, include_plotlyjs=True) ->
  pathlib.Path` — то же, но с записью в файл.
