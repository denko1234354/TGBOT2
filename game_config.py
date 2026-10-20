"""Игровые настройки (редактируются через админ-панель)."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field

from regions import GLOBAL_ROULETTE_COST
from data_paths import data_directory

_DEFAULT_START_BALANCE = 2500
_DEFAULT_SAFE_UPGRADE = (5000, 18000, 45000, 100000)
_DEFAULT_COLLECTION_UPGRADE = (7500, 22000, 55000, 130000)


@dataclass
class GameSettings:
    global_roulette_cost: int = GLOBAL_ROULETTE_COST
    start_balance: int = _DEFAULT_START_BALANCE
    sell_price_multiplier: float = 1.0
    special_spawn_multiplier: float = 1.0
    safe_upgrade_prices: list[int] = field(default_factory=lambda: list(_DEFAULT_SAFE_UPGRADE))
    collection_upgrade_prices: list[int] = field(default_factory=lambda: list(_DEFAULT_COLLECTION_UPGRADE))
    collection_bonus_step: float = 0.03


def default_settings() -> GameSettings:
    return GameSettings()


class GameConfigStore:
    def __init__(self, base_dir: str) -> None:
        self._path = os.path.join(data_directory(base_dir), "game_config.json")
        self._lock = asyncio.Lock()
        self._settings = default_settings()

    async def load(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        if not os.path.isfile(self._path):
            await self.save()
            return
        with open(self._path, encoding="utf-8") as f:
            raw = json.load(f)
        self._settings = _from_dict(raw)

    async def save(self) -> None:
        async with self._lock:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(asdict(self._settings), f, ensure_ascii=False, indent=2)

    def get(self) -> GameSettings:
        return self._settings

    async def replace(self, settings: GameSettings) -> None:
        async with self._lock:
            self._settings = settings
        await self.save()

    async def reset(self) -> None:
        await self.replace(default_settings())

    async def set_field(self, key: str, value: int | float | list[int]) -> None:
        async with self._lock:
            if not hasattr(self._settings, key):
                raise KeyError(key)
            setattr(self._settings, key, value)
        await self.save()

_store: GameConfigStore | None = None


def init_game_config(base_dir: str) -> GameConfigStore:
    global _store
    _store = GameConfigStore(base_dir)
    return _store


def cfg() -> GameSettings:
    if _store is None:
        return default_settings()
    return _store.get()


def config_store() -> GameConfigStore:
    assert _store is not None
    return _store


def global_spin_cost() -> int:
    if _store is None:
        return GLOBAL_ROULETTE_COST
    return _store.get().global_roulette_cost


def _from_dict(raw: dict) -> GameSettings:
    base = default_settings()
    data = asdict(base)
    for key in data:
        if key in raw:
            data[key] = raw[key]
    # Старый формат содержал spin_tier_* и базу прокрута, отличную от пошлины
    # в оригинале. На миграции используем значение из оригинальной игры.
    has_legacy_spin_tiers = any(key.startswith("spin_tier_") for key in raw)
    if has_legacy_spin_tiers or raw.get("global_roulette_cost") == 220:
        data["global_roulette_cost"] = GLOBAL_ROULETTE_COST
    return GameSettings(**data)


CONFIG_FIELDS: dict[str, str] = {
    "global_roulette_cost": "🎰 Базовая пошлина (₽)",
    "start_balance": "💳 Стартовый баланс новых игроков",
    "sell_price_multiplier": "💵 Множитель цены продажи номеров",
    "special_spawn_multiplier": "✨ Множ. шанса спецномеров",
    "collection_bonus_step": "📚 +бонус коллекции за уровень",
}


def format_config_text(settings: GameSettings | None = None) -> str:
    s = settings or cfg()
    lines = ["⚙️ <b>Настройки игры</b>", ""]
    for key, label in CONFIG_FIELDS.items():
        lines.append(f"{label}: <b>{getattr(s, key)}</b>")
    lines.append("")
    lines.append(f"🔐 Цены улучшения сейфа: <code>{s.safe_upgrade_prices}</code>")
    lines.append(f"📚 Цены улучшения коллекции: <code>{s.collection_upgrade_prices}</code>")
    return "\n".join(lines)
