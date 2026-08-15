"""Конвертор сцен planogram3d → Roblox place (.rbxlx).

Две сцены:

* :func:`convert_store` — торговый зал магазина: реальная планограмма
  (стеллажи, полки, выкладка по цветам поставщиков), кассы, зона СКО,
  весы, холодильники, зоны скоропорта, склад — плюс Luau-скрипты
  тренажёра (задания через ProximityPrompt, баллы, поощрения через
  MessagingService);
* :func:`convert_city` — обзорная сцена сети: магазины по реальным
  координатам города и логистический центр.

Масштаб: 1 метр = 4 стада; ось «вверх» planogram3d → Y Roblox.
"""

import math
from typing import List

from ..core import Store
from . import luau
from .rbxlx import Inst, billboard, build_place, part, prompt, script

S = 4.0            # стадов в метре
WALL_H = 3.2 * S   # высота стен зала


def m(v: float) -> float:
    return round(v * S, 3)


def _toast_gui() -> Inst:
    gui = Inst("ScreenGui", "TrainingGui")
    frame = Inst("Frame", "Toast")
    frame.p_udim2("Size", 0, 460, 0, 44)
    frame.p_udim2("Position", 0.5, -230, 0, 24)
    frame.p_float("BackgroundTransparency", 0.25)
    frame.p_color3("BackgroundColor3", 0.1, 0.16, 0.23)
    frame.p_bool("Visible", False)
    lbl = Inst("TextLabel", "Text")
    lbl.p_udim2("Size", 1, 0, 1, 0)
    lbl.p_float("BackgroundTransparency", 1)
    lbl.p_string("Text", "")
    lbl.p_bool("TextScaled", True)
    lbl.p_color3("TextColor3", 1, 0.92, 0.6)
    frame.add(lbl)
    gui.add(frame, script("AnnounceClient", luau.ANNOUNCE_CLIENT,
                          "LocalScript"))
    return gui


