"""Одна команда: самоработающая демонстрация автозаказа топлива.

Владелец хочет одну команду, после которой всё происходит само:
автозаказ срабатывает сразу на нескольких АЗС → штатный механизм
(``peco_fuel.FuelNetwork._maybe_dispatch``) собирает их в один рейс
бензовоза → компактное окно поверх остальных показывает выезд и
движение машины по карте → на каждой остановке, где начинается слив,
показ сам уходит на 3D-планограмму этой заправки, а досмотрев
разгрузку — возвращается на карту и едет к следующей. Никаких кликов
зрителя: хореография живёт в ``webapp/templates/fuel.html``
(``runDemoScenario``, параметр ``?demo=1``) и в
``fuelviz.build_station_page`` (параметры ``compact``/``demo``), а уже
показанные станции передаются в адресе (``?seen=``), чтобы обход шёл
вперёд, а не возвращался к первой.

Единственная уступка воспроизводимости (владелец явно разрешил её в
постановке): остатки выбранных станций принудительно опускаются ниже
порога заказа перед стартом (``FuelNetwork.force_low``), чтобы не
дожидаться естественного расхода. Дальше — ни одного нарисованного
кадра: рейс, движение и слив — настоящий эмулятор ``peco_fuel.py``,
evolve-on-poll, без единого нового фонового потока (переиспользуем тот
же встроенный backend, что и ``desktop.py``).

Запуск::

    python -m planogram3d.webapp.tools.demo_autoorder
    python -m planogram3d.webapp.tools.demo_autoorder --stations 12 21 --lang ro

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
#: несколько станций подряд — рейс получается многостанционным, и
#: сценарий может показать обход: карта → планограмма → снова карта
DEFAULT_STATIONS = [6, 3, 12, 21]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="planogram3d.webapp.tools.demo_autoorder",
        description="Самоработающая демонстрация: автозаказ топлива → "
                    "рейс бензовоза → разгрузка на 3D-планограмме станции.")
    parser.add_argument(
        "--stations", type=int, nargs="+", default=DEFAULT_STATIONS,
        help=f"id АЗС, на которых форсировать автозаказ; диспетчер "
             f"соберёт их в общий рейс (по умолчанию {DEFAULT_STATIONS})")
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

    # Опускаем остаток сразу нескольким станциям: диспетчер собирает их
    # в один рейс (до 4 остановок), и зритель видит то, ради чего всё
    # затевалось — машина объезжает несколько заправок, на каждой из
    # которых сработал автозаказ, а не одну-единственную.
    forced = [sid for sid in args.stations
              if webapp_server.fuel.force_low(sid)]
    if not forced:
        print(f"❌ Ни одна из АЗС {args.stations} не найдена в сети",
              file=sys.stderr)
        return 1
    print(f"🛢 Остаток АЗС {', '.join(map(str, forced))} опущен ниже порога "
          f"заказа — автозаказ сработает штатно на первом же опросе; "
          f"диспетчер соберёт их в общий рейс")

    url = (f"http://127.0.0.1:{port}/fuel"
          f"?compact=1&demo=1&lang={args.lang}")

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
