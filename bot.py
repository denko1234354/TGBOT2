import asyncio
import logging
import os
import random
import sys

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject
from dotenv import load_dotenv

from plates import (
    Plate,
    evaluate_plate,
    format_evaluation,
    generate_plate,
    parse_plate_text,
    plate_from_storage_key,
    plate_storage_key,
    rarity_badge,
)
from admin_panel import admin_router, init_admin_panel, is_admin
from game_config import global_spin_cost, init_game_config
from proxy import resolve_bot_session
from regions import (
    REGIONAL_GUARANTEE_MULTIPLIER,
    UNIQUE_REGIONS,
    get_region,
    region_multiplier,
    spin_cost_for_region,
)
from leaderboard import format_leaderboard
from storage import UserStorage
from vault import (
    MAX_COLLECTION_LEVEL,
    MAX_SAFE_LEVEL,
    collection_total_value,
    collection_upgrade_price,
    format_plate_short,
    safe_capacity,
    safe_upgrade_price,
    sorted_stored,
    vault_summary,
)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, ".env"), override=True)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

router = Router()
storage = UserStorage(_BASE_DIR)

REGIONS_PER_PAGE = 8
VAULT_PAGE_SIZE = 4
COLLECTION_PAGE_SIZE = 3
REGION_ALL = "all"


class FeedbackStates(StatesGroup):
    waiting_text = State()


class PromoStates(StatesGroup):
    waiting_code = State()


def plate_to_key(plate: Plate) -> str:
    return plate_storage_key(plate)


def plate_from_key(key: str) -> Plate | None:
    return plate_from_storage_key(key)


def plate_key_token(key: str) -> str:
    return key.replace(":", "~")


def plate_key_from_token(token: str) -> str | None:
    key = token.replace("~", ":")
    return key if plate_from_key(key) is not None else None


def is_all_regions(code: str | None) -> bool:
    return not code or code in (REGION_ALL, "global", "*")


def current_spin_cost(code: str | None) -> int:
    if is_all_regions(code):
        return global_spin_cost()
    return spin_cost_for_region(code or REGION_ALL)


def region_choice_label(code: str | None) -> str:
    if is_all_regions(code):
        return "🌍 Все регионы"
    region = get_region(code or "")
    if region is None:
        return "🌍 Все регионы"
    return region.name


def main_menu_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🎰 Крутить", callback_data="menu:spin")],
        [
            InlineKeyboardButton(text="💰 Баланс", callback_data="menu:balance"),
        ],
        [
            InlineKeyboardButton(text="🔐 Сейф", callback_data="vlt:safe:0"),
            InlineKeyboardButton(text="📚 Коллекция", callback_data="vlt:col:0"),
        ],
        [InlineKeyboardButton(text="⬆️ Улучшения сейфа и коллекции", callback_data="menu:vault")],
        [
            InlineKeyboardButton(text="📖 Правила", callback_data="menu:rules"),
            InlineKeyboardButton(text="🏆 Лидеры", callback_data="menu:leaderboard"),
        ],
        [InlineKeyboardButton(text="🔍 Оценить", callback_data="menu:rate_hint")],
        [InlineKeyboardButton(text="🎟 Промокод", callback_data="menu:promo")],
        [InlineKeyboardButton(text="📨 Отзыв / предложение", callback_data="menu:feedback")],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(text="🛠 Админка", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def region_list_keyboard(page: int) -> InlineKeyboardMarkup:
    start = page * REGIONS_PER_PAGE
    chunk = UNIQUE_REGIONS[start : start + REGIONS_PER_PAGE]
    rows: list[list[InlineKeyboardButton]] = []
    if page == 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🌍 Все регионы ({global_spin_cost()} ₽)",
                    callback_data=f"pick:{REGION_ALL}",
                )
            ]
        )
    for region in chunk:
        multiplier = region_multiplier(region.code)
        region_label = f"{region.name} · ×{multiplier:.2f}"
        if len(region_label) > 64:
            region_label = f"{region.name[:55].rstrip()}… · ×{multiplier:.2f}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=region_label,
                    callback_data=f"pick:{region.code}",
                ),
                InlineKeyboardButton(
                    text="Коды: " + " ".join(region.registration_codes),
                    callback_data=f"pick:{region.code}",
                ),
            ]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"rpage:{page - 1}"))
    max_page = (len(UNIQUE_REGIONS) - 1) // REGIONS_PER_PAGE
    if page < max_page:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"rpage:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ К прокруту", callback_data="menu:spin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def spin_actions_keyboard(region_code: str) -> InlineKeyboardMarkup:
    cost = current_spin_cost(region_code)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🎲 Крутить ({cost} ₽)", callback_data="spin:now")],
            [
                InlineKeyboardButton(text="🗺 Выбрать регион", callback_data="menu:region"),
                InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:home"),
            ],
        ]
    )


def after_spin_keyboard(plate_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔐 В сейф", callback_data="vlt:store"),
                InlineKeyboardButton(text="💵 Продать", callback_data=f"sell:{plate_key}"),
            ],
            [
                InlineKeyboardButton(text="🎰 Крутить ещё раз", callback_data="spin:repeat"),
                InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:home"),
            ],
        ]
    )


def upgrades_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬆️ Улучшить сейф", callback_data="vlt:upsafe"),
                InlineKeyboardButton(text="⬆️ Улучшить коллекцию", callback_data="vlt:upcol"),
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
        ]
    )


def _paginate_nav(prefix: str, page: int, total_pages: int) -> list[InlineKeyboardButton]:
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page + 1}"))
    return nav


async def sync_profile(user_id: int, username: str | None, full_name: str) -> None:
    display = f"@{username}" if username else full_name
    user = await storage.get(user_id)
    if user.display_name != display:
        await storage.update(user_id, display_name=display)
        await storage.save()


class ProfileMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user is not None:
            await sync_profile(user.id, user.username, user.full_name)
        return await handler(event, data)


async def apply_spin_progress(user_id: int, plate_key: str, sell_price: int, rarity_id: str) -> None:
    user = await storage.get(user_id)
    patch: dict[str, object] = {}
    if sell_price > user.best_plate_price:
        patch["best_plate_key"] = plate_key
        patch["best_plate_price"] = sell_price
    storage.try_add_collection(user, plate_key)
    patch["collection_items"] = user.collection_items
    await storage.update(user_id, **patch)


async def build_upgrades_text(user_id: int) -> str:
    user = await storage.get(user_id)
    visible = storage.visible_collection(user)
    coll_value = collection_total_value(visible, user.collection_level)
    s_up = safe_upgrade_price(user.safe_level)
    c_up = collection_upgrade_price(user.collection_level)
    up_lines = []
    if s_up is not None:
        up_lines.append(f"⬆️ Сейф → ур. {user.safe_level + 1}: <b>{s_up}</b> ₽")
    if c_up is not None:
        up_lines.append(f"⬆️ Коллекция → ур. {user.collection_level + 1}: <b>{c_up}</b> ₽")
    upgrades = "\n".join(up_lines) if up_lines else "Все улучшения куплены."
    return (
        "⬆️ <b>Улучшения сейфа и коллекции</b>\n\n"
        f"{vault_summary(user.safe_level, user.collection_level, len(user.safe_items), len(visible))}\n"
        f"💎 Ценность коллекции: <b>{coll_value:,}</b> ₽\n\n{upgrades}".replace(",", " ")
    )


async def profile_line(user_id: int) -> str:
    user = await storage.get(user_id)
    return (
        f"💳 Баланс: <b>{user.balance}</b> ₽\n"
        f"🗺 Регион прокрута: <b>{region_choice_label(user.selected_region)}</b>\n"
        f"🎲 Всего прокрутов: <b>{user.spins}</b>"
    )


WELCOME = (
    "🇷🇺 <b>Генератор госномеров РФ</b>\n\n"
    "Крути рулетку, лови крутые комбо на цифрах и буквах, продавай номера и копи баланс.\n\n"
    "• <b>Крутить</b> — по умолчанию все регионы РФ, можно выбрать конкретный код.\n"
    "• Цена регионального прокрута = базовая пошлина × множитель региона × гарантия региона (×1,50).\n"
    "• Множитель региона влияет и на стоимость номера.\n"
    "• Цена номера учитывает регион, тип номера и комбинации цифр/букв.\n"
    "• В рулетке редко выпадают <b>спецномера</b> госорганов.\n"
)


RULES = (
    "📖 <b>Правила</b>\n\n"
    "Гражданский: <code>А 123 ВС 77</code>\n"
    "Дипломат: <code>дип D 123 CD 77</code>\n"
    "Военный: <code>воен 1234 АА 77</code>\n"
    "МВД / ФСО / МЧС: <code>мвд А 001 АА 77</code> (префикс типа + номер)\n\n"
    "<b>Тип номера</b> (сильно влияет на цену):\n"
    "🟥 дипломат ×14, 🛡 ФСО ×11, 🪖 военный ×9, 🚔 МВД ×7,\n"
    "⚖️ прокуратура ×6.5, 🚒 МЧС ×5.5, 🚛 транзит ×1.35, 🚕 такси ×0.72\n\n"
    "<b>Комбо</b> (перемножаются): 777, 007, последовательности, зеркала,\n"
    "🔤 две/три буквы, 🌀 палиндром, 🕷 блатные серии <code>АУЕ</code> / <code>ВОР</code> / <code>ХУЕ</code>,\n"
    "🏛 малые гос. номера (001–020) и др.\n\n"
    "Премиум-коды (77, 99, 78…) повышают базу при продаже.\n\n"
    "<b>Редкость</b> (рядом с номером):\n"
    "⚪ Обычные · 🟢 Необычные · 🟣 Эпические · 🟡 Легендарные\n\n"
    "<b>Сейф</b> — спрячь дорогой номер, чтобы не продать его с экрана прокрута.\n"
    "<b>Коллекция</b> — альбом всех выпавших номеров. То, что в сейфе, там не показывается.\n"
    "Улучшения расширяют места и дают бонус к ценности коллекции.\n\n"
    "Оценка: <code>/rate фсо А 007 АА 77</code>"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return
    u = message.from_user
    await sync_profile(u.id, u.username, u.full_name)
    text = WELCOME + "\n" + await profile_line(u.id)
    await message.answer(text, reply_markup=main_menu_keyboard(u.id))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    uid = message.from_user.id if message.from_user else None
    await message.answer(RULES, reply_markup=main_menu_keyboard(uid))


@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    if not message.from_user:
        return
    await message.answer(await profile_line(message.from_user.id))


@router.message(Command("promo"))
async def cmd_promo(message: Message) -> None:
    if not message.from_user:
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: <code>/promo КОД</code>")
        return
    status, reward, balance = await storage.redeem_promo(message.from_user.id, args[1])
    await _send_promo_result(message, status, reward, balance)


@router.callback_query(F.data == "menu:promo")
async def cb_promo_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.set_state(PromoStates.waiting_code)
    await callback.answer()
    await callback.message.edit_text(
        "🎟 Введите промокод одним сообщением:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="promo:cancel")]]
        ),
    )


@router.callback_query(F.data == "promo:cancel")
async def cb_promo_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await callback.answer("Отменено")
    await callback.message.edit_text(
        WELCOME + "\n" + await profile_line(callback.from_user.id),
        reply_markup=main_menu_keyboard(callback.from_user.id),
    )


