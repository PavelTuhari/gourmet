"""Пример внешнего ИИ-агента для командной смены тренажёра.

Показывает студентам, как подключить собственный ИИ по REST API:
``join`` → цикл ``state``/``action``. Политика простая и зависит от
роли — её и предлагается улучшать в учебных заданиях.

Запуск (сервер должен работать)::

    python -m planogram3d.webapp.tools.demo_bot --role merch \
        --name "ИИ Иванова" --store st17 --room main --seconds 120
"""

import argparse
import json
import time
import urllib.request


def call(url: str, payload=None):
    if payload is None:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def choose_action(state: dict, me: dict, role: str):
    """Политика агента: что делать в текущем состоянии смены."""
    if role == "cashier":
        if state["paper"] <= 0:
            return {"action": "paper"}
        return {"action": "serve"}
    if role == "cleaner" and state["messes"]:
        return {"action": "clean",
                "target": str(state["messes"][0]["id"])}
    if role == "tech":
        if state["fridge_alarm"]:
            return {"action": "fix_fridge"}
        if state["paper"] <= 15:
            return {"action": "paper"}
    # мерчандайзер и запасной вариант для остальных ролей
    low = min(state["shelves"], key=lambda s: s["stock"])
    if me["carry"] > 0 and low["stock"] < low["max"]:
        return {"action": "restock", "target": str(low["i"])}
    if low["stock"] <= 6:
        return {"action": "storeroom"}
    return None


def main():
    ap = argparse.ArgumentParser(description="Внешний ИИ-агент смены")
    ap.add_argument("--base", default="http://127.0.0.1:8050")
    ap.add_argument("--store", default="st17")
    ap.add_argument("--room", default="main")
    ap.add_argument("--role", default="merch",
                    choices=["cashier", "merch", "cleaner", "tech",
                             "supervisor"])
    ap.add_argument("--name", default="Внешний ИИ")
    ap.add_argument("--seconds", type=float, default=180)
    ap.add_argument("--start", action="store_true",
                    help="стартовать смену после подключения")
    args = ap.parse_args()

    api = f"{args.base}/api/mgame/{args.store}/{args.room}"
    joined = call(api + "/join", {"name": args.name, "role": args.role,
                                  "kind": "api"})
    if "error" in joined:
        raise SystemExit(f"Не удалось войти: {joined['error']}")
    pid = joined["player_id"]
    print(f"Подключён как {args.name} ({args.role}), id={pid}")
    if args.start:
        call(api + "/start", {})

    deadline = time.time() + args.seconds
    while time.time() < deadline:
        state = call(f"{api}/state?player={pid}")
        if state["phase"] == "ended":
            print("Смена завершена.")
            break
        me = next((p for p in state["players"] if p["id"] == pid), None)
        if me is None:
            raise SystemExit("Игрок выбыл из смены")
        if state["phase"] == "play" and me["busy"] <= 0:
            act = choose_action(state, me, args.role)
            if act:
                call(api + "/action", {"player": pid, **act})
        time.sleep(0.7)

    for p in sorted(call(f"{api}/state?player={pid}")["players"],
                    key=lambda p: -p["stats"]["points"]):
        print(f"  {p['name']:<22} {p['role']:<11} "
              f"баллы: {p['stats']['points']}")


if __name__ == "__main__":
    main()
