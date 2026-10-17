"""Сейф, коллекция и улучшения."""

from __future__ import annotations

from dataclasses import dataclass

from plates import evaluate_plate, plate_from_storage_key, rarity_badge

MAX_SAFE_LEVEL = 5
MAX_COLLECTION_LEVEL = 5

SAFE_CAPACITY: tuple[int, ...] = (3, 6, 10, 15, 22)
COLLECTION_CAPACITY: tuple[int, ...] = (12, 24, 40, 60, 90)

# Стоимость перехода на следующий уровень (index = текущий уровень).
SAFE_UPGRADE_PRICE: tuple[int, ...] = (5000, 18000, 45000, 100000)
COLLECTION_UPGRADE_PRICE: tuple[int, ...] = (7500, 22000, 55000, 130000)


@dataclass(frozen=True, slots=True)
class StoredPlate:
    key: str
    price: int


def safe_capacity(level: int) -> int:
    idx = max(1, min(level, MAX_SAFE_LEVEL)) - 1
    return SAFE_CAPACITY[idx]


def collection_capacity(level: int) -> int:
    idx = max(1, min(level, MAX_COLLECTION_LEVEL)) - 1
    return COLLECTION_CAPACITY[idx]


def collection_bonus_mult(level: int) -> float:
    """Пассивный бонус к «ценности коллекции»."""
    from game_config import cfg

    step = cfg().collection_bonus_step
    lvl = max(1, min(level, MAX_COLLECTION_LEVEL))
    return 1.0 + step * (lvl - 1)


def safe_upgrade_price(current_level: int) -> int | None:
    from game_config import cfg

    prices = cfg().safe_upgrade_prices
    if current_level >= MAX_SAFE_LEVEL or current_level - 1 >= len(prices):
        return None
    return prices[current_level - 1]


def collection_upgrade_price(current_level: int) -> int | None:
    from game_config import cfg

    prices = cfg().collection_upgrade_prices
    if current_level >= MAX_COLLECTION_LEVEL or current_level - 1 >= len(prices):
        return None
    return prices[current_level - 1]


def plate_price(key: str) -> int:
    plate = plate_from_storage_key(key)
    if plate is None:
        return 0
    return evaluate_plate(plate).sell_price


def sorted_stored(keys: list[str]) -> list[StoredPlate]:
    items = [StoredPlate(key=k, price=plate_price(k)) for k in keys]
    items.sort(key=lambda x: x.price, reverse=True)
    return items


def format_plate_short(key: str, price: int | None = None) -> str:
    plate = plate_from_storage_key(key)
    if plate is None:
        return key
    ev = evaluate_plate(plate)
    p = price if price is not None else ev.sell_price
    return f"{rarity_badge(ev.rarity)} · <code>{plate.formatted()}</code> · {p:,} ₽".replace(",", " ")


def collection_total_value(collection_keys: list[str], collection_level: int) -> int:
    total = sum(plate_price(k) for k in collection_keys)
    return int(total * collection_bonus_mult(collection_level))


def vault_summary(safe_level: int, collection_level: int, safe_count: int, collection_count: int) -> str:
    return (
        f"🔐 Сейф: ур. <b>{safe_level}</b> · места "
        f"<b>{safe_count}/{safe_capacity(safe_level)}</b>\n"
        f"📚 Коллекция: ур. <b>{collection_level}</b> · "
        f"<b>{collection_count}/{collection_capacity(collection_level)}</b> · "
        f"бонус ×{collection_bonus_mult(collection_level):.2f}"
    )