def convert_store(store: Store, levels) -> str:
    """Сцена торгового зала магазина с тренажёром."""
    ws: List[Inst] = []

    # пол и стены (зал 8×6 м, как в веб-симуляции)
    ws.append(part("Floor", (m(3.7), -0.5, m(2.75)),
                   (m(9.4), 1, m(7.3)), "#d9d2c4", "Marble"))
    ws.append(part("WallBack", (m(3.7), WALL_H / 2, m(-0.7)),
                   (m(9.4), WALL_H, 1), "#cfd6de", "Concrete"))
    ws.append(part("WallLeft", (m(-0.9), WALL_H / 2, m(2.75)),
                   (1, WALL_H, m(7.3)), "#c6cdd6", "Concrete"))

    # зоны скоропорта — светло-голубые накладки на пол
    perishable = Inst("Model", "PerishableZones")
    for i, (zx, zz, zw, zd) in enumerate(
            [(-0.25, 3.75, 2.9, 1.45), (0.0, 4.5, 3.05, 1.4)]):
        zone = part(f"Perishable{i + 1}",
                    (m(zx + zw / 2), 0.08, m(zz + zd / 2)),
                    (m(zw), 0.15, m(zd)), "#9fd4ef", "Ice",
                    transparency=0.55, can_collide=False)
        zone.add(billboard("❄ скоропорт", 1.2, 160, 36, (0.5, 0.8, 1)))
        perishable.add(zone)
    ws.append(perishable)

    # стеллажи с реальной планограммой
    gondolas = Inst("Model", "Gondolas")
    for g in store.gondolas:
        model = Inst("Model", g.name)
        top = max(s.z + s.clearance for s in g.shelves) + 0.05
        cx, cz = g.x + g.width / 2, g.y + g.depth / 2
        # боковины и задняя стенка
        for px in (g.x - 0.03, g.x + g.width + 0.03):
            model.add(part("Side", (m(px), m(top / 2), m(cz)),
                           (m(0.06), m(top), m(g.depth)), "#8f96a0",
                           "Metal"))
        model.add(part("Back", (m(cx), m(top / 2), m(g.y + g.depth)),
                       (m(g.width), m(top), m(0.06)), "#9aa1ab", "Metal"))
        # полки и выкладка (цвет — поставщик из утверждённой планограммы)
        for s in g.shelves:
            model.add(part("Shelf", (m(cx), m(s.z - 0.015), m(cz)),
                           (m(g.width), m(0.03), m(g.depth)), "#d4d9e0",
                           "SmoothPlastic"))
        for p in store.approved_planogram.by_gondola(g.gondola_id):
            product = store.product(p.sku)
            supplier = store.supplier_of(p.sku)
            shelf = g.shelf(p.shelf_index)
            width = p.facings * product.width
            block = part(
                product.name,
                (m(g.x + p.offset + width / 2),
                 m(shelf.z + product.height / 2),
                 m(g.y + 0.02 + product.depth * 1.5)),
                (m(width - 0.01), m(product.height), m(product.depth * 3)),
                supplier.color, "SmoothPlastic")
            block.add(prompt("Пополнить", product.name))
            model.add(block)
        first = model.children[0]
        first.add(billboard(g.name, top * S + 2.5))
        gondolas.add(model)
    ws.append(gondolas)

    # холодильники
    fridges = Inst("Model", "Fridges")
    for fid, fx, fz, fw, fd in [("ХВ-1", 0.25, 5.05, 1.15, 0.55),
                                ("ХВ-2", 1.65, 5.05, 1.15, 0.55)]:
        f = part(fid, (m(fx + fw / 2), m(0.4), m(fz + fd / 2)),
                 (m(fw), m(0.8), m(fd)), "#cfe5f2", "Glass",
                 transparency=0.25)
        f.add(billboard(f"🧊 {fid} · 4.0°C", 2.4, 170, 36, (0.55, 0.8, 1)),
              prompt("Проверить", fid))
        fridges.add(f)
    ws.append(fridges)

    # кассы и зона СКО
    checkout = Inst("Model", "Checkout")
    for name, px, pz in [("Касса 1", 6.15, 1.0), ("Касса 2", 7.0, 1.0)]:
        desk = part(name, (m(px), m(0.25), m(pz)),
                    (m(0.8), m(0.5), m(0.6)), "#a9b6c6", "SmoothPlastic")
        desk.add(billboard("🧾 " + name, 2.2),
                 prompt("Обслужить покупателя", name, hold=1.0))
        checkout.add(desk)
    sco = part("Зона СКО", (m(4.85), 0.1, m(1.0)),
               (m(1.3), 0.2, m(1.6)), "#7fa7f0", "Neon",
               transparency=0.4, can_collide=False)
    sco.add(billboard("СКО — кассы самообслуживания", 1.6, 240, 36,
                      (0.55, 0.7, 1)),
            prompt("Обслужить покупателя", "СКО", hold=1.0))
    checkout.add(sco)
    ws.append(checkout)

    # весы и склад
    scales = part("Весы", (m(4.6), m(0.28), m(4.6)),
                  (m(0.5), m(0.55), m(0.4)), "#b9c4cf", "Metal")
    scales.add(billboard("⚖ Весы", 1.9), prompt("Взвесить", "Весы"))
    ws.append(scales)
    storeroom = Inst("Model", "Storeroom")
    door = part("Дверь склада", (m(6.6), m(1.1), m(-0.62)),
                (m(1.1), m(2.2), m(0.12)), "#8d6e63", "WoodPlanks")
    door.add(billboard("📦 СКЛАД", 5.2), prompt("Взять товар", "Склад"))
    storeroom.add(door)
    ws.append(storeroom)

    # вход/выход и точка появления
    enter = part("Вход", (m(7.0), 0.07, m(5.3)), (m(1.0), 0.15, m(0.5)),
                 "#9fdca8", "Neon", transparency=0.3,
                 can_collide=False)
    enter.add(billboard("ВХОД", 1.2, 120, 32, (0.4, 0.85, 0.5)))
    ws.append(enter)
    ws.append(part("Выход", (m(7.35), 0.07, m(0.25)),
                   (m(1.0), 0.15, m(0.45)), "#f0b3ad", "Neon",
                   transparency=0.3, can_collide=False))
    ws.append(part("Spawn", (m(5.6), 0.3, m(3.2)), (m(1.5), 0.5, m(1.5)),
                   "#e8e2d5", "SmoothPlastic",
                   class_name="SpawnLocation"))

    announce = Inst("RemoteEvent", "Announce")
    return build_place(
        ws,
        server_scripts=[
            script("TrainingServer", luau.TRAINING_SERVER),
            script("RewardConfig", luau.reward_config(levels),
                   "ModuleScript"),
            script("PlanogramData", luau.planogram_data(store),
                   "ModuleScript"),
        ],
        replicated=[announce],
        starter_gui=[_toast_gui()])


def convert_city(network_layout, dc_location) -> str:
    """Обзорная сцена сети: магазины по реальным координатам + РЦ.

    Масштаб города: 1 метр = 0.25 стада (центр Твери ~4 км → ~1000
    стадов — обходимая пешком сцена).
    """
    lat0 = sum(lat for _, _, lat, _, _ in network_layout) / len(
        network_layout)
    lon0 = sum(lon for _, _, _, lon, _ in network_layout) / len(
        network_layout)

    def xy(lat, lon):
        x = (lon - lon0) * 111320 * math.cos(math.radians(lat0)) * 0.25
        z = (lat0 - lat) * 110540 * 0.25
        return round(x, 1), round(z, 1)

    ws: List[Inst] = [part("Ground", (0, -1, 0), (5200, 2, 5200),
                           "#cfe3b8", "Plastic")]

    stores_model = Inst("Model", "Stores")
    for store_id, title, lat, lon, _seed in network_layout:
        x, z = xy(lat, lon)
        b = part(title, (x, 18, z), (36, 36, 36), "#e8b64c", "Brick")
        b.add(billboard("🏪 " + title, 24, 320, 48, (1, 0.85, 0.4)),
              prompt("Открыть тренажёр", title))
        stores_model.add(b)
    ws.append(stores_model)

    dx, dz = xy(*dc_location)
    dc = part("РЦ «Гурман»", (dx, 24, dz), (90, 48, 60), "#8fa3b8",
              "Metal")
    dc.add(billboard("🏭 Логистический центр", 32, 340, 52,
                     (0.75, 0.85, 1)))
    ws.append(dc)
    ws.append(part("Spawn", (0, 1, 0), (8, 1, 8), "#ffffff",
                   class_name="SpawnLocation"))
    return build_place(ws)
