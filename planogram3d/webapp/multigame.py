"""Командный тренажёр: до 10 игроков разных ролей в одной смене.

Сервер ведёт общую авторитетную симуляцию смены магазина; подключаться
могут:

* **люди** — через браузер (``/store/<id>/game/multi``);
* **ИИ-боты** — встроенная политика по роли, добавляются кнопкой или
  ``POST .../bot``;
* **внешние ИИ / программы студентов** — через REST API: ``join`` →
  цикл ``state``/``action``. Так студенты учатся и работе в команде
  магазина на всех ролях, и написанию агентов.

Роли (лимиты в сумме дают 10 игроков): 2 кассира, 3 мерчандайзера,
2 клинера, 2 техника, 1 супервайзер. Любая роль может выполнять любую
работу, но «не свою» — медленнее: студент чувствует, почему важно
распределение обязанностей.
"""

import math
import random
import threading
import time
import uuid
from typing import Dict, List, Optional

from .instore import (ENTRANCE, EXIT, HALL, POS_DESKS, SCO_PAY, SCO_RECT,
                      FRIDGES)
from .network import price_for

#: заголовки ролей теперь переведены в i18n.py (ключи "mgame.role.*") —
#: здесь остаётся русский текст как ключ для team.award() (лента команды
#: в roblox.py хранит уже готовую строку без языка запроса, см. HANDOFF)
#: и как запасное значение для внешних API-потребителей, не читающих
#: каталог сообщений.

STOREROOM = (6.6, -0.15)
REGISTER = POS_DESKS[0]           # штатная касса, требует кассира
SHIFT_SECONDS = 180.0
MAX_PLAYERS = 10
WALK = 1.7

#: роли: заголовок, иконка, лимит и множители длительности действий
#: (меньше — быстрее; «не своя» работа заметно медленнее)
ROLES = {
    "cashier": {"title": "Кассир", "icon": "🧑‍💼", "limit": 2,
                "serve": 0.8, "restock": 1.8, "clean": 1.8, "tech": 1.8},
    "merch": {"title": "Мерчандайзер", "icon": "📦", "limit": 3,
              "serve": 2.0, "restock": 0.7, "clean": 1.5, "tech": 1.5},
    "cleaner": {"title": "Клинер", "icon": "🧹", "limit": 2,
                "serve": 2.0, "restock": 1.5, "clean": 0.6, "tech": 1.5},
    "tech": {"title": "Техник", "icon": "🛠", "limit": 2,
             "serve": 2.0, "restock": 1.5, "clean": 1.5, "tech": 0.6},
    "supervisor": {"title": "Супервайзер", "icon": "🧑‍💻", "limit": 1,
                   "serve": 1.1, "restock": 1.1, "clean": 1.1,
                   "tech": 1.1},
}

POINTS = {"serve": 25, "restock": 15, "clean": 12, "fridge": 20,
          "paper": 10}


