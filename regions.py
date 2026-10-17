"""Регионы РФ для игровых госномеров: код, название, tier и цена прокрута."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Region:
    code: str
    name: str
    tier: int  # 1 — премиум, 4 — дешёвые


# Tier задаёт престиж региона и стоимость прокрута «своего» региона.
SPIN_COST_BY_TIER: dict[int, int] = {
    1: 450,
    2: 280,
    3: 170,
    4: 90,
}

GLOBAL_ROULETTE_COST = 220

# Коды для общей рулетки (все субъекты представлены хотя бы одним кодом).
REGIONS: tuple[Region, ...] = (
    Region("77", "Москва", 1),
    Region("99", "Москва", 1),
    Region("97", "Москва", 1),
    Region("177", "Москва", 1),
    Region("199", "Москва", 1),
    Region("777", "Москва", 1),
    Region("78", "Санкт-Петербург", 1),
    Region("98", "Санкт-Петербург", 1),
    Region("178", "Санкт-Петербург", 1),
    Region("50", "Московская область", 2),
    Region("750", "Московская область", 2),
    Region("790", "Московская область", 2),
    Region("23", "Краснодарский край", 2),
    Region("93", "Краснодарский край", 2),
    Region("123", "Краснодарский край", 2),
    Region("61", "Ростовская область", 2),
    Region("161", "Ростовская область", 2),
    Region("63", "Самарская область", 2),
    Region("163", "Самарская область", 2),
    Region("716", "Казань / Татарстан", 2),
    Region("116", "Казань / Татарстан", 2),
    Region("02", "Башкортостан", 3),
    Region("102", "Башкортостан", 3),
    Region("16", "Татарстан", 3),
    Region("52", "Нижегородская область", 3),
    Region("152", "Нижегородская область", 3),
    Region("66", "Свердловская область", 3),
    Region("96", "Свердловская область", 3),
    Region("196", "Свердловская область", 3),
    Region("54", "Новосибирская область", 3),
    Region("154", "Новосибирская область", 3),
    Region("24", "Красноярский край", 3),
    Region("124", "Красноярский край", 3),
    Region("36", "Воронежская область", 3),
    Region("136", "Воронежская область", 3),
    Region("47", "Ленинградская область", 3),
    Region("147", "Ленинградская область", 3),
    Region("39", "Калининградская область", 3),
    Region("139", "Калининградская область", 3),
    Region("25", "Приморский край", 3),
    Region("125", "Приморский край", 3),
    Region("27", "Хабаровский край", 3),
    Region("127", "Хабаровский край", 3),
    Region("03", "Бурятия", 4),
    Region("04", "Алтай", 4),
    Region("14", "Якутия", 4),
    Region("19", "Хакасия", 4),
    Region("75", "Забайкальский край", 4),
    Region("87", "Чукотка", 4),
    Region("89", "Ямало-Ненецкий АО", 4),
)

# Уникальные коды (первое вхождение в списке сохраняем для выбора).
_REGION_BY_CODE: dict[str, Region] = {}
for _r in REGIONS:
    _REGION_BY_CODE.setdefault(_r.code, _r)

UNIQUE_REGIONS: tuple[Region, ...] = tuple(_REGION_BY_CODE.values())


def get_region(code: str) -> Region | None:
    return _REGION_BY_CODE.get(code)


def spin_cost_for_region(code: str) -> int:
    from game_config import spin_cost_for_tier

    region = get_region(code)
    tier = region.tier if region else 3
    return spin_cost_for_tier(tier)


def region_value_bonus(tier: int) -> int:
    return {1: 520, 2: 280, 3: 120, 4: 40}.get(tier, 120)