async def _send_promo_result(message: Message, status: str, reward: int, balance: int) -> None:
    texts = {
        "not_found": "❌ Такой промокод не найден.",
        "inactive": "❌ Этот промокод отключён.",
        "used": "ℹ️ Вы уже активировали этот промокод.",
        "exhausted": "ℹ️ Лимит активаций промокода исчерпан.",
        "success": f"✅ Промокод активирован! Начислено <b>{reward}</b> ₽. Баланс: <b>{balance}</b> ₽.",
    }
    await message.answer(
        texts.get(status, "Не удалось активировать промокод."),
        reply_markup=main_menu_keyboard(message.from_user.id if message.from_user else None),
    )


@router.message(PromoStates.waiting_code, F.text)
async def msg_promo_redeem(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    status, reward, balance = await storage.redeem_promo(message.from_user.id, message.text or "")
    await state.clear()
    await _send_promo_result(message, status, reward, balance)


@router.callback_query(F.data == "menu:feedback")
async def cb_feedback_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await state.set_state(FeedbackStates.waiting_text)
    await callback.answer()
    await callback.message.edit_text(
        "📨 Напишите одним сообщением отзыв или предложение (до 2000 символов).\n"
        "Его сможет прочитать только администратор.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="feedback:cancel")]]
        ),
    )


@router.callback_query(F.data == "feedback:cancel")
async def cb_feedback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await callback.answer("Отменено")
    text = WELCOME + "\n" + await profile_line(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard(callback.from_user.id))


@router.message(FeedbackStates.waiting_text, F.text)
async def msg_feedback_submit(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    body = (message.text or "").strip()
    if not body:
        await message.answer("Сообщение пустое. Напишите отзыв или предложение.")
        return
    if len(body) > 2000:
        await message.answer("Слишком длинное сообщение. Максимум — 2000 символов.")
        return
    user = await storage.get(message.from_user.id)
    await storage.add_feedback(message.from_user.id, user.display_name or message.from_user.full_name, body)
    await state.clear()
    await message.answer(
        "✅ Спасибо! Отзыв отправлен администратору.",
        reply_markup=main_menu_keyboard(message.from_user.id),
    )


@router.message(Command("rate"))
async def cmd_rate(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Примеры:\n"
            "<code>/rate А 777 АА 77</code>\n"
            "<code>/rate дип D 007 CD 77</code>\n"
            "<code>/rate мвд А 001 АА 77</code>"
        )
        return
    plate = parse_plate_text(args[1].replace(" ", " "))
    if plate is None:
        plate = parse_plate_text(args[1])
    if plate is None:
        await message.answer("Не удалось разобрать номер. Формат: А 123 ВС 77")
        return
    await message.answer(format_evaluation(evaluate_plate(plate)))


@router.callback_query(F.data == "menu:leaderboard")
async def cb_leaderboard(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    rows = await storage.leaderboard(10)
    await callback.answer()
    await callback.message.edit_text(
        format_leaderboard(rows),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:home")]]
        ),
    )


@router.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await callback.answer()
    text = WELCOME + "\n" + await profile_line(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard(callback.from_user.id))


@router.callback_query(F.data == "menu:balance")
async def cb_balance(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await callback.answer()
    await callback.message.edit_text(
        await profile_line(callback.from_user.id),
        reply_markup=main_menu_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "menu:rules")
async def cb_rules(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    await callback.answer()
    uid = callback.from_user.id if callback.from_user else None
    await callback.message.edit_text(RULES, reply_markup=main_menu_keyboard(uid))


@router.callback_query(F.data == "menu:vault")
async def cb_vault_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    await callback.answer()
    await callback.message.edit_text(
        await build_upgrades_text(callback.from_user.id),
        reply_markup=upgrades_keyboard(),
    )


@router.callback_query(F.data == "vlt:store")
async def cb_vault_store(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    user = await storage.get(callback.from_user.id)
    key = user.last_plate_key
    if not key:
        await callback.answer("Нет номера для сохранения", show_alert=True)
        return
    if key in user.safe_items:
        await callback.answer("Уже в сейфе", show_alert=True)
        return
    if not storage.try_add_safe(user, key):
        await callback.answer("Сейф полон — улучшите его", show_alert=True)
        return
    await storage.update(
        callback.from_user.id,
        last_plate_key=None,
        safe_items=user.safe_items,
        collection_items=user.collection_items,
    )
    await storage.save()
    await callback.answer("Сохранено в сейфе 🔐")
    await callback.message.edit_text(
        f"🔐 Номер убран в сейф:\n{format_plate_short(key)}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎰 Крутить ещё раз", callback_data="spin:repeat")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")],
            ]
        ),
    )


async def _show_safe_list(callback: CallbackQuery, page: int, *, answer: bool = True) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        if answer:
            await callback.answer()
        return
    user = await storage.get(callback.from_user.id)
    items = sorted_stored(user.safe_items)
    total_pages = max(1, (len(items) + VAULT_PAGE_SIZE - 1) // VAULT_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * VAULT_PAGE_SIZE : (page + 1) * VAULT_PAGE_SIZE]

    lines = [
        f"🔐 <b>Сейф</b> ({len(items)}/{safe_capacity(user.safe_level)})",
        "",
    ]
    if not items:
        lines.append("Пусто. После прокрута нажми «В сейф».")
    else:
        for idx, item in enumerate(chunk):
            global_idx = page * VAULT_PAGE_SIZE + idx
            lines.append(f"{global_idx + 1}. {format_plate_short(item.key, item.price)}")

    rows: list[list[InlineKeyboardButton]] = []
    for idx, item in enumerate(chunk):
        global_idx = page * VAULT_PAGE_SIZE + idx
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"💵 Продать #{global_idx + 1}",
                    callback_data=f"vlt:sellask:{plate_key_token(item.key)}",
                ),
                InlineKeyboardButton(
                    text=f"📚 В коллекцию #{global_idx + 1}",
                    callback_data=f"vlt:stocol:{plate_key_token(item.key)}:{page}",
                ),
            ]
        )
    nav = _paginate_nav("vlt:safe", page, total_pages)
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:home")])

    if answer:
        await callback.answer()
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("vlt:safe:"))
async def cb_vault_safe_list(callback: CallbackQuery) -> None:
    if not callback.data:
        await callback.answer()
        return
    page = int(callback.data.split(":")[2])
    await _show_safe_list(callback, page)


