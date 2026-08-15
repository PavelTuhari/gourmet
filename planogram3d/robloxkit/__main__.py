"""CLI конвертора: демо-сцены planogram3d → Roblox place-файлы.

::

    python -m planogram3d.robloxkit               # → robloxkit/demo/
    python -m planogram3d.robloxkit -o out/       # свой каталог
    python -m planogram3d.robloxkit --store st03  # конкретный магазин
"""

import argparse
import sys
import xml.dom.minidom
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="planogram3d.robloxkit",
        description="Конвертация сцен planogram3d в формат Roblox "
                    "(.rbxlx, открывается в Roblox Studio).")
    parser.add_argument("-o", "--output",
                        default=str(Path(__file__).parent / "demo"),
                        help="каталог для .rbxlx файлов")
    parser.add_argument("--store", default="st17",
                        help="id магазина сети для сцены зала")
    args = parser.parse_args(argv)

    from ..webapp.network import (NETWORK_LAYOUT, DistributionCenter,
                                  StoreNetwork)
    from .convert import convert_city, convert_store

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    network = StoreNetwork(dc_enabled=False)
    store = network.store(args.store)

    # уровни-смены — те же, что в веб-тренажёре (game.html)
    levels = [
        {"title": "Смена 1 · Основы", "goal": 700, "time": 150},
        {"title": "Смена 2 · Чистота и лента", "goal": 1400, "time": 150},
        {"title": "Смена 3 · Час пик", "goal": 2100, "time": 160},
    ]

    results = []
    for name, xml_text in [
        (f"gourman_store_{args.store}.rbxlx",
         convert_store(store, levels)),
        ("gourman_city.rbxlx",
         convert_city(NETWORK_LAYOUT, DistributionCenter.LOCATION)),
    ]:
        # проверка корректности XML перед записью
        xml.dom.minidom.parseString(xml_text)
        path = out / name
        path.write_text(xml_text, encoding="utf-8")
        parts = xml_text.count('<Item class="Part"') + xml_text.count(
            '<Item class="SpawnLocation"')
        scripts = (xml_text.count('<Item class="Script"')
                   + xml_text.count('<Item class="ModuleScript"')
                   + xml_text.count('<Item class="LocalScript"'))
        prompts = xml_text.count('<Item class="ProximityPrompt"')
        results.append((path, parts, scripts, prompts))
        print(f"✔ {path}  ({path.stat().st_size // 1024} КБ, "
              f"блоков: {parts}, скриптов: {scripts}, "
              f"интерактивных точек: {prompts})")

    print("\nОткройте файлы в Roblox Studio: File → Open from File, "
          "затем Publish для команды магазина.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
