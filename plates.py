"""Генерация и оценка российских автомобильных номеров (гражданские и спецсерии)."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from regions import REGIONS, Region, get_region, region_value_bonus

# Допустимые буквы на гражданских госномерах РФ.
PLATE_LETTERS = "АВЕКМНОРСТУХ"

KIND_CIVILIAN = "civilian"

# Множитель стоимости региона при продаже номера.
REGION_SELL_MULT: dict[int, float] = {1: 1.45, 2: 1.2, 3: 1.0, 4: 0.85}


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
    "transit": PlateKindInfo("transit", "Транзитный", "🚛", 1.35, 22, "trn"),
    "taxi": PlateKindInfo("taxi", "Такси / коммерция", "🚕", 0.72, 35, "tax"),
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


RARITY_COMMON = RarityInfo("common", "Обычные", "⚪")
RARITY_UNCOMMON = RarityInfo("uncommon", "Необычные", "🟢")
RARITY_EPIC = RarityInfo("epic", "Эпические", "🟣")
RARITY_LEGENDARY = RarityInfo("legendary", "Легендарные", "🟡")


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
        return f"{self.letter1}{self.digits}{self.letter2}{self.letter3}"

    def kind_info(self) -> PlateKindInfo:
        return PLATE_KINDS.get(self.kind, PLATE_KINDS[KIND_CIVILIAN])

    def formatted(self) -> str:
        info = self.kind_info()
        if self.kind == "diplomatic":
            body = f"D {self.digits} {self.letter2}{self.letter3}"
        elif self.kind == "military":
            body = f"{self.digits} {self.letter2}{self.letter3}"
        else:
            body = f"{self.letter1} {self.digits} {self.letter2}{self.letter3}"
        return f"{info.emoji} {body} {self.region_code}"


@dataclass(frozen=True, slots=True)
class PlateEvaluation:
    plate: Plate
    region: Region | None
    specialties: tuple[Specialty, ...]
    base_value: int
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
    combo = [s for s in specialties if not s.id.startswith("kind_")]
    spec_ids = {s.id for s in specialties}

    if total_multiplier >= 45:
        return RARITY_LEGENDARY
    if "jackpot777" in spec_ids and total_multiplier >= 12:
        return RARITY_LEGENDARY
    if plate.kind == "diplomatic" and total_multiplier >= 25:
        return RARITY_LEGENDARY
    if plate.kind in ("fso", "military") and total_multiplier >= 30:
        return RARITY_LEGENDARY

    if total_multiplier >= 9 or len(combo) >= 3:
        return RARITY_EPIC
    if plate.kind in ("diplomatic", "fso", "military", "mvd", "prosecutor") and total_multiplier >= 6:
        return RARITY_EPIC

    if total_multiplier >= 2.4 or combo or plate.kind not in (KIND_CIVILIAN, "taxi"):
        if plate.kind == "taxi" and total_multiplier < 2 and not combo:
            return RARITY_COMMON
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
        region_code = rng.choice(REGIONS).code

    kind = _roll_kind(rng)
    digits = _gov_digits(rng, kind)

    if kind == "diplomatic":
        tail = rng.choice(DIPLO_TAIL)
        return Plate("D", digits, tail[0], tail[1], region_code, kind=kind)

    if kind == "military":
        l2, l3 = _random_letters(2, rng)
        return Plate("", digits, l2, l3, region_code, kind=kind)

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

    if digits in ("123", "234", "345", "456", "567", "678", "789"):
        found.append(
            _spec(
                "sequence_asc",
                "Прямая последовательность",
                2.8,
                "📈",
                f"цифры идут подряд вверх: {digits}",
            )
        )
    if digits in ("987", "876", "765", "654", "543", "432", "321"):
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

    if plate.letter2 == plate.letter3:
        found.append(
            _spec(
                "twin_letters",
                "Две одинаковые буквы",
                1.7,
                "🔤",
                f"в конце две одинаковые буквы: {tail}",
            )
        )
    if plate.letter1 and plate.letter1 == plate.letter2 == plate.letter3:
        found.append(
            _spec(
                "triple_letter",
                "Тройная буква",
                3.5,
                "🏆",
                f"все три буквы одинаковые: {plate.letter1}{tail}",
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
    base = 80 + region_value_bonus(tier)

    specs_list: list[Specialty] = []
    kind_spec = _kind_specialty(plate.kind)
    if kind_spec:
        specs_list.append(kind_spec)
    specs_list.extend(_detect_digit_specialties(plate.digits))
    specs_list.extend(_detect_letter_specialties(plate))
    specs_list.extend(_detect_blat_specialties(plate))
    specs_list.extend(_detect_gov_specialties(plate))
    specs = _dedupe_specialties(specs_list)

    mult = 1.0
    for s in specs:
        mult *= s.multiplier
    mult = min(mult, 200.0)

    from game_config import cfg

    region_mult = REGION_SELL_MULT.get(tier, 1.0)
    sell = int(base * mult * region_mult * cfg().sell_price_multiplier)
    sell = max(sell, 10)

    rarity = determine_rarity(plate, specs, mult)

    return PlateEvaluation(
        plate=plate,
        region=region,
        specialties=specs,
        base_value=base,
        total_multiplier=mult,
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
    tier = ev.region.tier if ev.region else 3
    region_mult = REGION_SELL_MULT.get(tier, 1.0)
    lines = [
        f"{rarity_badge(ev.rarity)} · <b>{ev.plate.formatted()}</b>",
        f"📂 Тип: {kind.emoji} <b>{kind.title}</b>",
        f"📍 {region_name} ({ev.plate.region_code})",
        "",
        f"База региона: <b>{ev.base_value}</b> ₽",
        f"Регион: <b>×{region_mult:.2f}</b> (престиж кода {ev.plate.region_code})",
        f"Итоговый множитель комбо: <b>×{ev.total_multiplier:.2f}</b>",
        f"💵 Продажа: <b>{ev.sell_price}</b> ₽",
    ]
    combo_specs = [s for s in ev.specialties if not s.id.startswith("kind_")]
    kind_specs = [s for s in ev.specialties if s.id.startswith("kind_")]
    if kind_specs or combo_specs:
        lines.append("")
        lines.append("<b>За что иксы</b> (все перемножаются):")
        for s in kind_specs + combo_specs:
            why = f" — {s.reason}" if s.reason else ""
            lines.append(f"{s.emoji} {s.title} <b>×{s.multiplier:g}</b>{why}")
    else:
        lines.append("")
        lines.append("Обычный номер — нет комбо букв, цифр и спецсерии, иксы не начислены.")
    return "\n".join(lines)
