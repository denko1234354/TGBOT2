"""Генерация и оценка российских автомобильных номеров (гражданские и спецсерии)."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from regions import REGIONS, Region, get_region, region_multiplier, registration_codes_for

# Допустимые буквы на гражданских госномерах РФ.
PLATE_LETTERS = "АВЕКМНОРСТУХ"

KIND_CIVILIAN = "civilian"

# Multipliers and category bonuses follow the original game's price cards.
REGION_CODE_MULT: dict[str, float] = {"two_digit": 1.0, "three_digit": 0.69, "repeated": 0.57}
RARITY_CLASS_MULT: dict[str, float] = {
    "common": 1.0,
    "uncommon": 1.05,
    "rare": 1.2,
    "epic": 16.0,
    "legendary": 50.0,
}


@dataclass(frozen=True, slots=True)
class PlateKindInfo:
    id: str
    title: str
    emoji: str
    price_multiplier: float
    spawn_weight: int
    short: str


PLATE_KINDS: dict[str, PlateKindInfo] = {
    KIND_CIVILIAN: PlateKindInfo("civilian", "Гражданский", "🚗", 1.0, 780, "civ"),
    "diplomatic": PlateKindInfo("diplomatic", "Дипломатический (красный)", "🟥", 14.0, 4, "dip"),
    "military": PlateKindInfo("military", "Военный (чёрный)", "🪖", 9.0, 10, "mil"),
    "fso": PlateKindInfo("fso", "ФСО / федеральная охрана", "🛡", 11.0, 5, "fso"),
    "mvd": PlateKindInfo("mvd", "МВД / полиция", "🚔", 7.0, 14, "mvd"),
    "mchs": PlateKindInfo("mchs", "МЧС", "🚒", 5.5, 12, "mch"),
    "prosecutor": PlateKindInfo("prosecutor", "Прокуратура / следствие", "⚖️", 6.5, 8, "pro"),
    "transit": PlateKindInfo("transit", "Транзитный", "🚛", 1.0, 22, "trn"),
    "taxi": PlateKindInfo("taxi", "Такси", "🚕", 1.0, 35, "tax"),
}

_KIND_WEIGHTS: list[tuple[str, int]] = [(k.id, k.spawn_weight) for k in PLATE_KINDS.values()]

KIND_ALIASES: dict[str, str] = {
    "граж": KIND_CIVILIAN,
    "civ": KIND_CIVILIAN,
    "дип": "diplomatic",
    "дипломат": "diplomatic",
    "diplomatic": "diplomatic",
    "cd": "diplomatic",
    "воен": "military",
    "армия": "military",
    "mil": "military",
    "мвд": "mvd",
    "полиция": "mvd",
    "gibdd": "mvd",
    "фсо": "fso",
    "fso": "fso",
    "мчс": "mchs",
    "прок": "prosecutor",
    "прокуратура": "prosecutor",
    "следствие": "prosecutor",
    "транзит": "transit",
    "tr": "transit",
    "такси": "taxi",
    "taxi": "taxi",
}

DIPLO_TAIL = ("CD", "DP", "MD", "TD", "CC", "DD")


@dataclass(frozen=True, slots=True)
class RarityInfo:
    id: str
    name: str
    emoji: str


RARITY_COMMON = RarityInfo("common", "Обычный", "⚪")
RARITY_UNCOMMON = RarityInfo("uncommon", "Необычный", "🟢")
RARITY_RARE = RarityInfo("rare", "Редкий", "🔵")
RARITY_EPIC = RarityInfo("epic", "Эпический", "🟣")
RARITY_LEGENDARY = RarityInfo("legendary", "Легендарный", "🟡")


@dataclass(frozen=True, slots=True)
class Specialty:
    id: str
    title: str
    multiplier: float
    emoji: str
    reason: str = ""


# Буквы только из разрешённого набора АВЕКМНОРСТУХ.
# Ключ — три буквы серии (А + УЕ = АУЕ) или две буквы хвоста.
BLAT_TRIPLE: dict[str, tuple[str, float, str]] = {
    "АУЕ": ("Блатная серия АУЕ", 7.5, "классический «блатной» код АУЕ"),
    "ВОР": ("Блатной ВОР", 6.5, "серия ВОР — воровской статус"),
    "ХУЕ": ("Блатная серия ХУЕ", 5.5, "мат-серия из трёх букв"),
    "ХЕР": ("Блатная серия ХЕР", 4.8, "грубая трёхбуквенная серия"),
    "СУК": ("Блатная серия СУК", 5.0, "серия СУК — тюремный сленг"),
    "НАХ": ("Блатная серия НАХ", 4.5, "грубый трёхбуквенный код"),
    "ХАМ": ("Серия ХАМ", 4.0, "серия ХАМ — наглая «блатная» связка"),
    "КУМ": ("Серия КУМ", 3.8, "блатная кличка «кум»"),
    "КОТ": ("Серия КОТ", 3.6, "блатная кличка «кот»"),
    "АКМ": ("Серия АКМ", 4.5, "АКМ — «калаш», силовой статус"),
    "МУР": ("Серия МУР", 4.4, "МУР — намёк на угрозыск"),
    "СКР": ("Серия СКР", 4.0, "СКР — следственный комитет"),
    "ОМН": ("Серия ОМН", 4.2, "почти ОМОН — силовой код"),
    "ВВС": ("Серия ВВС", 3.8, "ВВС — военный/статусный код"),
    "МММ": ("Серия МММ", 4.0, "МММ — культовая трёхбуквенка"),
    "РУС": ("Серия РУС", 3.5, "РУС — патриотичный код"),
    "МОС": ("Серия МОС", 3.5, "МОС — намёк на Москву"),
    "УРА": ("Серия УРА", 3.2, "УРА — победный код"),
    "ХАН": ("Серия ХАН", 3.5, "ХАН — «царский» код"),
    "РАК": ("Серия РАК", 3.0, "трёхбуквенка РАК"),
    "СОС": ("Серия СОС", 3.2, "SOS кириллицей"),
    "ТРУ": ("Серия ТРУ", 3.0, "ТРУ — «трушный» код"),
}

KIND_REASONS: dict[str, str] = {
    "diplomatic": "красный дипломатический номер (CD/DP) — редкая спецсерия",
    "military": "чёрный военный номер — ведомственная серия армии",
    "fso": "серия федеральной охраны — высокий статус",
    "mvd": "номер МВД / полиции — служебная серия",
    "mchs": "номер МЧС — аварийно-спасательная серия",
    "prosecutor": "номер прокуратуры / следствия — ведомственный статус",
    "transit": "транзитный номер — временная серия",
    "taxi": "жёлтый коммерческий / такси — массовая серия, цена ниже",
}


@dataclass(frozen=True, slots=True)
class Plate:
    letter1: str
    digits: str
    letter2: str
    letter3: str
    region_code: str
    kind: str = KIND_CIVILIAN

    @property
    def series(self) -> str:
        if self.kind == "taxi":
            return f"{self.letter2}{self.letter3}{self.digits}"
        if self.kind == "transit":
            return f"Т{self.letter2}{self.letter3}{self.digits}"
        return f"{self.letter1}{self.digits}{self.letter2}{self.letter3}"

    def kind_info(self) -> PlateKindInfo:
        return PLATE_KINDS.get(self.kind, PLATE_KINDS[KIND_CIVILIAN])

    def formatted(self) -> str:
        info = self.kind_info()
        if self.kind == "diplomatic":
            body = f"D {self.digits} {self.letter2}{self.letter3}"
        elif self.kind == "military":
            body = f"{self.digits} {self.letter2}{self.letter3}"
        elif self.kind == "taxi":
            body = f"{self.letter2}{self.letter3} {self.digits}"
        elif self.kind == "transit":
            body = f"Т {self.letter2}{self.letter3} {self.digits}"
        else:
            body = f"{self.letter1} {self.digits} {self.letter2}{self.letter3}"
        return f"{info.emoji} {body} {self.region_code}"


@dataclass(frozen=True, slots=True)
class PlateEvaluation:
    plate: Plate
    region: Region | None
    specialties: tuple[Specialty, ...]
    base_value: int
    combination_bonus: int
    combo_multiplier: float
    region_multiplier: float
    code_multiplier: float
    kind_multiplier: float
    class_multiplier: float
    total_multiplier: float
    sell_price: int
    rarity: RarityInfo


def rarity_badge(rarity: RarityInfo) -> str:
    return f"{rarity.emoji} <b>{rarity.name}</b>"


def determine_rarity(
    plate: Plate,
    specialties: tuple[Specialty, ...],
    total_multiplier: float,
) -> RarityInfo:
    bonus = sum(int(s.multiplier) for s in specialties)
    if bonus >= 90_000:
        return RARITY_LEGENDARY
    if bonus >= 40_000:
        return RARITY_EPIC
    if bonus >= 20_000:
        return RARITY_RARE
    if bonus >= 5_000:
        return RARITY_UNCOMMON
    return RARITY_COMMON


def _random_letters(count: int, rng: random.Random) -> str:
    return "".join(rng.choice(PLATE_LETTERS) for _ in range(count))


def _roll_kind(rng: random.Random) -> str:
    from game_config import cfg

    spawn_mult = max(0.0, cfg().special_spawn_multiplier)
    weighted: list[tuple[str, int]] = []
    for kind_id, weight in _KIND_WEIGHTS:
        if kind_id == KIND_CIVILIAN:
            weighted.append((kind_id, weight))
        else:
            scaled = max(1, int(round(weight * spawn_mult))) if spawn_mult > 0 else 0
            if scaled > 0:
                weighted.append((kind_id, scaled))
    total = sum(w for _, w in weighted) or 1
    point = rng.randint(1, total)
    acc = 0
    for kind_id, weight in weighted:
        acc += weight
        if point <= acc:
            return kind_id
    return KIND_CIVILIAN


def _gov_digits(rng: random.Random, kind: str) -> str:
    """У спецслужб чаще «красивые» и малые номера."""
    if kind == KIND_CIVILIAN:
        return f"{rng.randint(0, 999):03d}"
    if kind == "military":
        if rng.random() < 0.35:
            return f"{rng.randint(0, 99):02d}{rng.randint(0, 99):02d}"
        return f"{rng.randint(0, 9999):04d}"
    if rng.random() < 0.4:
        return f"{rng.randint(0, 99):03d}"
    return f"{rng.randint(0, 999):03d}"


def generate_plate(region_code: str | None, rng: random.Random | None = None) -> Plate:
    rng = rng or random.Random()
    if region_code is None:
        region = rng.choice(REGIONS)
        region_code = rng.choice(region.registration_codes)
    else:
        region_code = rng.choice(registration_codes_for(region_code))

    kind = _roll_kind(rng)
    digits = _gov_digits(rng, kind)

    if kind == "diplomatic":
        tail = rng.choice(DIPLO_TAIL)
        return Plate("D", digits, tail[0], tail[1], region_code, kind=kind)

    if kind == "military":
        l2, l3 = _random_letters(2, rng)
        return Plate("", digits, l2, l3, region_code, kind=kind)

    if kind == "taxi":
        l2, l3 = _random_letters(2, rng)
        return Plate("", digits, l2, l3, region_code, kind=kind)

    if kind == "transit":
        l2, l3 = _random_letters(2, rng)
        return Plate("Т", digits, l2, l3, region_code, kind=kind)

    l1 = rng.choice(PLATE_LETTERS)
    l2, l3 = _random_letters(2, rng)
    return Plate(l1, digits, l2, l3, region_code, kind=kind)


def _kind_specialty(kind: str) -> Specialty | None:
    info = PLATE_KINDS.get(kind)
    if info is None or kind == KIND_CIVILIAN:
        return None
    return Specialty(
        f"kind_{kind}",
        info.title,
        info.price_multiplier,
        info.emoji,
        KIND_REASONS.get(kind, "специальный тип госномера"),
    )


def _spec(
    spec_id: str,
    title: str,
    multiplier: float,
    emoji: str,
    reason: str,
) -> Specialty:
    return Specialty(spec_id, title, multiplier, emoji, reason)


def _detect_digit_specialties(digits: str) -> list[Specialty]:
    found: list[Specialty] = []
    if not digits.isdigit():
        return found

    if len(digits) == 4:
        if digits[0] == digits[1] == digits[2] == digits[3]:
            found.append(
                _spec(
                    "quad",
                    "Четыре одинаковые цифры",
                    5.0,
                    "💥",
                    f"все четыре цифры совпадают: {digits}",
                )
            )
        if digits in ("7777", "0001", "0070"):
            found.append(
                _spec(
                    "mil_elite",
                    "Элитный военный код",
                    4.0,
                    "🎖",
                    f"редкий военный набор цифр {digits}",
                )
            )
        return found

    a, b, c = digits[0], digits[1], digits[2]

    if a == b == c:
        found.append(
            _spec(
                "triple",
                "Три одинаковые цифры",
                4.0,
                "🔥",
                f"цифры {digits} — все три одинаковые",
            )
        )
        if digits == "777":
            found.append(
                _spec("jackpot777", "Джекпот 777", 8.0, "👑", "классический «счастливый» набор 777")
            )
        if digits == "666":
            found.append(_spec("beast666", "Зверь 666", 5.5, "😈", "культовый набор 666"))
        if digits == "000":
            found.append(
                _spec("triple_zero", "Тройной ноль", 4.5, "💎", "номер 000 — один из самых статусных")
            )

    if digits == "007":
        found.append(_spec("agent007", "Агент 007", 6.0, "🕶", "цифры 007 — «агентский» код"))
    if digits == "001":
        found.append(_spec("first001", "Первый 001", 4.0, "🥇", "цифры 001 — почти первый номер серии"))
    if digits == "888":
        found.append(_spec("lucky888", "Удача 888", 5.0, "🍀", "цифры 888 считаются удачными"))

    if a != b or b != c:
        if a == b:
            found.append(
                _spec(
                    "pair_digits",
                    "Пара одинаковых цифр",
                    1.6,
                    "✨",
                    f"две одинаковые цифры в начале: {a}{b}",
                )
            )
        elif b == c:
            found.append(
                _spec(
                    "pair_digits",
                    "Пара одинаковых цифр",
                    1.6,
                    "✨",
                    f"две одинаковые цифры в конце: {b}{c}",
                )
            )
        elif a == c:
            found.append(
                _spec(
                    "pair_digits",
                    "Пара одинаковых цифр",
                    1.6,
                    "✨",
                    f"крайние цифры совпадают: {a} и {c}",
                )
            )

    if digits in ("012", "123", "234", "345", "456", "567", "678", "789"):
        found.append(
            _spec(
                "sequence_asc",
                "Прямая последовательность",
                2.8,
                "📈",
                f"цифры идут подряд вверх: {digits}",
            )
        )
    if digits in ("987", "876", "765", "654", "543", "432", "321", "210"):
        found.append(
            _spec(
                "sequence_desc",
                "Обратная последовательность",
                2.8,
                "📉",
                f"цифры идут подряд вниз: {digits}",
            )
        )

    if digits[0] == digits[2] and digits[0] != digits[1]:
        found.append(
            _spec(
                "mirror3",
                "Зеркальные цифры",
                2.4,
                "🪞",
                f"{digits} читается одинаково с начала и с конца",
            )
        )

    if digits.endswith("00") and digits != "000":
        found.append(
            _spec("round_hundred", "Ровная сотня", 2.0, "💰", f"круглое окончание на 00: {digits}")
        )

    if digits in ("100", "200", "300", "400", "500", "600", "700", "800", "900"):
        found.append(
            _spec("round_exact", "Круглая сумма", 2.2, "⭕", f"ровная сотня {digits}")
        )

    return found


def _detect_letter_specialties(plate: Plate) -> list[Specialty]:
    found: list[Specialty] = []
    tail = f"{plate.letter2}{plate.letter3}"
    if plate.kind == "diplomatic":
        if tail in ("CD", "CC"):
            found.append(
                _spec(
                    "diplo_cd",
                    "Серия CD",
                    2.2,
                    "🇺🇳",
                    f"хвост {tail} — дипломатический корпус (Corps Diplomatique)",
                )
            )
        return found

    letter_group = (
        (plate.letter2, plate.letter3)
        if plate.kind in ("taxi", "transit", "military")
        else (plate.letter1, plate.letter2, plate.letter3)
    )
    if len(set(letter_group)) == 1 and len(letter_group) == 3:
        found.append(
            _spec(
                "triple_letter",
                "Три одинаковые буквы",
                3.5,
                "🏆",
                f"все три буквы одинаковые: {''.join(letter_group)}",
            )
        )
    elif len(set(letter_group)) < len(letter_group):
        found.append(
            _spec(
                "twin_letters",
                "Две одинаковые буквы",
                1.7,
                "🔤",
                "в серии есть две одинаковые буквы",
            )
        )

    status = "АМОРТУХ"
    if plate.letter2 in status and plate.letter3 in status:
        found.append(
            _spec(
                "status_letters",
                "Статусные буквы",
                1.35,
                "⭐",
                f"буквы {tail} из «красивого» набора А, М, О, Р, Т, У, Х",
            )
        )

    full = plate.series.lower()
    if plate.letter1 and full == full[::-1] and len(set(full)) > 1:
        shown = plate.series
        found.append(
            _spec(
                "full_palindrome",
                "Палиндром серии",
                5.0,
                "🌀",
                f"{shown} читается одинаково слева направо и справа налево",
            )
        )

    return found


def _detect_blat_specialties(plate: Plate) -> list[Specialty]:
    if plate.kind == "diplomatic" or not plate.letter1:
        return []
    triple = f"{plate.letter1}{plate.letter2}{plate.letter3}"
    if triple not in BLAT_TRIPLE:
        return []
    title, mult, reason = BLAT_TRIPLE[triple]
    return [_spec("blat_triple", title, mult, "🕷", reason)]


def _detect_gov_specialties(plate: Plate) -> list[Specialty]:
    if plate.kind == KIND_CIVILIAN:
        return []
    found: list[Specialty] = []
    num_str = plate.digits.lstrip("0") or "0"
    try:
        num = int(num_str)
    except ValueError:
        return found
    if num <= 20:
        found.append(
            _spec(
                "gov_reserve",
                "Гос. резерв",
                3.0,
                "🏛",
                f"малый номер {plate.digits} (до 020) — «генеральский» пул",
            )
        )
    elif num <= 100:
        found.append(
            _spec(
                "gov_pool",
                "Ведомственный пул",
                1.8,
                "📋",
                f"номер {plate.digits} из первой сотни ведомства",
            )
        )
    return found


def _dedupe_specialties(items: list[Specialty]) -> tuple[Specialty, ...]:
    seen: set[str] = set()
    out: list[Specialty] = []
    for s in items:
        if s.id in seen:
            continue
        seen.add(s.id)
        out.append(s)
    return tuple(out)


def evaluate_plate(plate: Plate) -> PlateEvaluation:
    region = get_region(plate.region_code)
    tier = region.tier if region else 3
    base = 100

    detected: list[Specialty] = []
    detected.extend(_detect_digit_specialties(plate.digits))
    detected.extend(_detect_letter_specialties(plate))
    detected.extend(_detect_blat_specialties(plate))
    detected.extend(_detect_gov_specialties(plate))
    detected = list(_dedupe_specialties(detected))

    bonus_by_id = {
        "twin_letters": 8_000,
        "triple_letter": 24_000,
        "triple": 21_000,
        "quad": 30_000,
        "sequence_asc": 5_000,
        "sequence_desc": 5_000,
        "mirror3": 10_000,
        "full_palindrome": 12_000,
        "pair_digits": 2_000,
        "round_hundred": 2_000,
        "round_exact": 3_000,
        "agent007": 5_000,
        "first001": 3_000,
        "lucky888": 5_000,
        "blat_triple": 8_000,
        "diplo_cd": 50_000,
        "gov_reserve": 10_000,
        "gov_pool": 3_000,
    }
    kind_bonus = {
        "fso": 50_000,
        "diplomatic": 50_000,
        "military": 24_000,
        "mvd": 24_000,
        "prosecutor": 24_000,
        "mchs": 12_000,
        "taxi": 0,
        "transit": 0,
    }

    priced: list[Specialty] = []
    for item in detected:
        amount = bonus_by_id.get(item.id, 0)
        if amount:
            priced.append(Specialty(item.id, item.title, float(amount), item.emoji, item.reason))
    kind_amount = kind_bonus.get(plate.kind, 0)
    if kind_amount:
        kind = PLATE_KINDS[plate.kind]
        priced.append(
            Specialty(f"kind_{plate.kind}", kind.title, float(kind_amount), kind.emoji, KIND_REASONS.get(plate.kind, ""))
        )

    if (
        tier == 1
        and plate.kind == KIND_CIVILIAN
        and plate.digits[0] == plate.digits[1] == plate.digits[2]
        and f"{plate.letter2}{plate.letter3}" == "МО"
    ):
        priced.append(Specialty("moscow_government", "Мэрия Москвы", 24_000.0, "🏛"))
    if plate.kind == KIND_CIVILIAN and plate.letter1 == "М" and plate.letter2 == plate.letter3 == "М":
        priced.append(Specialty("former_mvd", "Ранее МВД, сейчас в основном частники", 24_000.0, "🚔"))
    if (
        plate.kind == KIND_CIVILIAN
        and plate.digits[0] == plate.digits[1] == plate.digits[2]
        and plate.letter1 == plate.letter2 == plate.letter3
    ):
        priced.append(Specialty("full_plate", "Фуллблат: все цифры и буквы одинаковые", 24_000.0, "🏆"))

    if any(item.id == "triple_letter" for item in detected):
        priced = [item for item in priced if item.id != "twin_letters"]

    if plate.kind == "taxi":
        found = {item.id for item in detected}
        priced = []
        if "sequence_asc" in found or "sequence_desc" in found:
            sequence_bonus = 200 if "twin_letters" in found else 100
            priced.append(Specialty("sequence", "Цифры подряд", float(sequence_bonus), "📈"))
        if "twin_letters" in found:
            priced.append(Specialty("twin_letters", "Две одинаковые буквы", 2_900.0, "🔤"))
        if "triple" in found:
            priced.append(Specialty("triple", "Три одинаковые цифры", 2_796.0, "🔥"))
        if "triple" in found and "twin_letters" in found:
            priced.append(Specialty("taxi_full_combo", "Полный такси-комбо", 3_554.0, "🏆"))

    specs = tuple(priced)
    combination_bonus = sum(int(item.multiplier) for item in specs)
    if plate.kind == "taxi":
        found = {item.id for item in detected}
        if "triple" in found and "twin_letters" in found:
            rarity = RARITY_LEGENDARY
        elif "triple" in found:
            rarity = RARITY_EPIC
        elif "twin_letters" in found and ("sequence_asc" in found or "sequence_desc" in found):
            rarity = RARITY_RARE
        elif "twin_letters" in found or "sequence_asc" in found or "sequence_desc" in found:
            rarity = RARITY_UNCOMMON
        else:
            rarity = RARITY_COMMON
    else:
        rarity = determine_rarity(plate, specs, float(combination_bonus))
    combo_mult = 3.38 if rarity.id == "legendary" else 1.5 if rarity.id in ("rare", "epic") else 1.0
    region_mult = region_multiplier(plate.region_code)
    code_mult = (
        REGION_CODE_MULT["two_digit"]
        if len(plate.region_code) <= 2
        else REGION_CODE_MULT["repeated"]
        if len(set(plate.region_code)) == 1
        else REGION_CODE_MULT["three_digit"]
    )
    kind_mult = 2.0 if plate.kind == "taxi" else 1.0
    class_mult = RARITY_CLASS_MULT[rarity.id]
    total_mult = combo_mult * region_mult * code_mult * kind_mult * class_mult

    from game_config import cfg

    sell = int((base + combination_bonus) * total_mult * cfg().sell_price_multiplier)
    sell = max(sell, 10)

    return PlateEvaluation(
        plate=plate,
        region=region,
        specialties=specs,
        base_value=base,
        combination_bonus=combination_bonus,
        combo_multiplier=combo_mult,
        region_multiplier=region_mult,
        code_multiplier=code_mult,
        kind_multiplier=kind_mult,
        class_multiplier=class_mult,
        total_multiplier=total_mult,
        sell_price=sell,
        rarity=rarity,
    )


_PARSE_RE = re.compile(
    r"^\s*([авекмнорстухАВЕКМНОРСТУХ])\s*(\d{3})\s*([авекмнорстухАВЕКМНОРСТУХ]{2})\s*(\d{2,3})\s*$",
    re.IGNORECASE,
)
_PARSE_COMPACT_RE = re.compile(
    r"^\s*([авекмнорстухАВЕКМНОРСТУХ])(\d{3})([авекмнорстухАВЕКМНОРСТУХ]{2})\s*(\d{2,3})\s*$",
    re.IGNORECASE,
)
_PARSE_DIPLO_RE = re.compile(
    r"^\s*[dD]\s*(\d{3})\s*([cCdDmMtTpP]{2})\s*(\d{2,3})\s*$",
)
_PARSE_MIL_RE = re.compile(
    r"^\s*(\d{4})\s*([авекмнорстухАВЕКМНОРСТУХ]{2})\s*(\d{2,3})\s*$",
    re.IGNORECASE,
)
_PARSE_TAXI_RE = re.compile(
    r"^\s*([авекмнорстухАВЕКМНОРСТУХ]{2})\s*(\d{3})\s*(\d{2,3})\s*$",
    re.IGNORECASE,
)
_PARSE_TRANSIT_RE = re.compile(
    r"^\s*Т\s*([авекмнорстухАВЕКМНОРСТУХ]{2})\s*(\d{3})\s*(\d{2,3})\s*$",
    re.IGNORECASE,
)

_LATIN_PLATE_LETTERS = str.maketrans({
    "A": "А", "B": "В", "E": "Е", "K": "К", "M": "М", "H": "Н",
    "O": "О", "P": "Р", "C": "С", "T": "Т", "Y": "У", "X": "Х",
    "a": "А", "b": "В", "e": "Е", "k": "К", "m": "М", "h": "Н",
    "o": "О", "p": "Р", "c": "С", "t": "Т", "y": "У", "x": "Х",
})


def _extract_kind_prefix(text: str) -> tuple[str, str]:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return KIND_CIVILIAN, text
    alias = parts[0].lower().replace("ё", "е")
    if alias in KIND_ALIASES:
        rest = parts[1] if len(parts) > 1 else ""
        return KIND_ALIASES[alias], rest
    return KIND_CIVILIAN, text


def parse_plate_text(text: str) -> Plate | None:
    cleaned = text.replace("|", " ").strip()
    kind, body = _extract_kind_prefix(cleaned)
    body = body.strip()

    # Standard Russian plates use Cyrillic letters that look like Latin ones;
    # users often type them with an English keyboard layout.
    if kind != "diplomatic":
        body = body.translate(_LATIN_PLATE_LETTERS)

    m = _PARSE_DIPLO_RE.match(body)
    if m or kind == "diplomatic":
        if m:
            digits, tail, region = m.groups()
            return Plate("D", digits, tail[0].upper(), tail[1].upper(), region, kind="diplomatic")

    m = _PARSE_MIL_RE.match(body)
    if m or kind == "military":
        if m:
            digits, tail, region = m.groups()
            return Plate("", digits, tail[0].upper(), tail[1].upper(), region, kind="military")

    if kind == "transit" or body.startswith("Т "):
        m = _PARSE_TRANSIT_RE.match(body)
        if m:
            tail, digits, region = m.groups()
            return Plate("Т", digits, tail[0].upper(), tail[1].upper(), region, kind="transit")

    if kind == "taxi":
        m = _PARSE_TAXI_RE.match(body)
        if m:
            tail, digits, region = m.groups()
            return Plate("", digits, tail[0].upper(), tail[1].upper(), region, kind="taxi")

    if kind == KIND_CIVILIAN:
        m = _PARSE_TAXI_RE.match(body)
        if m:
            tail, digits, region = m.groups()
            return Plate("", digits, tail[0].upper(), tail[1].upper(), region, kind="taxi")

    m = _PARSE_COMPACT_RE.match(body) or _PARSE_RE.match(body)
    if not m:
        return None
    l1, digits, tail, region = m.groups()
    return Plate(
        letter1=l1.upper(),
        digits=digits,
        letter2=tail[0].upper(),
        letter3=tail[1].upper(),
        region_code=region,
        kind=kind,
    )


def plate_storage_key(plate: Plate) -> str:
    info = plate.kind_info()
    return (
        f"{info.short}:{plate.kind}:{plate.letter1}:{plate.digits}:"
        f"{plate.letter2}{plate.letter3}:{plate.region_code}"
    )


def plate_from_storage_key(key: str) -> Plate | None:
    parts = key.split(":")
    if len(parts) == 6:
        _, kind, l1, digits, tail, region = parts
        if len(tail) != 2:
            return None
        return Plate(l1, digits, tail[0], tail[1], region, kind=kind)
    if len(parts) == 4:
        l1, digits, tail, region = parts
        if len(tail) != 2:
            return None
        return Plate(l1, digits, tail[0], tail[1], region, kind=KIND_CIVILIAN)
    return None


def format_evaluation(ev: PlateEvaluation) -> str:
    region_name = ev.region.name if ev.region else "Неизвестный регион"
    kind = ev.plate.kind_info()
    lines = [
        f"{rarity_badge(ev.rarity)} · <b>{ev.plate.formatted()}</b>",
        f"📂 Тип: {kind.emoji} <b>{kind.title}</b>",
        f"📍 {region_name} ({ev.plate.region_code})",
        "",
        f"Базовая стоимость: <b>{ev.base_value}</b> ₽",
    ]
    if ev.specialties:
        lines.append("")
        lines.append("<b>Комбинации</b>")
        for s in ev.specialties:
            why = f" — {s.reason}" if s.reason else ""
            lines.append(f"{s.emoji} {s.title} <b>+{int(s.multiplier):,} ₽</b>{why}".replace(",", " "))
    lines.extend(
        [
            "",
            f"Комбо ×{ev.combo_multiplier:g} · регион ×{ev.region_multiplier:g} · "
            f"код ×{ev.code_multiplier:g} · тип ×{ev.kind_multiplier:g} · класс ×{ev.class_multiplier:g}",
            f"💵 Цена номера: <b>{ev.sell_price:,}</b> ₽".replace(",", " "),
        ]
    )
    return "\n".join(lines)
