"""Конвертация текста в Unicode-шрифты."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FontStyle:
    id: str
    name: str
    emoji: str
    category: str


@dataclass(frozen=True, slots=True)
class FontCategory:
    id: str
    name: str
    emoji: str


FONT_CATEGORIES: tuple[FontCategory, ...] = (
    FontCategory("math", "Математика", "📐"),
    FontCategory("decor", "Декоративные", "⭕"),
    FontCategory("fx", "Эффекты", "🎭"),
    FontCategory("latin", "Латиница", "🔤"),
    FontCategory("cyrillic", "Кириллица", "🇷🇺"),
)

# fmt: off
FONT_STYLES: tuple[FontStyle, ...] = (
    # --- Математика ---
    FontStyle("bold", "Жирный", "𝐁", "math"),
    FontStyle("italic", "Курсив", "𝘐", "math"),
    FontStyle("bold_italic", "Жирный курсив", "𝘽", "math"),
    FontStyle("script", "Рукописный", "𝒮", "math"),
    FontStyle("bold_script", "Жирный рукописный", "𝓢", "math"),
    FontStyle("fraktur", "Готика", "𝔉", "math"),
    FontStyle("bold_fraktur", "Жирная готика", "𝕱", "math"),
    FontStyle("double", "Обводной", "𝔸", "math"),
    FontStyle("sans", "Sans", "𝖲", "math"),
    FontStyle("sans_bold", "Sans жирный", "𝗦", "math"),
    FontStyle("sans_italic", "Sans курсив", "𝘚", "math"),
    FontStyle("sans_bold_italic", "Sans ж. курсив", "𝙎", "math"),
    FontStyle("mono", "Моноширинный", "𝚂", "math"),
    FontStyle("small_caps", "Малые заглавные", "S", "math"),
    # --- Декоративные ---
    FontStyle("circled", "В кружках", "Ⓢ", "decor"),
    FontStyle("circled_neg", "Чёрные кружки", "🅂", "decor"),
    FontStyle("squared", "В квадратах", "🅂", "decor"),
    FontStyle("parenthesized", "В скобках", "🄢", "decor"),
    FontStyle("fullwidth", "Широкий", "Ｓ", "decor"),
    FontStyle("regional", "Региональные", "🇸", "decor"),
    FontStyle("keycap", "Клавиши", "1️⃣", "decor"),
    FontStyle("subscript", "Подстрочный", "ₛ", "decor"),
    FontStyle("superscript", "Надстрочный", "ˢ", "decor"),
    # --- Эффекты ---
    FontStyle("underline", "Подчёркнутый", "S̲", "fx"),
    FontStyle("double_underline", "Двойное подч.", "S̳", "fx"),
    FontStyle("overline", "Надчёркнутый", "S̅", "fx"),
    FontStyle("strikethrough", "Зачёркнутый", "S̶", "fx"),
    FontStyle("dot_above", "Точки сверху", "Ṡ", "fx"),
    FontStyle("tilde_above", "Волна сверху", "S̃", "fx"),
    FontStyle("upside_down", "Перевёрнутый", "S", "fx"),
    FontStyle("mirror", "Зеркало", "S", "fx"),
    FontStyle("spaced", "С пробелами", "S", "fx"),
    FontStyle("vaporwave", "Vaporwave", "Ａ", "fx"),
    FontStyle("alternating", "Чередование", "Aa", "fx"),
    FontStyle("brackets_square", "【Скобки】", "【", "fx"),
    FontStyle("brackets_angle", "《Угловые》", "《", "fx"),
    FontStyle("brackets_flower", "❰Цветы❱", "❰", "fx"),
    FontStyle("stars", "Со звёздами", "★", "fx"),
    FontStyle("dots", "С точками", "·", "fx"),
    FontStyle("hearts", "С сердечками", "♥", "fx"),
    FontStyle("fire", "Огонь", "🔥", "fx"),
    FontStyle("sparkle", "Блеск", "✨", "fx"),
    FontStyle("wave", "Волны", "〜", "fx"),
    # --- Латиница (эстетика) ---
    FontStyle("lat_greek", "Греческий", "α", "latin"),
    FontStyle("lat_currency", "Валюта", "₳", "latin"),
    FontStyle("lat_symbols", "Символы", "☯", "latin"),
    FontStyle("lat_medieval", "Средневек.", "🕯", "latin"),
    FontStyle("lat_tech", "Тech", "▸", "latin"),
    FontStyle("lat_cute", "Милый", "🌸", "latin"),
    FontStyle("lat_hacker", "Хакер", "⌗", "latin"),
    FontStyle("lat_royal", "Королевский", "👑", "latin"),
    FontStyle("lat_bubble", "Пузырьки", "ⓐ", "latin"),
    FontStyle("lat_stylish", "Стильный", "💎", "latin"),
    FontStyle("lat_minimal", "Минимал", "▁", "latin"),
    FontStyle("lat_graffiti", "Граффити", "🎨", "latin"),
    # --- Кириллица ---
    FontStyle("cyr_elegant", "Изящный", "а", "cyrillic"),
    FontStyle("cyr_bold", "Жирный", "б", "cyrillic"),
    FontStyle("cyr_gothic", "Готика", "г", "cyrillic"),
    FontStyle("cyr_round", "Круглый", "д", "cyrillic"),
    FontStyle("cyr_script", "Рукопись", "е", "cyrillic"),
    FontStyle("cyr_fairy", "Сказочный", "ж", "cyrillic"),
    FontStyle("cyr_dark", "Тёмный", "з", "cyrillic"),
    FontStyle("cyr_cute", "Милый", "и", "cyrillic"),
    FontStyle("cyr_old", "Старослав.", "к", "cyrillic"),
    FontStyle("cyr_modern", "Модерн", "л", "cyrillic"),
    FontStyle("cyr_line", "Линии", "м", "cyrillic"),
    FontStyle("cyr_star", "Звёзды", "н", "cyrillic"),
)
# fmt: on

FONTS_PER_PAGE = 8

_CYR_TO_LAT: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}

_SCRIPT_UPPER: dict[str, str] = {
    "B": "ℬ", "E": "ℰ", "F": "ℱ", "H": "ℋ", "I": "ℐ",
    "L": "ℒ", "M": "ℳ", "R": "ℛ", "e": "ℯ", "g": "ℊ", "o": "ℴ",
}
_BOLD_SCRIPT_UPPER: dict[str, str] = {
    "B": "𝓑", "E": "𝓔", "F": "𝓕", "H": "𝓗", "I": "𝓘",
    "L": "𝓛", "M": "𝓜", "R": "𝓡", "e": "𝓮", "g": "𝓰", "o": "𝓸",
}
_FRAKTUR_UPPER: dict[str, str] = {"C": "ℭ", "H": "ℌ", "I": "ℑ", "R": "ℜ", "Z": "ℨ"}
_BOLD_FRAKTUR_UPPER: dict[str, str] = {"C": "𝕮", "H": "𝕳", "I": "𝕴", "R": "ℝ", "Z": "ℤ"}
_DOUBLE_UPPER: dict[str, str] = {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}

_SMALL_CAPS: dict[str, str] = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ",
    "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ",
    "o": "ᴏ", "p": "ᴘ", "q": "ꞯ", "r": "ʀ", "s": "s", "t": "ᴛ", "u": "ᴜ",
    "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ",
}

_SUBSCRIPT: dict[str, str] = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅",
    "6": "₆", "7": "₇", "8": "₈", "9": "₉", "a": "ₐ", "e": "ₑ",
    "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ",
    "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ",
    "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
}

_SUPERSCRIPT: dict[str, str] = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
    "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "a": "ᵃ", "b": "ᵇ",
    "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ", "h": "ʰ",
    "i": "ⁱ", "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ",
    "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
    "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
    "A": "ᴬ", "B": "ᴮ", "D": "ᴰ", "E": "ᴱ", "G": "ᴳ", "H": "ᴴ",
    "I": "ᴵ", "J": "ᴶ", "K": "ᴷ", "L": "ᴸ", "M": "ᴹ", "N": "ᴺ",
    "O": "ᴼ", "P": "ᴾ", "R": "ᴿ", "T": "ᵀ", "U": "ᵁ", "V": "ⱽ", "W": "ᵂ",
}

_UPSIDE_DOWN: dict[str, str] = {
    "a": "ɐ", "b": "q", "c": "ɔ", "d": "p", "e": "ǝ", "f": "ɟ", "g": "ƃ",
    "h": "ɥ", "i": "ᴉ", "j": "ɾ", "k": "ʞ", "l": "l", "m": "ɯ", "n": "u",
    "o": "o", "p": "d", "q": "b", "r": "ɹ", "s": "s", "t": "ʇ", "u": "n",
    "v": "ʌ", "w": "ʍ", "x": "x", "y": "ʎ", "z": "z",
    "A": "∀", "B": "q", "C": "Ɔ", "D": "p", "E": "Ǝ", "F": "Ⅎ", "G": "פ",
    "H": "H", "I": "I", "J": "ſ", "K": "ʞ", "L": "˥", "M": "W", "N": "N",
    "O": "O", "P": "Ԁ", "Q": "Q", "R": "R", "S": "S", "T": "┴", "U": "∩",
    "V": "Λ", "W": "M", "X": "X", "Y": "⅄", "Z": "Z",
    "0": "0", "1": "⇂", "2": "ϛ", "3": "Ɛ", "4": "ㄣ", "5": "ϛ", "6": "9",
    "7": "ㄥ", "8": "8", "9": "6", ".": "˙", ",": "'", "?": "¿", "!": "¡",
    "(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<",
    "&": "⅋", "_": "‾",
}

_LAT_GREEK: dict[str, str] = {
    "a": "α", "b": "в", "c": "¢", "d": "∂", "e": "ε", "f": "ƒ", "g": "ϱ",
    "h": "н", "i": "ι", "j": "ϳ", "k": "κ", "l": "ℓ", "m": "μ", "n": "η",
    "o": "σ", "p": "ρ", "q": "φ", "r": "я", "s": "ѕ", "t": "τ", "u": "υ",
    "v": "ν", "w": "ω", "x": "χ", "y": "γ", "z": "ζ",
    "A": "Α", "B": "Β", "C": "Ϲ", "D": "Δ", "E": "Ε", "F": "Ϝ", "G": "Γ",
    "H": "Η", "I": "Ι", "J": "ϑ", "K": "Κ", "L": "Λ", "M": "Μ", "N": "Ν",
    "O": "Ο", "P": "Ρ", "Q": "Θ", "R": "Я", "S": "Ѕ", "T": "Τ", "U": "Υ",
    "V": "Ѵ", "W": "Ѡ", "X": "Χ", "Y": "Ψ", "Z": "Ζ",
}

_LAT_CURRENCY: dict[str, str] = {
    "a": "₳", "b": "฿", "c": "¢", "d": "₫", "e": "€", "f": "₣", "g": "₲",
    "h": "₶", "i": "ℹ", "j": "Ɉ", "k": "₭", "l": "₺", "m": "₥", "n": "₦",
    "o": "⊙", "p": "₱", "q": "Q", "r": "₹", "s": "$", "t": "₸", "u": "∪",
    "v": "ⱽ", "w": "₩", "x": "Ӿ", "y": "¥", "z": "Ƶ",
}

_LAT_SYMBOLS: dict[str, str] = {
    "a": "ą", "b": "♭", "c": "☯", "d": "ď", "e": "∈", "f": "ƒ", "g": "ğ",
    "h": "♨", "i": "į", "j": "♪", "k": "ķ", "l": "ł", "m": "♏", "n": "ñ",
    "o": "ø", "p": "þ", "q": "φ", "r": "ř", "s": "§", "t": "†", "u": "ų",
    "v": "√", "w": "ẁ", "x": "×", "y": "ý", "z": "ž",
}

_LAT_MEDIEVAL: dict[str, str] = {
    "a": "ä", "b": "ß", "c": "ç", "d": "ð", "e": "ë", "f": "ƒ", "g": "ğ",
    "h": "ħ", "i": "ï", "j": "ĵ", "k": "ķ", "l": "ľ", "m": "ṁ", "n": "ñ",
    "o": "ö", "p": "þ", "q": "q", "r": "ř", "s": "š", "t": "ţ", "u": "ü",
    "v": "ṽ", "w": "ẅ", "x": "ẋ", "y": "ÿ", "z": "ž",
}

_LAT_TECH: dict[str, str] = {
    "a": "▲", "b": "β", "c": "©", "d": "◆", "e": "∈", "f": "ƒ", "g": "ɢ",
    "h": "♨", "i": "ℹ", "j": "⌂", "k": "⌘", "l": "↳", "m": "♍", "n": "♮",
    "o": "⊙", "p": "¶", "q": "Ω", "r": "®", "s": "§", "t": "†", "u": "∪",
    "v": "✓", "w": "ω", "x": "✕", "y": "¥", "z": "Ƶ",
}

_LAT_CUTE: dict[str, str] = {
    "a": "🄰", "b": "🄱", "c": "🄲", "d": "🄳", "e": "🄴", "f": "🄵", "g": "🄶",
    "h": "🄷", "i": "🄸", "j": "🄹", "k": "🄺", "l": "🄻", "m": "🄼", "n": "🄽",
    "o": "🄾", "p": "🄿", "q": "🅀", "r": "🅁", "s": "🅂", "t": "🅃", "u": "🅄",
    "v": "🅅", "w": "🅆", "x": "🅇", "y": "🅈", "z": "🅉",
}

_LAT_HACKER: dict[str, str] = {
    "a": "4", "b": "8", "c": "(", "d": "d", "e": "3", "f": "ƒ", "g": "6",
    "h": "#", "i": "1", "j": "j", "k": "|<", "l": "|_", "m": "|\\/|", "n": "|\\|",
    "o": "0", "p": "¶", "q": "q", "r": "Я", "s": "5", "t": "7", "u": "µ",
    "v": "\\/", "w": "\\/\\/", "x": "×", "y": "¥", "z": "2",
}

_LAT_ROYAL: dict[str, str] = {
    "a": "👑", "b": "♔", "c": "♕", "d": "♖", "e": "♗", "f": "♘", "g": "♙",
    "h": "⚜", "i": "💎", "j": "🏰", "k": "🗡", "l": "⚔", "m": "🛡", "n": "🏹",
    "o": "🔱", "p": "💠", "q": "❖", "r": "♜", "s": "✦", "t": "⚜", "u": "☀",
    "v": "✧", "w": "♛", "x": "✵", "y": "☽", "z": "⚡",
}

_LAT_BUBBLE: dict[str, str] = {chr(i): chr(0x24D0 + i - ord("a")) for i in range(ord("a"), ord("z") + 1)}
_LAT_BUBBLE.update({chr(i): chr(0x24B6 + i - ord("A")) for i in range(ord("A"), ord("Z") + 1)})

_LAT_STYLISH: dict[str, str] = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ", "g": "ɢ",
    "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ",
    "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "ꜱ", "t": "ᴛ", "u": "ᴜ",
    "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ",
}

_LAT_MINIMAL: dict[str, str] = {
    "a": "ₐ", "b": "ᵦ", "c": "ᶜ", "d": "ᵈ", "e": "ₑ", "f": "ᶠ", "g": "ᵍ",
    "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ",
    "o": "ₒ", "p": "ₚ", "q": "q", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
    "v": "ᵥ", "w": "w", "x": "ₓ", "y": "y", "z": "z",
}

_LAT_GRAFFITI: dict[str, str] = {
    "a": "ᗩ", "b": "ᗷ", "c": "ᑕ", "d": "ᗪ", "e": "ᗴ", "f": "ᖴ", "g": "ᘜ",
    "h": "ᕼ", "i": "Ꭵ", "j": "ᒍ", "k": "Ҝ", "l": "ᒪ", "m": "ᗰ", "n": "ᑎ",
    "o": "ᗝ", "p": "ᑭ", "q": "ᑫ", "r": "ᖇ", "s": "ᔕ", "t": "T", "u": "ᑌ",
    "v": "ᐯ", "w": "ᗯ", "x": "᙭", "y": "Y", "z": "ᘔ",
}

_CYR_ELEGANT: dict[str, str] = {
    "а": "ᴀ", "б": "б", "в": "ʙ", "г": "г", "д": "д", "е": "ᴇ", "ё": "ё",
    "ж": "ж", "з": "з", "и": "и", "й": "й", "к": "ᴋ", "л": "л", "м": "м",
    "н": "н", "о": "ᴏ", "п": "п", "р": "ᴘ", "с": "ᴄ", "т": "т", "у": "у",
    "ф": "ꜰ", "х": "х", "ц": "ц", "ч": "ч", "ш": "ш", "щ": "щ", "ъ": "ъ",
    "ы": "ы", "ь": "ь", "э": "э", "ю": "ю", "я": "я",
    "А": "ᴀ", "Б": "Б", "В": "ʙ", "Г": "Г", "Д": "Д", "Е": "ᴇ", "Ё": "Ё",
    "Ж": "Ж", "З": "З", "И": "И", "Й": "Й", "К": "ᴋ", "Л": "Л", "М": "М",
    "Н": "Н", "О": "ᴏ", "П": "П", "Р": "ᴘ", "С": "ᴄ", "Т": "Т", "У": "У",
    "Ф": "ꜰ", "Х": "Х", "Ц": "Ц", "Ч": "Ч", "Ш": "Ш", "Щ": "Щ", "Ъ": "Ъ",
    "Ы": "Ы", "Ь": "Ь", "Э": "Э", "Ю": "Ю", "Я": "Я",
}

_CYR_BOLD: dict[str, str] = {
    "а": "𝐚", "б": "𝐛", "в": "𝐯", "г": "𝐠", "д": "𝐝", "е": "𝐞", "ё": "𝐞",
    "ж": "𝐳𝐡", "з": "𝐳", "и": "𝐢", "й": "𝐲", "к": "𝐤", "л": "𝐥", "м": "𝐦",
    "н": "𝐧", "о": "𝐨", "п": "𝐩", "р": "𝐫", "с": "𝐬", "т": "𝐭", "у": "𝐮",
    "ф": "𝐟", "х": "𝐡", "ц": "𝐭𝐬", "ч": "𝐜𝐡", "ш": "𝐬𝐡", "щ": "𝐬𝐜𝐡",
    "ы": "𝐲", "э": "𝐞", "ю": "𝐲𝐮", "я": "𝐲𝐚",
}

_CYR_GOTHIC: dict[str, str] = {
    "а": "𝔞", "б": "𝔟", "в": "𝔳", "г": "𝔤", "д": "𝔡", "е": "𝔢", "ё": "𝔢",
    "ж": "𝔷𝔥", "з": "𝔷", "и": "𝔦", "й": "𝔶", "к": "𝔨", "л": "𝔩", "м": "𝔪",
    "н": "𝔫", "о": "𝔬", "п": "𝔭", "р": "𝔯", "с": "𝔰", "т": "𝔱", "у": "𝔲",
    "ф": "𝔣", "х": "𝔥", "ц": "𝔱𝔰", "ч": "𝔠𝔥", "ш": "𝔰𝔥", "щ": "𝔰𝔠𝔥",
    "ы": "𝔶", "э": "𝔢", "ю": "𝔶𝔲", "я": "𝔶𝔞",
}

_CYR_ROUND: dict[str, str] = {
    "а": "ⓐ", "б": "ⓑ", "в": "ⓥ", "г": "ⓖ", "д": "ⓓ", "е": "ⓔ", "ё": "ⓔ",
    "ж": "ⓩⓗ", "з": "ⓩ", "и": "ⓘ", "й": "ⓨ", "к": "ⓚ", "л": "ⓛ", "м": "ⓜ",
    "н": "ⓝ", "о": "ⓞ", "п": "ⓟ", "р": "ⓡ", "с": "ⓢ", "т": "ⓣ", "у": "ⓤ",
    "ф": "ⓕ", "х": "ⓗ", "ц": "ⓣⓢ", "ч": "ⓒⓗ", "ш": "ⓢⓗ", "щ": "ⓢⓒⓗ",
    "ы": "ⓨ", "э": "ⓔ", "ю": "ⓨⓤ", "я": "ⓨⓐ",
}

_CYR_SCRIPT: dict[str, str] = {
    "а": "𝒶", "б": "𝒷", "в": "𝓋", "г": "𝑔", "д": "𝒹", "е": "𝑒", "ё": "𝑒",
    "ж": "𝓏𝒽", "з": "𝓏", "и": "𝒾", "й": "𝓎", "к": "𝓀", "л": "𝓁", "м": "𝓂",
    "н": "𝓃", "о": "𝑜", "п": "𝓅", "р": "𝓇", "с": "𝓈", "т": "𝓉", "у": "𝓊",
    "ф": "𝒻", "х": "𝒽", "ц": "𝓉𝓈", "ч": "𝒸𝒽", "ш": "𝓈𝒽", "щ": "𝓈𝒸𝒽",
    "ы": "𝓎", "э": "𝑒", "ю": "𝓎𝓊", "я": "𝓎𝒶",
}

_CYR_FAIRY: dict[str, str] = {
    "а": "α", "б": "♭", "в": "✓", "г": "Γ", "д": "∂", "е": "ε", "ё": "ё",
    "ж": "ж", "з": "з", "и": "ι", "й": "й", "к": "κ", "л": "λ", "м": "μ",
    "н": "η", "о": "σ", "п": "π", "р": "ρ", "с": "ς", "т": "τ", "у": "υ",
    "ф": "φ", "х": "χ", "ц": "ц", "ч": "ч", "ш": "ш", "щ": "щ", "ъ": "ъ",
    "ы": "ы", "ь": "ь", "э": "э", "ю": "ю", "я": "я",
}

_CYR_DARK: dict[str, str] = {
    "а": "🅰", "б": "🅱", "в": "🆅", "г": "🅶", "д": "🅳", "е": "🅴", "ё": "🅴",
    "ж": "🆉🅷", "з": "🆉", "и": "🅸", "й": "🆈", "к": "🅺", "л": "🅻", "м": "🅼",
    "н": "🅽", "о": "🅾", "п": "🅿", "р": "🆁", "с": "🆂", "т": "🆃", "у": "🆄",
    "ф": "🅵", "х": "🅷", "ц": "🆃🆂", "ч": "🅲🅷", "ш": "🆂🅷", "щ": "🆂🅲🅷",
    "ы": "🆈", "э": "🅴", "ю": "🆈🆄", "я": "🆈🅰",
}

_CYR_CUTE: dict[str, str] = {
    "а": "🄰", "б": "🄱", "в": "🅅", "г": "🄶", "д": "🄳", "е": "🄴", "ё": "🄴",
    "ж": "🅉🄷", "з": "🅉", "и": "🄸", "й": "🅈", "к": "🄺", "л": "🄻", "м": "🄼",
    "н": "🄽", "о": "🄾", "п": "🄿", "р": "🅁", "с": "🅂", "т": "🅃", "у": "🅄",
    "ф": "🄵", "х": "🄷", "ц": "🅃🅂", "ч": "🄲🄷", "ш": "🅂🄷", "щ": "🅂🄲🄷",
    "ы": "🅈", "э": "🄴", "ю": "🅈🅄", "я": "🅈🄰",
}

_CYR_OLD: dict[str, str] = {
    "а": "а̃", "б": "б̃", "в": "в̃", "г": "г̃", "д": "д̃", "е": "е̃", "ё": "ё̃",
    "ж": "ж̃", "з": "з̃", "и": "и̃", "й": "й̃", "к": "к̃", "л": "л̃", "м": "м̃",
    "н": "н̃", "о": "о̃", "п": "п̃", "р": "р̃", "с": "с̃", "т": "т̃", "у": "у̃",
    "ф": "ф̃", "х": "х̃", "ц": "ц̃", "ч": "ч̃", "ш": "ш̃", "щ": "щ̃", "ъ": "ъ̃",
    "ы": "ы̃", "ь": "ь̃", "э": "э̃", "ю": "ю̃", "я": "я̃",
}

_CYR_MODERN: dict[str, str] = {
    "а": "ᴀ", "б": "ʙ", "в": "ᴠ", "г": "ɢ", "д": "ᴅ", "е": "ᴇ", "ё": "ᴇ",
    "ж": "ᴊ", "з": "ᴢ", "и": "ɪ", "й": "ʏ", "к": "ᴋ", "л": "ʟ", "м": "ᴍ",
    "н": "ɴ", "о": "ᴏ", "п": "ᴘ", "р": "ʀ", "с": "ꜱ", "т": "ᴛ", "у": "ᴜ",
    "ф": "ꜰ", "х": "ʜ", "ц": "ᴄ", "ч": "ᴄʜ", "ш": "ꜱʜ", "щ": "ꜱᴄʜ",
    "ы": "ʏ", "э": "ᴇ", "ю": "ʏᴜ", "я": "ʏᴀ",
}

_CYR_LINE: dict[str, str] = {
    "а": "а̲", "б": "б̲", "в": "в̲", "г": "г̲", "д": "д̲", "е": "е̲", "ё": "ё̲",
    "ж": "ж̲", "з": "з̲", "и": "и̲", "й": "й̲", "к": "к̲", "л": "л̲", "м": "м̲",
    "н": "н̲", "о": "о̲", "п": "п̲", "р": "р̲", "с": "с̲", "т": "т̲", "у": "у̲",
    "ф": "ф̲", "х": "х̲", "ц": "ц̲", "ч": "ч̲", "ш": "ш̲", "щ": "щ̲", "ъ": "ъ̲",
    "ы": "ы̲", "ь": "ь̲", "э": "э̲", "ю": "ю̲", "я": "я̲",
}

_CYR_STAR: dict[str, str] = {
    "а": "★а★", "б": "★б★", "в": "★в★", "г": "★г★", "д": "★д★", "е": "★е★",
    "ё": "★ё★", "ж": "★ж★", "з": "★з★", "и": "★и★", "й": "★й★", "к": "★к★",
    "л": "★л★", "м": "★м★", "н": "★н★", "о": "★о★", "п": "★п★", "р": "★р★",
    "с": "★с★", "т": "★т★", "у": "★у★", "ф": "★ф★", "х": "★х★", "ц": "★ц★",
    "ч": "★ч★", "ш": "★ш★", "щ": "★щ★", "ъ": "★ъ★", "ы": "★ы★", "ь": "★ь★",
    "э": "★э★", "ю": "★ю★", "я": "★я★",
}

_CYRILLIC_MAPS: dict[str, dict[str, str]] = {
    "cyr_elegant": _CYR_ELEGANT,
    "cyr_bold": _CYR_BOLD,
    "cyr_gothic": _CYR_GOTHIC,
    "cyr_round": _CYR_ROUND,
    "cyr_script": _CYR_SCRIPT,
    "cyr_fairy": _CYR_FAIRY,
    "cyr_dark": _CYR_DARK,
    "cyr_cute": _CYR_CUTE,
    "cyr_old": _CYR_OLD,
    "cyr_modern": _CYR_MODERN,
    "cyr_line": _CYR_LINE,
    "cyr_star": _CYR_STAR,
}

_LATIN_MAPS: dict[str, dict[str, str]] = {
    "lat_greek": _LAT_GREEK,
    "lat_currency": _LAT_CURRENCY,
    "lat_symbols": _LAT_SYMBOLS,
    "lat_medieval": _LAT_MEDIEVAL,
    "lat_tech": _LAT_TECH,
    "lat_cute": _LAT_CUTE,
    "lat_hacker": _LAT_HACKER,
    "lat_royal": _LAT_ROYAL,
    "lat_bubble": _LAT_BUBBLE,
    "lat_stylish": _LAT_STYLISH,
    "lat_minimal": _LAT_MINIMAL,
    "lat_graffiti": _LAT_GRAFFITI,
}


def transliterate(text: str) -> str:
    result: list[str] = []
    for char in text:
        lower = char.lower()
        if lower not in _CYR_TO_LAT:
            result.append(char)
            continue
        latin = _CYR_TO_LAT[lower]
        if not latin:
            continue
        if char.isupper():
            latin = latin[0].upper() + latin[1:] if len(latin) > 1 else latin.upper()
        result.append(latin)
    return "".join(result)


def has_cyrillic(text: str) -> bool:
    return any("\u0400" <= char <= "\u04FF" for char in text)


def _map_range(text: str, upper_start: int, lower_start: int, digit_start: int | None = None) -> str:
    result: list[str] = []
    for char in text:
        code = ord(char)
        if 65 <= code <= 90:
            result.append(chr(upper_start + code - 65))
        elif 97 <= code <= 122:
            result.append(chr(lower_start + code - 97))
        elif digit_start is not None and 48 <= code <= 57:
            result.append(chr(digit_start + code - 48))
        else:
            result.append(char)
    return "".join(result)


def _map_dict(text: str, mapping: dict[str, str]) -> str:
    return "".join(mapping.get(char, char) for char in text)


def _map_dict_translit(text: str, mapping: dict[str, str]) -> str:
    return _map_dict(transliterate(text), mapping)


def _script(text: str, bold: bool = False) -> str:
    special = _BOLD_SCRIPT_UPPER if bold else _SCRIPT_UPPER
    upper_start = 0x1D4D0 if bold else 0x1D49C
    lower_start = 0x1D4EA if bold else 0x1D4B6
    result: list[str] = []
    for char in text:
        if char in special:
            result.append(special[char])
        elif "A" <= char <= "Z":
            result.append(chr(upper_start + ord(char) - 65))
        elif "a" <= char <= "z":
            result.append(chr(lower_start + ord(char) - 97))
        else:
            result.append(char)
    return "".join(result)


def _fraktur(text: str, bold: bool = False) -> str:
    special = _BOLD_FRAKTUR_UPPER if bold else _FRAKTUR_UPPER
    upper_start = 0x1D56C if bold else 0x1D504
    lower_start = 0x1D586 if bold else 0x1D51E
    result: list[str] = []
    for char in text:
        if char in special:
            result.append(special[char])
        elif "A" <= char <= "Z":
            result.append(chr(upper_start + ord(char) - 65))
        elif "a" <= char <= "z":
            result.append(chr(lower_start + ord(char) - 97))
        else:
            result.append(char)
    return "".join(result)


def _double(text: str) -> str:
    result: list[str] = []
    for char in text:
        if char in _DOUBLE_UPPER:
            result.append(_DOUBLE_UPPER[char])
        elif "A" <= char <= "Z":
            result.append(chr(0x1D538 + ord(char) - 65))
        elif "a" <= char <= "z":
            result.append(chr(0x1D552 + ord(char) - 97))
        elif "0" <= char <= "9":
            result.append(chr(0x1D7D8 + ord(char) - 48))
        else:
            result.append(char)
    return "".join(result)


def _circled(text: str) -> str:
    result: list[str] = []
    for char in text:
        if "A" <= char <= "Z":
            result.append(chr(0x24B6 + ord(char) - 65))
        elif "a" <= char <= "z":
            result.append(chr(0x24D0 + ord(char) - 97))
        elif "0" <= char <= "9":
            result.append("⓪" if char == "0" else chr(0x24EA + ord(char) - 48))
        else:
            result.append(char)
    return "".join(result)


def _circled_neg(text: str) -> str:
    result: list[str] = []
    for char in text:
        if "A" <= char <= "Z":
            result.append(chr(0x1F150 + ord(char) - 65))
        elif "a" <= char <= "z":
            result.append(chr(0x1F170 + ord(char) - 97))
        elif "0" <= char <= "9":
            result.append(chr(0x1F101 + ord(char) - 48) if char != "0" else "⓿")
        else:
            result.append(char)
    return "".join(result)


def _squared(text: str) -> str:
    return "".join(chr(0x1F130 + ord(char) - 65) if "A" <= char <= "Z" else char for char in text)


def _parenthesized(text: str) -> str:
    result: list[str] = []
    for char in text:
        if "a" <= char <= "z":
            result.append(chr(0x249C + ord(char) - 97))
        elif "A" <= char <= "Z":
            result.append(chr(0x1F110 + ord(char) - 65))
        elif "1" <= char <= "9":
            result.append(chr(0x2474 + ord(char) - 49))
        elif char == "0":
            result.append("⓪")
        else:
            result.append(char)
    return "".join(result)


def _fullwidth(text: str) -> str:
    result: list[str] = []
    for char in text:
        if "A" <= char <= "Z":
            result.append(chr(0xFF21 + ord(char) - 65))
        elif "a" <= char <= "z":
            result.append(chr(0xFF41 + ord(char) - 97))
        elif "0" <= char <= "9":
            result.append(chr(0xFF10 + ord(char) - 48))
        elif char == " ":
            result.append("\u3000")
        else:
            result.append(char)
    return "".join(result)


def _regional(text: str) -> str:
    result: list[str] = []
    for char in text:
        if "A" <= char <= "Z":
            result.append(chr(0x1F1E6 + ord(char) - 65))
        elif "a" <= char <= "z":
            result.append(chr(0x1F1E6 + ord(char) - 97))
        else:
            result.append(char)
    return "".join(result)


def _keycap(text: str) -> str:
    result: list[str] = []
    for char in text:
        if "0" <= char <= "9":
            result.append(f"{char}\u20e3")
        elif "A" <= char <= "Z":
            result.append(chr(0x1F170 + ord(char) - 65))
        elif "a" <= char <= "z":
            result.append(chr(0x1F170 + ord(char) - 97))
        else:
            result.append(char)
    return "".join(result)


def _combining(text: str, mark: str) -> str:
    return "".join(f"{char}{mark}" if char.strip() else char for char in text)


def _upside_down(text: str) -> str:
    mapped = [_UPSIDE_DOWN.get(char, char) for char in text]
    return "".join(reversed(mapped))


def _mirror(text: str) -> str:
    return text[::-1]


def _spaced(text: str) -> str:
    return " ".join(text)


def _vaporwave(text: str) -> str:
    converted = _fullwidth(transliterate(text))
    return " ".join(converted)


def _alternating(text: str) -> str:
    result: list[str] = []
    upper = True
    for char in text:
        if char.isalpha():
            result.append(char.upper() if upper else char.lower())
            upper = not upper
        else:
            result.append(char)
    return "".join(result)


def _wrap(text: str, left: str, right: str) -> str:
    return f"{left}{text}{right}"


def _between(text: str, sep: str) -> str:
    chars = [char for char in text if char.strip()]
    if not chars:
        return text
    return sep.join(chars)


def _cyrillic(text: str, style_id: str) -> str:
    mapping = _CYRILLIC_MAPS[style_id]
    result: list[str] = []
    for char in text:
        if char in mapping:
            result.append(mapping[char])
        elif char.lower() in mapping:
            mapped = mapping[char.lower()]
            result.append(mapped)
        elif char.lower() in _CYR_TO_LAT:
            lat = transliterate(char)
            result.append(mapping.get(lat.lower(), lat))
        else:
            result.append(char)
    return "".join(result)


def _apply_translit(fn: Callable[[str], str]) -> Callable[[str], str]:
    def wrapper(text: str) -> str:
        return fn(transliterate(text))
    return wrapper


_CONVERTERS: dict[str, Callable[[str], str]] = {
    "bold": _apply_translit(lambda t: _map_range(t, 0x1D400, 0x1D41A, 0x1D7CE)),
    "italic": _apply_translit(lambda t: _map_range(t, 0x1D434, 0x1D44E, 0x1D7E2)),
    "bold_italic": _apply_translit(lambda t: _map_range(t, 0x1D468, 0x1D482, 0x1D7EC)),
    "script": _apply_translit(lambda t: _script(t, bold=False)),
    "bold_script": _apply_translit(lambda t: _script(t, bold=True)),
    "fraktur": _apply_translit(lambda t: _fraktur(t, bold=False)),
    "bold_fraktur": _apply_translit(lambda t: _fraktur(t, bold=True)),
    "double": _apply_translit(_double),
    "sans": _apply_translit(lambda t: _map_range(t, 0x1D5A0, 0x1D5BA, 0x1D7E2)),
    "sans_bold": _apply_translit(lambda t: _map_range(t, 0x1D5D4, 0x1D5EE, 0x1D7EC)),
    "sans_italic": _apply_translit(lambda t: _map_range(t, 0x1D608, 0x1D622)),
    "sans_bold_italic": _apply_translit(lambda t: _map_range(t, 0x1D63C, 0x1D656)),
    "mono": _apply_translit(lambda t: _map_range(t, 0x1D670, 0x1D68A, 0x1D7F6)),
    "small_caps": _apply_translit(lambda t: _map_dict(t, _SMALL_CAPS)),
    "circled": _apply_translit(_circled),
    "circled_neg": _apply_translit(_circled_neg),
    "squared": _apply_translit(_squared),
    "parenthesized": _apply_translit(_parenthesized),
    "fullwidth": _apply_translit(_fullwidth),
    "regional": _apply_translit(_regional),
    "keycap": _apply_translit(_keycap),
    "subscript": _apply_translit(lambda t: _map_dict(t.lower(), _SUBSCRIPT)),
    "superscript": _apply_translit(lambda t: _map_dict(t, _SUPERSCRIPT)),
    "underline": lambda t: _combining(t, "\u0332"),
    "double_underline": lambda t: _combining(t, "\u0333"),
    "overline": lambda t: _combining(t, "\u0305"),
    "strikethrough": lambda t: _combining(t, "\u0336"),
    "dot_above": lambda t: _combining(t, "\u0307"),
    "tilde_above": lambda t: _combining(t, "\u0303"),
    "upside_down": _upside_down,
    "mirror": _mirror,
    "spaced": _spaced,
    "vaporwave": _vaporwave,
    "alternating": _alternating,
    "brackets_square": lambda t: _wrap(t, "【", "】"),
    "brackets_angle": lambda t: _wrap(t, "《", "》"),
    "brackets_flower": lambda t: _wrap(t, "❰", "❱"),
    "stars": lambda t: _between(t, "★"),
    "dots": lambda t: _between(t, "·"),
    "hearts": lambda t: _between(t, "♥"),
    "fire": lambda t: _between(t, "🔥"),
    "sparkle": lambda t: _between(t, "✨"),
    "wave": lambda t: _between(t, "〜"),
}

for _style_id, _mapping in _LATIN_MAPS.items():
    _CONVERTERS[_style_id] = lambda t, m=_mapping: _map_dict_translit(t, m)

for _style_id in _CYRILLIC_MAPS:
    _CONVERTERS[_style_id] = lambda t, sid=_style_id: _cyrillic(t, sid)


def convert(text: str, style_id: str) -> str:
    converter = _CONVERTERS.get(style_id)
    if converter is None:
        raise ValueError(f"Unknown style: {style_id}")
    return converter(text)


def convert_all(text: str) -> list[tuple[FontStyle, str]]:
    return [(style, convert(text, style.id)) for style in FONT_STYLES]


def get_style(style_id: str) -> FontStyle | None:
    return next((s for s in FONT_STYLES if s.id == style_id), None)


def get_category(category_id: str) -> FontCategory | None:
    return next((c for c in FONT_CATEGORIES if c.id == category_id), None)


def get_styles_by_category(category_id: str) -> tuple[FontStyle, ...]:
    return tuple(s for s in FONT_STYLES if s.category == category_id)


def get_styles_page(category_id: str, page: int) -> tuple[FontStyle, ...]:
    styles = get_styles_by_category(category_id)
    start = page * FONTS_PER_PAGE
    return styles[start : start + FONTS_PER_PAGE]


def get_pages_count(category_id: str) -> int:
    total = len(get_styles_by_category(category_id))
    return max(1, (total + FONTS_PER_PAGE - 1) // FONTS_PER_PAGE)