@router.callback_query(F.data.startswith("vlt:stocol:"))
async def cb_safe_to_collection(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Не удалось найти номер", show_alert=True)
        return
    key = plate_key_from_token(parts[2])
    if key is None:
        await callback.answer("Не удалось найти номер", show_alert=True)
        return
    try:
        page = int(parts[3])
    except ValueError:
        page = 0

    result = await storage.move_safe_to_collection(callback.from_user.id, key)
    if result == "full":
        await callback.answer("Коллекция заполнена — сначала улучшите её", show_alert=True)
        return
    if result != "moved":
        await callback.answer("Номер уже не находится в сейфе", show_alert=True)
        return
    await callback.answer("Номер перемещён в коллекцию 📚")
    await _show_safe_list(callback, page, answer=False)


def _collection_sorted(user) -> list:
    return sorted_stored(storage.visible_collection(user))


async def _show_collection(
    callback: CallbackQuery,
    page: int,
    *,
    pick: bool = False,
    answer: bool = True,
) -> None:
    from vault import collection_capacity

    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user = await storage.get(callback.from_user.id)
    items = _collection_sorted(user)
    cap = collection_capacity(user.collection_level)
    visible_keys = [item.key for item in items]
    user.collection_pick = [k for k in user.collection_pick if k in visible_keys]
    total_value = collection_total_value(visible_keys, user.collection_level)
    picked_value = sum(item.price for item in items if item.key in user.collection_pick)

    size = COLLECTION_PAGE_SIZE
    total_pages = max(1, (len(items) + size - 1) // size)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page * size : (page + 1) * size]

    if pick:
        lines = [
            "☑️ <b>Выбор продажи</b>",
            f"Отмечено: <b>{len(user.collection_pick)}</b> · <b>{picked_value:,}</b> ₽".replace(",", " "),
            "",
        ]
    else:
        lines = [
            f"📚 <b>Коллекция</b> ({len(items)}/{cap})",
            f"💎 Ценность: <b>{total_value:,}</b> ₽".replace(",", " "),
            "",
        ]

    if not items:
        lines.append("Пока пусто. Сюда попадают все выпавшие номера, кроме тех, что в сейфе.")
    else:
        for idx, item in enumerate(chunk):
            global_idx = page * size + idx
            mark = "✅" if pick and item.key in user.collection_pick else f"{global_idx + 1}."
            lines.append(f"{mark} {format_plate_short(item.key, item.price)}")

    rows: list[list[InlineKeyboardButton]] = []
    if pick:
        for idx, item in enumerate(chunk):
            global_idx = page * size + idx
            checked = item.key in user.collection_pick
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{'✅' if checked else '☐'} #{global_idx + 1}",
                        callback_data=f"vlt:ctog:{global_idx}:{page}",
                    )
                ]
            )
        nav = _paginate_nav("vlt:cpick", page, total_pages)
        if nav:
            rows.append(nav)
        if user.collection_pick:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"💵 Продать выбранные ({len(user.collection_pick)})",
                        callback_data="vlt:cpicksell",
                    )
                ]
            )
        rows.append([InlineKeyboardButton(text="↩️ Назад к коллекции", callback_data=f"vlt:col:{page}")])
    else:
        for idx, _item in enumerate(chunk):
            global_idx = page * size + idx
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🔐 #{global_idx + 1} в сейф",
                        callback_data=f"vlt:csafe:{global_idx}",
                    ),
                    InlineKeyboardButton(
                        text=f"💵 #{global_idx + 1}",
                        callback_data=f"vlt:csellask:{plate_key_token(item.key)}",
                    ),
                ]
            )
        nav = _paginate_nav("vlt:col", page, total_pages)
        if nav:
            rows.append(nav)
        if items:
            rows.append(
                [
                    InlineKeyboardButton(text="☑️ Выбрать", callback_data="vlt:cpick:0"),
                    InlineKeyboardButton(text="⚡ Продать всё", callback_data="vlt:cfast"),
                ]
            )
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:home")])

    if answer:
        await callback.answer()
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("vlt:col:"))
async def cb_vault_collection(callback: CallbackQuery) -> None:
    if not callback.data:
        await callback.answer()
        return
    page = int(callback.data.split(":")[2])
    await _show_collection(callback, page, pick=False)


@router.callback_query(F.data.startswith("vlt:cpick:"))
async def cb_collection_pick_mode(callback: CallbackQuery) -> None:
    if not callback.data:
        await callback.answer()
        return
    page = int(callback.data.split(":")[2])
    await _show_collection(callback, page, pick=True)


