"""planogram3d как нативное десктоп-приложение.

Открывает системное окно (на macOS — WKWebView через pywebview, как у
нативных программ; Dock, Cmd+Tab, полноэкранный режим — всё родное),
внутри которого работает вся система: карта сети, планограммы,
симуляция зала, тренажёр, доставка, документация.

Запуск::

    python -m planogram3d.desktop            # нативное окно
    python -m planogram3d.desktop --debug    # + инструменты разработчика
    python -m planogram3d.desktop --url /fuel --width 720 --height 520 --on-top
                                              # компактное окно поверх
                                              # остальных — для демонстрации
                                              # «краем глаза», пока
                                              # пользователь работает в
                                              # другом окне

Служебное: переменная окружения ``PLANOGRAM3D_NO_GUI=1`` запускает
только встроенный сервер и проверяет его готовность (для автотестов в
средах без дисплея).
"""

import argparse
import os
import socket
import sys
import threading
import time
import urllib.request


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_backend(port: int) -> None:
    """Встроенный сервер системы в фоновом потоке."""
    from .webapp import server

    server.network.start()
    threading.Thread(
        target=lambda: server.app.run(
            host="127.0.0.1", port=port, threaded=True,
            use_reloader=False),
        daemon=True).start()


def _wait_ready(port: int, timeout: float = 30.0) -> bool:
    url = f"http://127.0.0.1:{port}/api/state"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="planogram3d.desktop",
        description="planogram3d в нативном окне (pywebview).")
    parser.add_argument("--debug", action="store_true",
                        help="инструменты разработчика в окне")
    parser.add_argument(
        "--url", default="/",
        help="страница системы при старте: путь (например, /fuel) "
             "или полный адрес (по умолчанию /)")
    parser.add_argument("--width", type=int, default=1480,
                        help="ширина окна (по умолчанию 1480)")
    parser.add_argument("--height", type=int, default=920,
                        help="высота окна (по умолчанию 920)")
    parser.add_argument(
        "--on-top", action="store_true",
        help="держать окно поверх всех остальных окон (демонстрация "
             "«краем глаза», пока работаешь в другом приложении)")
    args = parser.parse_args(argv)

    port = _free_port()
    _start_backend(port)
    if not _wait_ready(port):
        print("❌ Встроенный сервер не поднялся", file=sys.stderr)
        return 1

    if os.environ.get("PLANOGRAM3D_NO_GUI") == "1":
        print(f"OK: сервер готов на порту {port} (режим без GUI)")
        return 0

    try:
        import webview
    except ImportError:
        print("❌ Не установлен pywebview: pip install pywebview",
              file=sys.stderr)
        return 1

    # --url принимает и путь («/fuel»), и полный адрес — второе нужно,
    # если когда-нибудь захочется указать внешний хост вместо
    # встроенного сервера на локальном порту.
    target_url = (args.url if "://" in args.url
                  else f"http://127.0.0.1:{port}{args.url}")

    # min_size не может быть больше запрошенного размера окна — иначе
    # окно физически не сожмётся до компактного вида (было жёстко
    # 1100×700 при дефолте 1480×920, что ломало --width/--height
    # меньше этого порога).
    min_size = (min(1100, args.width), min(700, args.height))

    webview.create_window(
        "planogram3d — цифровой двойник сети «Гурман»",
        target_url,
        width=args.width, height=args.height, min_size=min_size,
        on_top=args.on_top)
    webview.start(debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
