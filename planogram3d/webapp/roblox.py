"""Интеграция с Roblox: команда магазина, бонусы и поощрения.

Члены команды регистрируются (имя + ник в Roblox), проходят смены
веб-тренажёра и игровые кейсы — за успехи начисляются баллы и бейджи.
Начисления отправляются в Roblox-опыт сети:

* **реальный режим** — через Roblox Open Cloud API (переменные
  окружения ``ROBLOX_API_KEY`` и ``ROBLOX_UNIVERSE_ID``):

  - баллы сотрудника пишутся в стандартный DataStore ``GourmanTeam``;
  - объявление о поощрении публикуется в MessagingService (топик
    ``gourman-rewards``) — сгенерированный robloxkit place подписан на
    него и показывает поздравление прямо в игре, начисляя leaderstats;

* **эмуляция** — без ключей всё учитывается локально (файл-реестр),
  интерфейс тот же.

Общение команды происходит в самом Roblox-опыте (встроенный чат);
эта интеграция обеспечивает единый счёт баллов и события поощрений.
"""

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional

#: бейджи за пройденные обучающие кейсы (смены тренажёра)
BADGES = {
    1: "🥉 Кассир-новичок",
    2: "🥈 Хранитель чистоты",
    3: "🥇 Герой часа пик",
}
MASTER_BADGE = "🏆 Наставник смены"   # все три смены на 3 звезды


class RobloxCloud:
    """Клиент Roblox Open Cloud (DataStore + MessagingService)."""

    def __init__(self, api_key: str, universe_id: str,
                 timeout: float = 6.0):
        self.api_key = api_key
        self.universe_id = universe_id
        self.timeout = timeout
        self.mode = "roblox"

    def _request(self, url: str, payload: dict,
                 content_type: str = "application/json") -> None:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"x-api-key": self.api_key,
                     "Content-Type": content_type}, method="POST")
        urllib.request.urlopen(req, timeout=self.timeout).read()

    def save_member(self, member: dict) -> None:
        """Баллы сотрудника → стандартный DataStore GourmanTeam."""
        key = urllib.parse.quote(member["roblox_user"])
        url = (f"https://apis.roblox.com/datastores/v1/universes/"
               f"{self.universe_id}/standard-datastores/datastore/entries/"
               f"entry?datastoreName=GourmanTeam&entryKey={key}")
        self._request(url, {
            "name": member["name"], "points": member["points"],
            "badges": member["badges"], "store_id": member["store_id"]})

    def announce(self, message: dict) -> None:
        """Поощрение → MessagingService (топик gourman-rewards)."""
        url = (f"https://apis.roblox.com/messaging-service/v1/universes/"
               f"{self.universe_id}/topics/gourman-rewards")
        self._request(url, {"message": json.dumps(message)})


class RobloxEmulator:
    """Локальная эмуляция Open Cloud: те же вызовы, журнал в памяти."""

    def __init__(self):
        self.mode = "emulation"
        self.log: List[dict] = []

    def save_member(self, member: dict) -> None:
        self.log.append({"op": "datastore", "user": member["roblox_user"],
                         "points": member["points"]})

    def announce(self, message: dict) -> None:
        self.log.append({"op": "announce", **message})


def create_cloud():
    api_key = os.environ.get("ROBLOX_API_KEY")
    universe = os.environ.get("ROBLOX_UNIVERSE_ID")
    if api_key and universe:
        return RobloxCloud(api_key, universe)
    return RobloxEmulator()