@router.callback_query(F.data.startswith("vlt:ctog:"))
async def cb_collection_toggle(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        await callback.answer()
        return
    _, _, idx_s, page_s = callback.data.split(":")
    idx, page = int(idx_s), int(page_s)
    user = await storage.get(callback.from_user.id)
    items = _collection_sorted(user)
    if idx < 0 or idx >= len(items):
        await callback.answer("Номер не найден", show_alert=True)
        return
    key = items[idx].key
    if key in user.collection_pick:
        user.collection_pick.remove(key)
    else:
        user.collection_pick.append(key)
    await storage.update(callback.from_user.id, collection_pick=user.collection_pick)
    await _show_collection(callback, page, pick=True)


@router.callback_query(F.data.startswith("vlt:csafe:"))
async def cb_collection_to_safe(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    idx = int(callback.data.split(":")[2])
    user = await storage.get(callback.from_user.id)
    items = _collection_sorted(user)
    if idx < 0 or idx >= len(items):
        await callback.answer("Номер не найден", show_alert=True)
        return
    key = items[idx].key
    if not storage.try_add_safe(user, key):
        await callback.answer("Сейф полон — улучшите его", show_alert=True)
        return
    await storage.update(
        callback.from_user.id,
        safe_items=user.safe_items,
        collection_items=user.collection_items,
        collection_pick=user.collection_pick,
        last_plate_key=None if user.last_plate_key == key else user.last_plate_key,
    )
    await storage.save()
    await callback.answer("В сейфе 🔐")
    page = idx // COLLECTION_PAGE_SIZE
    await _show_collection(callback, page, pick=False, answer=False)


@router.callback_query(F.data.startswith("vlt:csellask:"))
async def cb_collection_sell_ask(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    key = plate_key_from_token(callback.data.split(":", 2)[2])
    if key is None:
        await callback.answer("Номер не найден", show_alert=True)
        return
    user = await storage.get(callback.from_user.id)
    items = _collection_sorted(user)
    item = next((stored for stored in items if stored.key == key), None)
    if item is None:
        await callback.answer("Номер не найден", show_alert=True)
        return
    token = plate_key_token(key)
    await callback.answer()
    await callback.message.edit_text(
        f"⚠️ <b>Продать из коллекции?</b>\n\n{format_plate_short(item.key, item.price)}\n\n"
        "Это действие нельзя отменить.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да, продать", callback_data=f"vlt:csellok:{token}"),
                    InlineKeyboardButton(text="↩️ Отмена", callback_data="vlt:col:0"),
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("vlt:csellok:"))
async def cb_collection_sell_ok(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    key = plate_key_from_token(callback.data.split(":", 2)[2])
    if key is None:
        await callback.answer("Номер не найден", show_alert=True)
        return
    user = await storage.get(callback.from_user.id)
    item = next((stored for stored in _collection_sorted(user) if stored.key == key), None)
    if item is None:
        await callback.answer("Уже продано", show_alert=True)
        return
    sold, new_balance = await storage.sell_collection_plates(
        callback.from_user.id,
        [(item.key, item.price)],
    )
    if not sold:
        await callback.answer("Уже продано", show_alert=True)
        return
    await callback.answer(f"+{item.price} ₽")
    await callback.message.edit_text(
        f"💵 Продано из коллекции за <b>{item.price}</b> ₽\nБаланс: <b>{new_balance}</b> ₽",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📚 К коллекции", callback_data="vlt:col:0")]]
        ),
    )


@router.callback_query(F.data == "vlt:cfast")
async def cb_collection_fast_ask(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    user = await storage.get(callback.from_user.id)
    items = _collection_sorted(user)
    if not items:
        await callback.answer("Коллекция пуста", show_alert=True)
        return
    total = sum(item.price for item in items)
    await callback.answer()
    await callback.message.edit_text(
        f"⚡ <b>Быстрая продажа</b>\n\n"
        f"Продать все <b>{len(items)}</b> номеров из коллекции за <b>{total:,}</b> ₽?\n"
        "Номера в сейфе не затронутся.".replace(",", " "),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Продать всё", callback_data="vlt:cfastok"),
                    InlineKeyboardButton(text="↩️ Отмена", callback_data="vlt:col:0"),
                ]
            ]
        ),
    )


@router.callback_query(F.data == "vlt:cfastok")
async def cb_collection_fast_ok(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    user = await storage.get(callback.from_user.id)
    items = _collection_sorted(user)
    if not items:
        await callback.answer("Коллекция пуста", show_alert=True)
        return
    sold, new_balance = await storage.sell_collection_plates(
        callback.from_user.id,
        [(item.key, item.price) for item in items],
    )
    if not sold:
        await callback.answer("Номера уже проданы", show_alert=True)
        return
    total = sum(price for _, price in sold)
    await callback.answer(f"+{total} ₽")
    await callback.message.edit_text(
        f"⚡ Продано <b>{len(sold)}</b> номеров за <b>{total}</b> ₽\n"
        f"Баланс: <b>{new_balance}</b> ₽",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📚 К коллекции", callback_data="vlt:col:0")]]
        ),
    )


@router.callback_query(F.data == "vlt:cpicksell")
async def cb_collection_pick_sell_ask(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    user = await storage.get(callback.from_user.id)
    items = [item for item in _collection_sorted(user) if item.key in user.collection_pick]
    if not items:
        await callback.answer("Ничего не выбрано", show_alert=True)
        return
    total = sum(item.price for item in items)
    await callback.answer()
    await callback.message.edit_text(
        f"☑️ <b>Продать выбранные</b>\n\n"
        f"Номеров: <b>{len(items)}</b>\n"
        f"Сумма: <b>{total:,}</b> ₽".replace(",", " "),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Продать", callback_data="vlt:cpickok"),
                    InlineKeyboardButton(text="↩️ Назад", callback_data="vlt:cpick:0"),
                ]
            ]
        ),
    )


@router.callback_query(F.data == "vlt:cpickok")
async def cb_collection_pick_sell_ok(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    user = await storage.get(callback.from_user.id)
    items = [item for item in _collection_sorted(user) if item.key in user.collection_pick]
    if not items:
        await callback.answer("Ничего не выбрано", show_alert=True)
        return
    sold, new_balance = await storage.sell_collection_plates(
        callback.from_user.id,
        [(item.key, item.price) for item in items],
    )
    if not sold:
        await callback.answer("Выбранные номера уже проданы", show_alert=True)
        return
    total = sum(price for _, price in sold)
    await callback.answer(f"+{total} ₽")
    await callback.message.edit_text(
        f"💵 Продано выбранных: <b>{len(sold)}</b> за <b>{total}</b> ₽\n"
        f"Баланс: <b>{new_balance}</b> ₽",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📚 К коллекции", callback_data="vlt:col:0")]]
        ),
    )


