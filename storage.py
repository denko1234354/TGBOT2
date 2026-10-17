"""Простое хранилище баланса и настроек игроков."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

from vault import collection_capacity, safe_capacity

START_BALANCE = 2500
DATA_DIR = "data"
USERS_FILE = "users.json"


def _normalize_selected_region(value: object) -> str:
    code = str(value or "all").strip()
    if not code or code in ("all", "global", "*"):
        return "all"
    return code


@dataclass
class UserState:
    balance: int = START_BALANCE
    selected_region: str = "all"
    last_plate_key: str | None = None
    spins: int = 0
    display_name: str = ""
    best_plate_key: str | None = None
    best_plate_price: int = 0
    lifetime_earnings: int = 0
    safe_level: int = 1
    collection_level: int = 1
    safe_items: list[str] = field(default_factory=list)
    collection_items: list[str] = field(default_factory=list)
    collection_pick: list[str] = field(default_factory=list)


class UserStorage:
    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(base_dir, DATA_DIR, USERS_FILE)
        self._lock = asyncio.Lock()
        self._users: dict[str, UserState] = {}

    async def load(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        if not os.path.isfile(self._path):
            return
        with open(self._path, encoding="utf-8") as f:
            raw = json.load(f)
        for uid, data in raw.items():
            self._users[uid] = UserState(
                balance=int(data.get("balance", START_BALANCE)),
                selected_region=_normalize_selected_region(data.get("selected_region")),
                last_plate_key=data.get("last_plate_key"),
                spins=int(data.get("spins", 0)),
                display_name=str(data.get("display_name", "")),
                best_plate_key=data.get("best_plate_key"),
                best_plate_price=int(data.get("best_plate_price", 0)),
                lifetime_earnings=int(data.get("lifetime_earnings", 0)),
                safe_level=int(data.get("safe_level", 1)),
                collection_level=int(data.get("collection_level", 1)),
                safe_items=list(data.get("safe_items", [])),
                collection_items=list(data.get("collection_items", [])),
                collection_pick=list(data.get("collection_pick", [])),
            )

    async def save(self) -> None:
        async with self._lock:
            payload = {
                uid: {
                    "balance": u.balance,
                    "selected_region": u.selected_region,
                    "last_plate_key": u.last_plate_key,
                    "spins": u.spins,
                    "display_name": u.display_name,
                    "best_plate_key": u.best_plate_key,
                    "best_plate_price": u.best_plate_price,
                    "lifetime_earnings": u.lifetime_earnings,
                    "safe_level": u.safe_level,
                    "collection_level": u.collection_level,
                    "safe_items": u.safe_items,
                    "collection_items": u.collection_items,
                    "collection_pick": u.collection_pick,
                }
                for uid, u in self._users.items()
            }
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

    async def get(self, user_id: int) -> UserState:
        from game_config import cfg

        key = str(user_id)
        async with self._lock:
            if key not in self._users:
                self._users[key] = UserState(balance=int(cfg().start_balance))
            return self._users[key]

    async def list_players(self) -> list[tuple[str, UserState]]:
        async with self._lock:
            rows = list(self._users.items())
        rows.sort(key=lambda item: ((item[1].display_name or item[0]).lower(), -item[1].spins))
        return rows

    async def wipe_user(self, user_id: int) -> bool:
        key = str(user_id)
        async with self._lock:
            existed = key in self._users
            self._users.pop(key, None)
        if existed:
            await self.save()
        return existed

    async def wipe_all(self) -> int:
        async with self._lock:
            count = len(self._users)
            self._users.clear()
        await self.save()
        return count

    async def update(self, user_id: int, **kwargs: object) -> UserState:
        key = str(user_id)
        async with self._lock:
            user = self._users.setdefault(key, UserState())
            for name, value in kwargs.items():
                setattr(user, name, value)
            return user

    async def leaderboard(self, limit: int = 10) -> list[tuple[str, UserState]]:
        async with self._lock:
            rows = [
                (uid, user)
                for uid, user in self._users.items()
                if user.best_plate_price > 0
            ]
        rows.sort(
            key=lambda item: (item[1].best_plate_price, item[1].lifetime_earnings),
            reverse=True,
        )
        return rows[:limit]

    def visible_collection(self, user: UserState) -> list[str]:
        safe = set(user.safe_items)
        return [key for key in user.collection_items if key not in safe]

    def try_add_collection(self, user: UserState, plate_key: str) -> bool:
        if plate_key in user.safe_items:
            return False
        cap = collection_capacity(user.collection_level)
        if plate_key in user.collection_items:
            return True
        if len(self.visible_collection(user)) >= cap:
            return False
        user.collection_items.append(plate_key)
        return True

    def try_add_safe(self, user: UserState, plate_key: str) -> bool:
        cap = safe_capacity(user.safe_level)
        if plate_key in user.safe_items:
            return False
        if len(user.safe_items) >= cap:
            return False
        user.safe_items.append(plate_key)
        if plate_key in user.collection_items:
            user.collection_items.remove(plate_key)
        if plate_key in user.collection_pick:
            user.collection_pick.remove(plate_key)
        return True

    def remove_collection_item(self, user: UserState, plate_key: str) -> bool:
        if plate_key not in user.collection_items:
            return False
        user.collection_items.remove(plate_key)
        if plate_key in user.collection_pick:
            user.collection_pick.remove(plate_key)
        if user.last_plate_key == plate_key:
            user.last_plate_key = None
        return True
