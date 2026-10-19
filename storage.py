"""Простое хранилище баланса и настроек игроков."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from vault import collection_capacity, safe_capacity
from data_paths import data_directory

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
        self._data_dir = data_directory(base_dir)
        self._path = os.path.join(self._data_dir, USERS_FILE)
        self._feedback_path = os.path.join(self._data_dir, "feedback.json")
        self._promos_path = os.path.join(self._data_dir, "promocodes.json")
        self._lock = asyncio.Lock()
        self._feedback_lock = asyncio.Lock()
        self._promos_lock = asyncio.Lock()
        self._users: dict[str, UserState] = {}
        self._feedback: list[dict[str, object]] = []
        self._promos: dict[str, dict[str, object]] = {}

    async def load(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)
        raw = {}
        if os.path.isfile(self._path):
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
        if os.path.isfile(self._feedback_path):
            with open(self._feedback_path, encoding="utf-8") as f:
                raw_feedback = json.load(f)
            if isinstance(raw_feedback, list):
                self._feedback = [item for item in raw_feedback if isinstance(item, dict)]
        if os.path.isfile(self._promos_path):
            with open(self._promos_path, encoding="utf-8") as f:
                raw_promos = json.load(f)
            if isinstance(raw_promos, dict):
                self._promos = {
                    str(code).upper(): item
                    for code, item in raw_promos.items()
                    if isinstance(item, dict)
                }

    async def _save_promos(self) -> None:
        os.makedirs(os.path.dirname(self._promos_path), exist_ok=True)
        with open(self._promos_path, "w", encoding="utf-8") as f:
            json.dump(self._promos, f, ensure_ascii=False, indent=2)

    async def add_promo(self, code: str, reward: int, max_uses: int) -> bool:
        normalized = code.strip().upper()
        async with self._promos_lock:
            if normalized in self._promos:
                return False
            self._promos[normalized] = {
                "reward": reward,
                "max_uses": max_uses,
                "redeemed_by": [],
                "active": True,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            }
            await self._save_promos()
            return True

    async def list_promos(self) -> list[tuple[str, dict[str, object]]]:
        async with self._promos_lock:
            return [(code, dict(data)) for code, data in sorted(self._promos.items())]

    async def redeem_promo(self, user_id: int, code: str) -> tuple[str, int, int]:
        """Return (status, reward, balance); a code can be claimed once per player."""
        user = await self.get(user_id)
        normalized = code.strip().upper()
        async with self._promos_lock:
            promo = self._promos.get(normalized)
            if promo is None:
                return "not_found", 0, user.balance
            if not promo.get("active", True):
                return "inactive", 0, user.balance
            redeemed = [str(uid) for uid in promo.get("redeemed_by", [])]
            if str(user_id) in redeemed:
                return "used", 0, user.balance
            max_uses = int(promo.get("max_uses", 0))
            if max_uses > 0 and len(redeemed) >= max_uses:
                return "exhausted", 0, user.balance
            reward = max(0, int(promo.get("reward", 0)))
            if reward <= 0:
                return "inactive", 0, user.balance
            redeemed.append(str(user_id))
            promo["redeemed_by"] = redeemed
            async with self._lock:
                current = self._users.setdefault(str(user_id), user)
                current.balance += reward
                balance = current.balance
            await self._save_promos()
            await self.save()
            return "success", reward, balance

    async def add_feedback(self, user_id: int, display_name: str, text: str) -> None:
        async with self._feedback_lock:
            self._feedback.append({
                "user_id": user_id,
                "display_name": display_name,
                "text": text,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            })
            os.makedirs(self._data_dir, exist_ok=True)
            with open(self._feedback_path, "w", encoding="utf-8") as f:
                json.dump(self._feedback, f, ensure_ascii=False, indent=2)

    async def list_feedback(self) -> list[dict[str, object]]:
        async with self._feedback_lock:
            return [dict(item) for item in reversed(self._feedback)]

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
            os.makedirs(self._data_dir, exist_ok=True)
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

    async def sell_last_plate(self, user_id: int, plate_key: str, price: int) -> int | None:
        """Sell the current spin result once; None means it was already consumed."""
        async with self._lock:
            user = self._users.get(str(user_id))
            if user is None or user.last_plate_key != plate_key or plate_key in user.safe_items:
                return None
            user.last_plate_key = None
            user.collection_items = [key for key in user.collection_items if key != plate_key]
            user.collection_pick = [key for key in user.collection_pick if key != plate_key]
            user.balance += price
            user.lifetime_earnings += price
            balance = user.balance
        await self.save()
        return balance

    async def sell_collection_plates(
        self,
        user_id: int,
        requested: list[tuple[str, int]],
    ) -> tuple[list[tuple[str, int]], int]:
        """Atomically sell only requested plates still present in the collection."""
        sold: list[tuple[str, int]] = []
        async with self._lock:
            user = self._users.get(str(user_id))
            if user is None:
                return sold, 0
            available = set(user.collection_items) - set(user.safe_items)
            seen: set[str] = set()
            for plate_key, price in requested:
                if plate_key in available and plate_key not in seen:
                    sold.append((plate_key, price))
                    seen.add(plate_key)
            if not sold:
                return sold, user.balance
            user.collection_items = [key for key in user.collection_items if key not in seen]
            user.collection_pick = [key for key in user.collection_pick if key not in seen]
            if user.last_plate_key in seen:
                user.last_plate_key = None
            earned = sum(price for _, price in sold)
            user.balance += earned
            user.lifetime_earnings += earned
            balance = user.balance
        await self.save()
        return sold, balance

    async def sell_safe_plate(self, user_id: int, plate_key: str, price: int) -> int | None:
        """Sell a plate only if it is still stored in the safe."""
        async with self._lock:
            user = self._users.get(str(user_id))
            if user is None or plate_key not in user.safe_items:
                return None
            user.safe_items = [key for key in user.safe_items if key != plate_key]
            user.balance += price
            user.lifetime_earnings += price
            balance = user.balance
        await self.save()
        return balance

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