@router.callback_query(F.data.startswith("vlt:sellask:"))
async def cb_vault_sell_ask(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    key = plate_key_from_token(callback.data.split(":", 2)[2])
    if key is None:
        await callback.answer("Номер не найден", show_alert=True)
        return
    user = await storage.get(callback.from_user.id)
    items = sorted_stored(user.safe_items)
    item = next((stored for stored in items if stored.key == key), None)
    if item is None:
        await callback.answer("Номер не найден", show_alert=True)
        return
    token = plate_key_token(key)
    await callback.answer()
    await callback.message.edit_text(
        f"⚠️ <b>Продать из сейфа?</b>\n\n{format_plate_short(item.key, item.price)}\n\n"
        "Это действие нельзя отменить.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да, продать", callback_data=f"vlt:sellok:{token}"),
                    InlineKeyboardButton(text="↩️ Отмена", callback_data="vlt:safe:0"),
                ]
            ]
        ),
    )


@router.callback_query(F.data.startswith("vlt:sellok:"))
async def cb_vault_sell_ok(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    key = plate_key_from_token(callback.data.split(":", 2)[2])
    if key is None:
        await callback.answer("Номер не найден", show_alert=True)
        return
    user = await storage.get(callback.from_user.id)
    items = sorted_stored(user.safe_items)
    item = next((stored for stored in items if stored.key == key), None)
    if item is None:
        await callback.answer("Уже продан", show_alert=True)
        return

    price = item.price
    new_balance = await storage.sell_safe_plate(callback.from_user.id, key, price)
    if new_balance is None:
        await callback.answer("Уже продан", show_alert=True)
        return
    await callback.answer(f"+{price} ₽")
    await callback.message.edit_text(
        f"💵 Продано из сейфа за <b>{price}</b> ₽\nБаланс: <b>{new_balance}</b> ₽",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔐 К сейфу", callback_data="vlt:safe:0")]]
        ),
    )


@router.callback_query(F.data == "vlt:upsafe")
async def cb_vault_upgrade_safe_ask(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user = await storage.get(callback.from_user.id)
    price = safe_upgrade_price(user.safe_level)
    if price is None:
        await callback.answer("У вас максимальный уровень сейфа!", show_alert=True)
        return

    cur_cap = safe_capacity(user.safe_level)
    next_cap = safe_capacity(user.safe_level + 1)
    can_afford = user.balance >= price

    price_fmt = f"{price:,}".replace(",", " ")
    bal_fmt = f"{user.balance:,}".replace(",", " ")

    lines_text = [
        "⬆️ <b>Улучшение сейфа</b>",
        "",
        f"• Уровень: <b>{user.safe_level}</b> → <b>{user.safe_level + 1}</b>/{MAX_SAFE_LEVEL}",
        f"• Вместимость: <b>{cur_cap}</b> → <b>{next_cap}</b> мест",
        f"• Стоимость: <b>{price_fmt}</b> ₽",
        "",
        f"💳 Ваш баланс: <b>{bal_fmt}</b> ₽",
    ]

    if can_afford:
        rem_fmt = f"{user.balance - price:,}".replace(",", " ")
        lines_text.append(f"Остаток после покупки: <b>{rem_fmt}</b> ₽")
        lines_text.append("")
        lines_text.append("Подтверждаете покупку?")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"✅ Купить за {price_fmt} ₽", callback_data="vlt:upsafe:ok")],
                [InlineKeyboardButton(text="↩️ Отмена", callback_data="menu:home")],
            ]
        )
    else:
        diff_fmt = f"{price - user.balance:,}".replace(",", " ")
        lines_text.append(f"⚠️ <b>Недостаточно средств!</b> Не хватает: <b>{diff_fmt}</b> ₽")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")]
            ]
        )

    await callback.answer()
    await callback.message.edit_text("\n".join(lines_text), reply_markup=kb)


@router.callback_query(F.data == "vlt:upsafe:ok")
async def cb_vault_upgrade_safe_ok(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user = await storage.get(callback.from_user.id)
    price = safe_upgrade_price(user.safe_level)
    if price is None:
        await callback.answer("Максимальный уровень сейфа", show_alert=True)
        return
    if user.balance < price:
        await callback.answer(f"Недостаточно средств. Нужно {price:,} ₽".replace(",", " "), show_alert=True)
        return

    new_level = user.safe_level + 1
    new_balance = user.balance - price
    await storage.update(callback.from_user.id, balance=new_balance, safe_level=new_level)
    await storage.save()
    await callback.answer(f"Сейф улучшен до ур. {new_level} 🔐")
    cap = safe_capacity(new_level)
    await callback.message.edit_text(
        f"✅ <b>Сейф успешно улучшен!</b>\n\n"
        f"Новый уровень: <b>{new_level}</b>/{MAX_SAFE_LEVEL}\n"
        f"Вместимость: <b>{cap}</b> мест\n"
        f"Списано: <b>{price:,}</b> ₽\n"
        f"Текущий баланс: <b>{new_balance:,}</b> ₽".replace(",", " "),
        reply_markup=main_menu_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "vlt:upcol")
async def cb_vault_upgrade_col_ask(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    from vault import collection_capacity, collection_bonus_mult

    user = await storage.get(callback.from_user.id)
    price = collection_upgrade_price(user.collection_level)
    if price is None:
        await callback.answer("У вас максимальный уровень коллекции!", show_alert=True)
        return

    cur_cap = collection_capacity(user.collection_level)
    next_cap = collection_capacity(user.collection_level + 1)
    cur_mult = collection_bonus_mult(user.collection_level)
    next_mult = collection_bonus_mult(user.collection_level + 1)
    can_afford = user.balance >= price

    price_fmt = f"{price:,}".replace(",", " ")
    bal_fmt = f"{user.balance:,}".replace(",", " ")

    lines_text = [
        "⬆️ <b>Улучшение коллекции</b>",
        "",
        f"• Уровень: <b>{user.collection_level}</b> → <b>{user.collection_level + 1}</b>/{MAX_COLLECTION_LEVEL}",
        f"• Слотов: <b>{cur_cap}</b> → <b>{next_cap}</b>",
        f"• Бонус ценности: <b>×{cur_mult:.2f}</b> → <b>×{next_mult:.2f}</b>",
        f"• Стоимость: <b>{price_fmt}</b> ₽",
        "",
        f"💳 Ваш баланс: <b>{bal_fmt}</b> ₽",
    ]

    if can_afford:
        rem_fmt = f"{user.balance - price:,}".replace(",", " ")
        lines_text.append(f"Остаток после покупки: <b>{rem_fmt}</b> ₽")
        lines_text.append("")
        lines_text.append("Подтверждаете покупку?")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"✅ Купить за {price_fmt} ₽", callback_data="vlt:upcol:ok")],
                [InlineKeyboardButton(text="↩️ Отмена", callback_data="menu:home")],
            ]
        )
    else:
        diff_fmt = f"{price - user.balance:,}".replace(",", " ")
        lines_text.append(f"⚠️ <b>Недостаточно средств!</b> Не хватает: <b>{diff_fmt}</b> ₽")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:home")]
            ]
        )

    await callback.answer()
    await callback.message.edit_text("\n".join(lines_text), reply_markup=kb)