class MultiGame:
    """Одна командная смена (сессия) магазина."""

    def __init__(self, store, session_key: str):
        self.store = store
        self.key = session_key
        self.rng = random.Random(hash(session_key) & 0xFFFFFF)
        self.lock = threading.Lock()
        self.phase = "lobby"          # lobby | play | ended
        self.players: Dict[str, dict] = {}
        self.reset_world()
        self._event_id = 1
        self.events: List[dict] = []
        self._last = time.time()

    # ----- мир смены ----------------------------------------------------
    def reset_world(self):
        self.time_left = SHIFT_SECONDS
        self.money = 0
        self.goal = 1500
        self.rep = 80.0
        self.shelves = [{"i": i, "x": g.x, "y": g.y, "w": g.width,
                         "d": g.depth,
                         "name": g.name.split("(")[0].strip(),
                         "stock": 10, "max": 10,
                         "products": [
                             {"name": self.store.product(p.sku).name,
                              "price": round(price_for(
                                  self.store.product(p.sku).category,
                                  p.sku))}
                             for p in
                             self.store.current_planogram.by_gondola(
                                 g.gondola_id)]}
                        for i, g in enumerate(self.store.gondolas)]
        self.customers: Dict[int, dict] = {}
        self._cust_id = 1
        self.next_spawn = 2.0
        self.queue: List[int] = []            # к штатной кассе
        self.sco_queue: List[int] = []
        self.serving_progress = 0.0
        self.sco_progress = 0.0
        self.paper = 100.0
        self.messes: Dict[int, dict] = {}
        self._mess_id = 1
        self.next_mess = 14.0
        self.fridge_alarm: Optional[str] = None
        self.next_fridge = 30.0

    def _emit(self, key: str, kind: str = "log", count=None,
              x=None, y=None, color=None, **params):
        """Запись ленты: ключ каталога + параметры, а не готовый текст.

        Роут ``/api/mgame/.../state`` не входит в эту задачу (см. i18n.py,
        комментарий у ключей ``mgame.*``), поэтому язык здесь неизвестен —
        клиент сам собирает текст через ``tt()``/``ttn()`` по каталогу,
        загруженному при открытии страницы (тот же итог, что у
        ``render_event`` в i18n.py, только рендер не в Python, а в JS).
        """
        ev = {"id": self._event_id, "kind": kind, "key": key,
              "params": params, "count": count}
        if x is not None:
            ev["x"] = x
        if y is not None:
            ev["y"] = y
        if color is not None:
            ev["color"] = color
        self.events.append(ev)
        self._event_id += 1
        del self.events[:-160]

    def _fx(self, x, y, key, color="#ffd54f", **params):
        self._emit(key, kind="fx", x=x, y=y, color=color, **params)

    # ----- игроки -------------------------------------------------------
    def join(self, name: str, role: str, kind: str,
             roblox_user: str = "") -> dict:
        with self.lock:
            if role not in ROLES:
                return {"error": "unknown_role"}
            if len(self.players) >= MAX_PLAYERS:
                return {"error": "session_full"}
            taken = sum(1 for p in self.players.values()
                        if p["role"] == role)
            if taken >= ROLES[role]["limit"]:
                return {"error": "role_full"}
            pid = uuid.uuid4().hex[:10]
            self.players[pid] = {
                "id": pid, "name": (name or "Игрок").strip()[:24],
                "role": role, "kind": kind, "roblox_user": roblox_user,
                "x": 5.6 + self.rng.uniform(-0.6, 0.6),
                "y": 3.2 + self.rng.uniform(-0.6, 0.6),
                "task": None, "busy": 0.0, "busy_max": 0.0,
                "busy_label": "", "carry": 0, "last_seen": time.time(),
                "stats": {"points": 0, "serve": 0, "restock": 0,
                          "clean": 0, "fridge": 0, "paper": 0},
            }
            self._emit("mgame.event.joined", name=self.players[pid]["name"],
                       icon=ROLES[role]["icon"], role=role,
                       ai=(kind != "human"))
            return {"player_id": pid, "role": role}

    def leave(self, pid: str):
        with self.lock:
            p = self.players.pop(pid, None)
            if p:
                self._emit("mgame.event.left", name=p["name"])

    def start(self):
        with self.lock:
            if self.phase == "play":
                return
            self.reset_world()
            for p in self.players.values():
                p["stats"] = {"points": 0, "serve": 0, "restock": 0,
                              "clean": 0, "fridge": 0, "paper": 0}
                p["task"] = None
                p["busy"] = 0
                p["carry"] = 0
            self.phase = "play"
            self._emit("mgame.event.started", count=len(self.players),
                       goal=self.goal)

    # ----- действия (люди и внешние ИИ по API) --------------------------
    def action(self, pid: str, act: str, x: Optional[float] = None,
               y: Optional[float] = None,
               target: Optional[str] = None) -> dict:
        with self.lock:
            p = self.players.get(pid)
            if p is None:
                return {"error": "no_such_player"}
            p["last_seen"] = time.time()
            if self.phase != "play":
                return {"error": "not_running"}
            t = None
            if act == "move" and x is not None:
                t = {"type": "walk",
                     "x": max(HALL[0] + .3, min(HALL[2] - .3, float(x))),
                     "y": max(HALL[1] + .3, min(HALL[3] - .3, float(y)))}
            elif act == "storeroom":
                t = {"type": "storeroom", "x": STOREROOM[0],
                     "y": STOREROOM[1] + 0.45}
            elif act == "restock":
                idx = int(target or 0)
                if 0 <= idx < len(self.shelves):
                    sh = self.shelves[idx]
                    t = {"type": "shelf", "shelf": idx,
                         "x": sh["x"] + sh["w"] / 2,
                         "y": sh["y"] + sh["d"] + 0.4}
            elif act == "serve":
                t = {"type": "register", "x": REGISTER[1] - 0.05,
                     "y": REGISTER[2] + 0.02}
            elif act == "clean":
                m = self.messes.get(int(target or -1))
                if m:
                    t = {"type": "mess", "mess": int(target),
                         "x": m["x"], "y": m["y"]}
            elif act == "fix_fridge":
                if self.fridge_alarm:
                    f = next(f for f in FRIDGES
                             if f[0] == self.fridge_alarm)
                    t = {"type": "fridge", "x": f[1] + f[3] / 2,
                         "y": f[2] + f[4] + 0.35}
            elif act == "paper":
                t = {"type": "paper", "x": REGISTER[1] - 0.05,
                     "y": REGISTER[2] + 0.02}
            if t is None:
                return {"error": "bad_action"}
            p["task"] = t
            return {"ok": True, "task": t["type"]}

    # ----- внутренняя механика ------------------------------------------
    def _perform(self, p: dict, t: dict):
        role = ROLES[p["role"]]

        def busy(base, mult_key, label, done):
            p["busy_max"] = base * role[mult_key]
            p["busy"] = 0.0001
            p["busy_label"] = label
            p["_done"] = done

        if t["type"] == "storeroom":
            busy(1.0, "restock", "берём товар 📦",
                 lambda: p.update(carry=3))
        elif t["type"] == "shelf":
            sh = self.shelves[t["shelf"]]
            if p["carry"] <= 0:
                self._fx(p["x"], p["y"], "mgame.fx.need_stock",
                         "#ff8a80")
                return
            def done():
                p["carry"] -= 1
                sh["stock"] = min(sh["max"], sh["stock"] + 5)
                p["stats"]["restock"] += 1
                p["stats"]["points"] += POINTS["restock"]
                self._fx(t["x"], t["y"], "game.popup.item_added", "#8bc34a")
            busy(0.9, "restock", "выкладка…", done)
        elif t["type"] == "mess":
            m = self.messes.get(t["mess"])
            if not m:
                return
            def done():
                if self.messes.pop(t["mess"], None):
                    p["stats"]["clean"] += 1
                    p["stats"]["points"] += POINTS["clean"]
                    self.rep = min(100, self.rep + 2)
                    self._fx(t["x"], t["y"], "game.popup.clean", "#8bc34a")
            busy(1.4, "clean", "уборка 🧹", done)
        elif t["type"] == "fridge":
            def done():
                if self.fridge_alarm:
                    self.fridge_alarm = None
                    p["stats"]["fridge"] += 1
                    p["stats"]["points"] += POINTS["fridge"]
                    self.rep = min(100, self.rep + 2)
                    self._fx(t["x"], t["y"], "game.popup.fridge_fixed",
                             "#90caf9")
            busy(1.8, "tech", "ремонт ХВ 🧊", done)
        elif t["type"] == "paper":
            if self.paper > 15:
                return
            def done():
                self.paper = 100.0
                p["stats"]["paper"] += 1
                p["stats"]["points"] += POINTS["paper"]
                self._fx(t["x"], t["y"], "game.popup.paper_replaced",
                         "#90caf9")
            busy(1.6, "tech", "замена ленты 🧻", done)
        # register: обслуживание идёт, пока игрок стоит у кассы (в tick)

    def _spawn_customer(self):
        cid = self._cust_id
        self._cust_id += 1
        wants = self.rng.sample(range(len(self.shelves)),
                                self.rng.randint(1, 2))
        self.customers[cid] = {
            "id": cid, "x": ENTRANCE[0], "y": ENTRANCE[1],
            "state": "shelf", "wants": wants, "idx": 0, "bill": 0,
            "items": 0, "patience": 100.0, "sco": self.rng.random() < .45,
            "icon": self.rng.choice(["🧍", "🧍‍♀️", "🧓", "👩", "👨"]),
        }

    def _cust_target(self, c):
        if c["state"] == "shelf":
            sh = self.shelves[c["wants"][c["idx"]]]
            return (sh["x"] + 0.4 + (c["id"] % 5) * 0.35,
                    sh["y"] + sh["d"] + 0.45)
        if c["state"] == "queue":
            if c["sco"]:
                i = self.sco_queue.index(c["id"])
                return (SCO_PAY[0], SCO_PAY[1] + 0.5 + i * 0.5)
            i = self.queue.index(c["id"])
            return (REGISTER[1], REGISTER[2] + 0.75 + i * 0.55)
        return EXIT

    def _tick(self, dt: float, now: float):
        # уход отвалившихся людей/API-агентов (боты остаются)
        for pid in [pid for pid, p in self.players.items()
                    if p["kind"] != "bot"
                    and now - p["last_seen"] > 40]:
            self._emit("mgame.event.disconnected",
                       name=self.players[pid]["name"])
            del self.players[pid]

        if self.phase != "play":
            return
        self.time_left -= dt
        if self.time_left <= 0:
            self._finish()
            return

        # покупатели
        self.next_spawn -= dt
        if self.next_spawn <= 0 and len(self.customers) < 14:
            self.next_spawn = self.rng.uniform(3.2, 6.0)
            self._spawn_customer()
        for c in list(self.customers.values()):
            tx, ty = self._cust_target(c)
            d = math.hypot(tx - c["x"], ty - c["y"])
            if d > 0.06:
                k = min(d, 0.9 * dt)
                c["x"] += (tx - c["x"]) / d * k
                c["y"] += (ty - c["y"]) / d * k
            elif c["state"] == "shelf":
                sh = self.shelves[c["wants"][c["idx"]]]
                if sh["stock"] > 0:
                    sh["stock"] -= 1
                    c["items"] += 1
                    prod = self.rng.choice(sh["products"]) if \
                        sh["products"] else {"price": 100}
                    c["bill"] += prod["price"]
                    c["idx"] += 1
                    if c["idx"] >= len(c["wants"]):
                        c["state"] = "queue"
                        (self.sco_queue if c["sco"]
                         else self.queue).append(c["id"])
                else:
                    c["patience"] -= 4.5 * dt
            elif c["state"] == "queue":
                q = self.sco_queue if c["sco"] else self.queue
                if q.index(c["id"]) > 0:
                    c["patience"] -= 2.6 * dt
            elif c["state"] == "exit" and d <= 0.06:
                del self.customers[c["id"]]
                continue
            if c["patience"] <= 0 and c["state"] != "exit":
                for q in (self.queue, self.sco_queue):
                    if c["id"] in q:
                        q.remove(c["id"])
                c["state"] = "exit"
                c["icon"] = "😡"
                self.rep = max(0, self.rep - 6)
                self._fx(c["x"], c["y"], "💢", "#ff8a80")

        # игроки: движение и занятость
        for p in self.players.values():
            if p["busy"] > 0:
                p["busy"] += dt
                if p["busy"] >= p["busy_max"]:
                    done = p.pop("_done", None)
                    p["busy"] = 0
                    p["busy_label"] = ""
                    if done:
                        done()
                continue
            t = p.get("task")
            if not t:
                continue
            d = math.hypot(t["x"] - p["x"], t["y"] - p["y"])
            if d > 0.12:
                speed = WALK
                for m in self.messes.values():
                    if math.hypot(p["x"] - m["x"], p["y"] - m["y"]) < .5:
                        speed = 0.9
                k = min(d, speed * dt)
                p["x"] += (t["x"] - p["x"]) / d * k
                p["y"] += (t["y"] - p["y"]) / d * k
            else:
                p["task"] = None
                self._perform(p, t)

        # штатная касса: нужен игрок у кассы
        cashier = None
        for p in self.players.values():
            if (p["busy"] <= 0 and not p.get("task")
                    and math.hypot(p["x"] - (REGISTER[1] - 0.05),
                                   p["y"] - (REGISTER[2] + 0.02)) < 0.5):
                cashier = p
                break
        if self.queue and cashier and self.paper > 0:
            head = self.customers.get(self.queue[0])
            if head and math.hypot(
                    head["x"] - REGISTER[1],
                    head["y"] - (REGISTER[2] + 0.75)) < 0.35:
                self.serving_progress += dt / ROLES[
                    cashier["role"]]["serve"]
                if self.serving_progress >= 1.7:
                    self.serving_progress = 0
                    self.queue.pop(0)
                    head["state"] = "exit"
                    self.money += head["bill"]
                    self.paper -= self.rng.uniform(4, 8)
                    cashier["stats"]["serve"] += 1
                    cashier["stats"]["points"] += POINTS["serve"]
                    self.rep = min(100, self.rep + 1.2)
                    self._fx(REGISTER[1], REGISTER[2],
                             f"+{head['bill']} L")
        else:
            self.serving_progress = 0
        if self.paper <= 0 and self.queue:
            pass                       # касса стоит: нужен техник

        # СКО обслуживает себя (медленно)
        if self.sco_queue:
            head = self.customers.get(self.sco_queue[0])
            if head:
                self.sco_progress += dt
                if self.sco_progress >= 3.4:
                    self.sco_progress = 0
                    self.sco_queue.pop(0)
                    head["state"] = "exit"
                    self.money += head["bill"]
                    self._fx(SCO_PAY[0], SCO_PAY[1],
                             f"+{head['bill']} L", "#90caf9")

        # события: разливы и холодильники
        self.next_mess -= dt
        if self.next_mess <= 0 and len(self.messes) < 3:
            self.next_mess = self.rng.uniform(12, 22)
            mid = self._mess_id
            self._mess_id += 1
            self.messes[mid] = {"id": mid,
                                "x": self.rng.uniform(2, 6.6),
                                "y": self.rng.uniform(0.8, 4.4)}
            self._fx(self.messes[mid]["x"], self.messes[mid]["y"],
                     "game.popup.mess", "#ff8a80")
        self.rep = max(0, self.rep - len(self.messes) * 0.2 * dt)
        self.next_fridge -= dt
        if self.next_fridge <= 0 and not self.fridge_alarm:
            self.next_fridge = self.rng.uniform(25, 45)
            self.fridge_alarm = self.rng.choice(FRIDGES)[0]
            self._emit("mgame.event.fridge_alarm", id=self.fridge_alarm)
        if self.fridge_alarm:
            self.rep = max(0, self.rep - 0.4 * dt)

        self._run_bots()

    def _finish(self):
        self.phase = "ended"
        ok = self.money >= self.goal
        self._emit("mgame.event.finished_ok" if ok else
                   "mgame.event.finished_fail",
                   money=self.money, goal=self.goal)
        # поощрения в Roblox-команду
        try:
            from .server import team
            for p in self.players.values():
                if p["roblox_user"]:
                    team.award(p["name"], p["roblox_user"],
                               self.store.store_id,
                               p["stats"]["points"],
                               f"командная смена ({ROLES[p['role']]['title']})")
        except Exception:
            pass

    # ----- встроенные ИИ-боты -------------------------------------------
    def _run_bots(self):
        for p in self.players.values():
            if p["kind"] != "bot" or p["busy"] > 0 or p.get("task"):
                continue
            role = p["role"]
            if role == "cashier" or (role == "supervisor"
                                     and len(self.queue) > 1):
                if self.paper <= 0:
                    self._bot_act(p, "paper")
                elif math.hypot(p["x"] - (REGISTER[1] - .05),
                                p["y"] - (REGISTER[2] + .02)) > 0.4:
                    self._bot_act(p, "serve")
                continue
            if role == "cleaner" and self.messes:
                mid = min(self.messes, key=lambda i: math.hypot(
                    self.messes[i]["x"] - p["x"],
                    self.messes[i]["y"] - p["y"]))
                self._bot_act(p, "clean", target=str(mid))
                continue
            if role == "tech":
                if self.fridge_alarm:
                    self._bot_act(p, "fix_fridge")
                elif self.paper <= 15:
                    self._bot_act(p, "paper")
                continue
            # мерчандайзер и все остальные по умолчанию — полки
            low = min(self.shelves, key=lambda s: s["stock"])
            if p["carry"] > 0 and low["stock"] < low["max"]:
                self._bot_act(p, "restock", target=str(low["i"]))
            elif low["stock"] <= 8:
                self._bot_act(p, "storeroom")
            elif role == "supervisor" and self.messes:
                mid = next(iter(self.messes))
                self._bot_act(p, "clean", target=str(mid))

    def _bot_act(self, p, act, target=None):
        pid = p["id"]
        self.lock.release()            # action() берёт lock сам
        try:
            self.action(pid, act, target=target)
        finally:
            self.lock.acquire()
        p["last_seen"] = time.time()

    # ----- состояние для клиентов и внешних ИИ --------------------------
    def state(self, pid: str = "", after: int = 0) -> dict:
        now = time.time()
        with self.lock:
            dt = min(1.0, now - self._last)
            self._last = now
            if pid in self.players:
                self.players[pid]["last_seen"] = now
            self._tick(dt, now)
            roles_free = {r: ROLES[r]["limit"] - sum(
                1 for p in self.players.values() if p["role"] == r)
                for r in ROLES}
            return {
                "phase": self.phase, "time_left": round(
                    max(0, self.time_left), 1),
                "money": self.money, "goal": self.goal,
                "rep": round(self.rep), "paper": round(self.paper),
                "queue_len": len(self.queue),
                "sco_len": len(self.sco_queue),
                "serving": round(self.serving_progress, 2),
                "fridge_alarm": self.fridge_alarm,
                "roles_free": roles_free,
                "players": [{k: p[k] for k in
                             ("id", "name", "role", "kind", "carry",
                              "busy", "busy_max", "busy_label", "stats")}
                            | {"x": round(p["x"], 2),
                               "y": round(p["y"], 2),
                               "icon": ROLES[p["role"]]["icon"],
                               "role_title": ROLES[p["role"]]["title"]}
                            for p in self.players.values()],
                "customers": [{"id": c["id"], "x": round(c["x"], 2),
                               "y": round(c["y"], 2), "icon": c["icon"],
                               "items": c["items"],
                               "hearts": max(0, math.ceil(
                                   c["patience"] / 20))}
                              for c in self.customers.values()],
                "shelves": [{k: s[k] for k in
                             ("i", "x", "y", "w", "d", "name", "stock",
                              "max")} for s in self.shelves],
                "messes": list(self.messes.values()),
                "events": [e for e in self.events if e["id"] > after],
            }


class MultiHub:
    """Реестр командных сессий: (store_id, код комнаты) → игра."""

    def __init__(self, network):
        self.network = network
        self._lock = threading.Lock()
        self._games: Dict[str, MultiGame] = {}

    def get(self, store_id: str, code: str = "main") -> MultiGame:
        key = f"{store_id}/{(code or 'main')[:16]}"
        with self._lock:
            if key not in self._games:
                self._games[key] = MultiGame(
                    self.network.store(store_id), key)
            return self._games[key]
