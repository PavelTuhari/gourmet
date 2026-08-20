"""Одна команда: самоработающая демонстрация автозаказа топлива.

Владелец хочет одну команду, после которой всё происходит само:
автозаказ срабатывает на выбранной АЗС → штатный механизм
(``peco_fuel.FuelNetwork._maybe_dispatch``) формирует рейс бензовоза →
компактное окно поверх остальных само показывает выезд и движение
машины по карте → как только на станции начинается реальный слив,
страница сама переключается на 3D-планограмму этой заправки, где видно
разгрузку. Никаких кликов зрителя — вся хореография внутри
``webapp/templates/fuel.html`` (параметр ``?focus=``, см. ``runDemoScenario``
в шаблоне) и ``fuelviz.build_station_page`` (параметр ``compact``).

Единственная уступка воспроизводимости (владелец явно разрешил её в
постановке): остаток выбранной станции принудительно опускается ниже
порога заказа перед стартом (``FuelNetwork.force_low``), чтобы не
дожидаться естественного расхода. Дальше — ни одного нарисованного
кадра: рейс, движение и слив — настоящий эмулятор ``peco_fuel.py``,
evolve-on-poll, без единого нового фонового потока (переиспользуем тот
же встроенный backend, что и ``desktop.py``).

Запуск::

    python -m planogram3d.webapp.tools.demo_autoorder
    python -m planogram3d.webapp.tools.demo_autoorder --station 12 --lang ro

Служебное: ``PLANOGRAM3D_NO_GUI=1`` — только сервер и форсирование
автозаказа, без окна (для проверки без дисплея).
"""

import argparse
import os
import sys

# desktop.py уже умеет поднимать встроенный backend на свободном порту
# и ждать его готовности — тот же приём, тот же код, никакой отдельной
# копии сервера для демонстрации.
from ...desktop import _free_port, _start_backend, _wait_ready

#: близкая к нефтебазе Сынжера станция — рейс успевает и выехать, и
#: доехать, и слиться в пределах короткого демонстрационного ролика
#: (скорость бензовоза в эмуляции намеренно велика, см. TANKER_SPEED в
#: peco_fuel.py — так весь мир туда «сжат», не только расход станций)
DEFAULT_STATION = 6


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="planogram3d.webapp.tools.demo_autoorder",
        description="Самоработающая демонстрация: автозаказ топлива → "
                    "рейс бензовоза → разгрузка на 3D-планограмме станции.")
    parser.add_argument(
        "--station", type=int, default=DEFAULT_STATION,
        help=f"id АЗС, на которой форсировать автозаказ (по умолчанию "
             f"{DEFAULT_STATION})")
    parser.add_argument("--lang", default="ru", choices=["ru", "ro", "en"],
                        help="язык демонстрации (по умолчанию ru)")
    parser.add_argument("--width", type=int, default=720,
                        help="ширина окна (по умолчанию 720)")
    parser.add_argument("--height", type=int, default=520,
                        help="высота окна (по умолчанию 520)")
    parser.add_argument(
        "--no-on-top", action="store_true",
        help="не держать окно поверх остальных (по умолчанию держит — "
             "смысл демонстрации «краем глаза»)")
    parser.add_argument("--debug", action="store_true",
                        help="инструменты разработчика в окне")
    args = parser.parse_args(argv)

    port = _free_port()
    _start_backend(port)
    if not _wait_ready(port):
        print("❌ Встроенный сервер не поднялся", file=sys.stderr)
        return 1

    # тот же процесс, тот же модуль server (desktop._start_backend уже
    # импортировал .webapp.server — Python кеширует модуль, поэтому
    # здесь это тот же самый объект fuel, что видит и сервер)
    from .. import server as webapp_server

    if not webapp_server.fuel.force_low(args.station):
        print(f"❌ АЗС {args.station} не найдена в топливной сети",
              file=sys.stderr)
        return 1
    print(f"🛢 Остаток АЗС {args.station} опущен ниже порога заказа — "
          f"автозаказ сработает штатно на первом же опросе состояния")

    url = (f"http://127.0.0.1:{port}/fuel"
          f"?compact=1&focus={args.station}&lang={args.lang}")

    if os.environ.get("PLANOGRAM3D_NO_GUI") == "1":
        print(f"OK: сервер готов на порту {port}, сценарий: {url}")
        return 0

    try:
        import webview
    except ImportError:
        print("❌ Не установлен pywebview: pip install pywebview",
              file=sys.stderr)
        return 1

    min_size = (min(1100, args.width), min(700, args.height))
    webview.create_window(
        "planogram3d — автозаказ топлива (демо)",
        url, width=args.width, height=args.height, min_size=min_size,
        on_top=not args.no_on_top)
    webview.start(debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