class TeamHub:
    """Реестр команды: регистрация, баллы, бейджи, лента поощрений."""

    def __init__(self, path: Optional[str] = None):
        self.cloud = create_cloud()
        self.path = Path(path or os.environ.get(
            "PLANOGRAM_TEAM_FILE", "planogram_team.json"))
        self._lock = threading.Lock()
        self.members: dict = {}
        self.feed: List[dict] = []
        self._load()

    # ----- персистентность ---------------------------------------------
    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.members = data.get("members", {})
                self.feed = data.get("feed", [])[-50:]
            except (ValueError, OSError):
                pass

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(
                {"members": self.members, "feed": self.feed[-50:]},
                ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    # ----- API ----------------------------------------------------------
    def register(self, name: str, roblox_user: str,
                 store_id: str) -> dict:
        key = roblox_user.strip().lower()
        with self._lock:
            member = self.members.get(key)
            if member is None:
                member = {"name": name.strip(), "roblox_user":
                          roblox_user.strip(), "store_id": store_id,
                          "points": 0, "badges": [], "shifts": {},
                          "registered_at": time.time()}
                self.members[key] = member
                self.feed.insert(0, {
                    "t": time.time(),
                    "text": f"👋 {member['name']} "
                            f"({member['roblox_user']}) присоединился "
                            f"к команде"})
            else:
                member["name"] = name.strip() or member["name"]
                member["store_id"] = store_id or member["store_id"]
            self._save()
            return dict(member)

    def progress(self, name: str, roblox_user: str, store_id: str,
                 level: int, stars: int, revenue: int,
                 stats: dict) -> dict:
        """Результат смены тренажёра → бонусы и поощрения."""
        member = self.register(name, roblox_user, store_id)
        key = member["roblox_user"].strip().lower()
        with self._lock:
            member = self.members[key]
            bonus = stars * 100 + round(revenue / 20)
            bonus += min(50, stats.get("served", 0) * 5)
            new_badges = []
            if stars > 0:
                shift_key = str(level)
                best = member["shifts"].get(shift_key, 0)
                member["shifts"][shift_key] = max(best, stars)
                badge = BADGES.get(level)
                if badge and badge not in member["badges"]:
                    member["badges"].append(badge)
                    new_badges.append(badge)
                if (len([s for s in member["shifts"].values()
                         if s >= 3]) >= 3
                        and MASTER_BADGE not in member["badges"]):
                    member["badges"].append(MASTER_BADGE)
                    new_badges.append(MASTER_BADGE)
                    bonus += 200
            member["points"] += bonus

            reason = (f"смена {level} " +
                      ("пройдена, " + "★" * stars if stars else
                       "не пройдена") + f", выручка {revenue} ₽")
            self.feed.insert(0, {
                "t": time.time(),
                "text": f"💎 {member['name']}: +{bonus} баллов — {reason}"
                        + (" · " + ", ".join(new_badges)
                           if new_badges else "")})
            self._save()
            snapshot = dict(member)

        # отправка в Roblox (реальный Open Cloud или эмуляция)
        ok = True
        try:
            self.cloud.save_member(snapshot)
            self.cloud.announce({
                "roblox_user": snapshot["roblox_user"],
                "name": snapshot["name"], "points": bonus,
                "reason": reason})
        except Exception:
            ok = False
        return {"bonus": bonus, "total": snapshot["points"],
                "badges": snapshot["badges"], "new_badges": new_badges,
                "mode": self.cloud.mode, "delivered": ok,
                "top": self.leaderboard()[:5]}

    def award(self, name: str, roblox_user: str, store_id: str,
              points: int, reason: str) -> dict:
        """Прямое поощрение (например, за командную смену тренажёра)."""
        member = self.register(name, roblox_user, store_id)
        key = member["roblox_user"].strip().lower()
        with self._lock:
            member = self.members[key]
            member["points"] += int(points)
            self.feed.insert(0, {
                "t": time.time(),
                "text": f"💎 {member['name']}: +{points} баллов — {reason}"})
            self._save()
            snapshot = dict(member)
        try:
            self.cloud.save_member(snapshot)
            self.cloud.announce({"roblox_user": snapshot["roblox_user"],
                                 "name": snapshot["name"],
                                 "points": int(points), "reason": reason})
        except Exception:
            pass
        return snapshot

    def leaderboard(self) -> List[dict]:
        with self._lock:
            rows = sorted(self.members.values(),
                          key=lambda mm: -mm["points"])
            return [{"name": mm["name"],
                     "roblox_user": mm["roblox_user"],
                     "store_id": mm["store_id"], "points": mm["points"],
                     "badges": mm["badges"]} for mm in rows]

    def team(self) -> dict:
        return {"mode": self.cloud.mode,
                "members": self.leaderboard(),
                "feed": self.feed[:20]}