@router.callback_query(F.data == "vlt:upcol:ok")
async def cb_vault_upgrade_col_ok(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    from vault import collection_capacity, collection_bonus_mult

    user = await storage.get(callback.from_user.id)
    price = collection_upgrade_price(user.collection_level)
    if price is None:
        await callback.answer("Максимальный уровень коллекции", show_alert=True)
        return
    if user.balance < price:
        await callback.answer(f"Недостаточно средств. Нужно {price:,} ₽".replace(",", " "), show_alert=True)
        return

    new_level = user.collection_level + 1
    new_balance = user.balance - price
    await storage.update(
        callback.from_user.id,
        balance=new_balance,
        collection_level=new_level,
    )
    await storage.save()
    await callback.answer(f"Коллекция улучшена до ур. {new_level} 📚")
    await callback.message.edit_text(
        f"✅ <b>Коллекция успешно улучшена!</b>\n\n"
        f"Новый уровень: <b>{new_level}</b>/{MAX_COLLECTION_LEVEL}\n"
        f"Слотов: <b>{collection_capacity(new_level)}</b> · "
        f"Бонус ценности: <b>×{collection_bonus_mult(new_level):.2f}</b>\n"
        f"Списано: <b>{price:,}</b> ₽\n"
        f"Текущий баланс: <b>{new_balance:,}</b> ₽".replace(",", " "),
        reply_markup=main_menu_keyboard(callback.from_user.id),
    )


@router.callback_query(F.data == "menu:rate_hint")
async def cb_rate_hint(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    await callback.answer()
    await callback.message.edit_text(
        "Отправьте команду:\n<code>/rate А 007 КК 77</code>",
        reply_markup=main_menu_keyboard(callback.from_user.id if callback.from_user else None),
    )


async def _spin_menu_text(user_id: int) -> str:
    user = await storage.get(user_id)
    code = user.selected_region
    cost = current_spin_cost(code)
    if is_all_regions(code):
        hint = "Номер выпадет со случайным кодом по всей РФ."
        price_details = f"Базовая пошлина: <b>{global_spin_cost():,}</b> ₽".replace(",", " ")
    else:
        hint = "Будут генерироваться только номера выбранного региона."
        base = global_spin_cost()
        multiplier = region_multiplier(code or "")
        price_details = (
            f"Базовая пошлина: <b>{base:,}</b> ₽\n"
            f"Множитель региона: <b>×{multiplier:.2f}</b>\n"
            f"Гарантия региона: <b>×{REGIONAL_GUARANTEE_MULTIPLIER:.2f}</b>"
        ).replace(",", " ")
    return (
        f"🎰 <b>Прокрут</b>\n"
        f"Регион: <b>{region_choice_label(code)}</b>\n"
        f"{price_details}\n"
        + f"Стоимость генерации: <b>{cost:,}</b> ₽\n".replace(",", " ")
        + f"{hint}\n\n"
        + await profile_line(user_id)
    )


@router.callback_query(F.data == "menu:spin")
async def cb_spin_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    user = await storage.get(callback.from_user.id)
    await callback.answer()
    await callback.message.edit_text(
        await _spin_menu_text(callback.from_user.id),
        reply_markup=spin_actions_keyboard(user.selected_region),
    )


@router.callback_query(F.data == "menu:global")
async def cb_global_menu_alias(callback: CallbackQuery) -> None:
    await cb_spin_menu(callback)


@router.callback_query(F.data == "menu:region")
async def cb_region_menu(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    await callback.answer()
    await callback.message.edit_text(
        "Выберите регион прокрута. Код региона влияет на генерацию и цену номера.\n"
        "Цена: базовая пошлина × множитель региона × гарантия региона (×1,50).",
        reply_markup=region_list_keyboard(0),
    )


@router.callback_query(F.data.startswith("rpage:"))
async def cb_region_page(callback: CallbackQuery) -> None:
    if not callback.message or not callback.data:
        await callback.answer()
        return
    page = int(callback.data.split(":")[1])
    await callback.answer()
    await callback.message.edit_text(
        "Выберите регион прокрута. Код региона влияет на генерацию и цену номера.\n"
        "Цена: базовая пошлина × множитель региона × гарантия региона (×1,50).",
        reply_markup=region_list_keyboard(page),
    )


@router.callback_query(F.data.startswith("pick:"))
async def cb_pick_region(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        await callback.answer()
        return
    code = callback.data.split(":")[1]
    if code != REGION_ALL and get_region(code) is None:
        await callback.answer("Регион не найден", show_alert=True)
        return
    await storage.update(callback.from_user.id, selected_region=code)
    await callback.answer("Все регионы" if code == REGION_ALL else f"Выбран {code}")
    await callback.message.edit_text(
        await _spin_menu_text(callback.from_user.id),
        reply_markup=spin_actions_keyboard(code),
    )


async def _safe_edit_text(message: Message, text: str, **kwargs) -> None:
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def _animate_spin(
    message: Message,
    final: Plate,
    *,
    lock_region: bool,
) -> None:
    rng = random.Random()
    last_text = ""
    for i in range(3):
        region = final.region_code if lock_region else None
        ghost = generate_plate(region, rng)
        text = f"🎰 Крутим…\n\n<code>{ghost.formatted()}</code>"
        if text == last_text:
            continue
        await _safe_edit_text(message, text)
        last_text = text
        await asyncio.sleep(0.35)
    await _safe_edit_text(message, f"🎰 Крутим…\n\n<code>{final.formatted()}</code>")


@router.callback_query(F.data.in_({"spin:now", "spin:global"}))
async def cb_spin_now(callback: CallbackQuery) -> None:
    await _do_spin(callback)


@router.callback_query(F.data == "spin:repeat")
async def cb_spin_repeat(callback: CallbackQuery) -> None:
    await _do_spin(callback)


@router.callback_query(F.data.startswith("spin:reg:"))
async def cb_spin_regional(callback: CallbackQuery) -> None:
    if not callback.data:
        await callback.answer()
        return
    code = callback.data.split(":")[2]
    if callback.from_user:
        await storage.update(callback.from_user.id, selected_region=code)
    await _do_spin(callback)


async def _do_spin(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    user = await storage.get(user_id)
    from vault import collection_capacity

    if len(storage.visible_collection(user)) >= collection_capacity(user.collection_level):
        await callback.answer(
            "Коллекция заполнена. Освободите место или улучшите коллекцию.",
            show_alert=True,
        )
        return

    region_code = user.selected_region
    all_mode = is_all_regions(region_code)
    cost = current_spin_cost(region_code)

    if user.balance < cost:
        await callback.answer("Недостаточно средств", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text("🎰 Запускаем барабан…")

    rng = random.Random()
    plate = generate_plate(None if all_mode else region_code, rng)

    await _animate_spin(callback.message, plate, lock_region=not all_mode)
    evaluation = evaluate_plate(plate)
    key = plate_to_key(plate)

    new_balance = user.balance - cost
    await storage.update(
        user_id,
        balance=new_balance,
        last_plate_key=key,
        spins=user.spins + 1,
    )
    await apply_spin_progress(user_id, key, evaluation.sell_price, evaluation.rarity.id)

    header = "✅ <b>Результат</b>"
    if evaluation.rarity.id == "legendary":
        header = "🟡 <b>ЛЕГЕНДА!</b>"
    elif evaluation.rarity.id == "epic":
        header = "🟣 <b>Эпический улов!</b>"

    text = (
        f"{header}\n\n"
        f"{format_evaluation(evaluation)}\n\n"
        f"Списано: <b>{cost}</b> ₽ · Баланс: <b>{new_balance}</b> ₽"
    )
    await callback.message.edit_text(text, reply_markup=after_spin_keyboard(key))
    await storage.save()


@router.callback_query(F.data.startswith("sell:"))
async def cb_sell(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message or not callback.data:
        await callback.answer()
        return

    key = callback.data.removeprefix("sell:")
    user = await storage.get(callback.from_user.id)

    if user.last_plate_key != key:
        await callback.answer("Этот номер уже продан или устарел", show_alert=True)
        return

    plate = plate_from_key(key)
    if plate is None:
        await callback.answer("Ошибка номера", show_alert=True)
        return

    if key in user.safe_items:
        await callback.answer("Номер в сейфе — продайте через меню сейфа", show_alert=True)
        return

    evaluation = evaluate_plate(plate)
    price = evaluation.sell_price
    new_balance = await storage.sell_last_plate(callback.from_user.id, key, price)
    if new_balance is None:
        await callback.answer("Этот номер уже продан или устарел", show_alert=True)
        return
    await callback.answer(f"+{price} ₽")
    await callback.message.edit_text(
        f"💵 Продано: {rarity_badge(evaluation.rarity)} · <code>{plate.formatted()}</code>\n"
        f"Получено: <b>{price}</b> ₽\n"
        f"Баланс: <b>{new_balance}</b> ₽\n\n"
        f"{await _spin_menu_text(callback.from_user.id)}",
        reply_markup=spin_actions_keyboard(user.selected_region),
    )


async def main() -> None:
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        env_path = os.path.join(_BASE_DIR, ".env")
        logger.error(
            "BOT_TOKEN не задан. Создайте файл %s с содержимым: BOT_TOKEN=ваш_токен",
            env_path,
        )
        sys.exit(1)

    await storage.load()
    game_cfg = init_game_config(_BASE_DIR)
    await game_cfg.load()
    admins = init_admin_panel(storage)
    if admins:
        logger.info("Админы: %s", ", ".join(str(i) for i in sorted(admins)))
    else:
        logger.warning("ADMIN_IDS пуст — админ-панель никому не доступна")
    session, connection_mode = await resolve_bot_session()

    bot = Bot(
        token=token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.update.outer_middleware(ProfileMiddleware())
    dp.include_router(admin_router)
    dp.include_router(router)

    if connection_mode == "direct":
        logger.info("Бот «Госномера РФ» запущен без прокси")
    else:
        logger.info("Бот «Госномера РФ» запущен через прокси")

    try:
        await dp.start_polling(bot)
    finally:
        await storage.save()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
