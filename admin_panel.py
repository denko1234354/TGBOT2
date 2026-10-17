"""Админ-панель: игроки, экономика, вайп."""

from __future__ import annotations

import os

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from game_config import (
    CONFIG_FIELDS,
    config_store,
    format_config_text,
)
from leaderboard import format_leaderboard
from storage import UserStorage

admin_router = Router(name="admin")

_ADMIN_IDS: set[int] = set()
_storage: UserStorage | None = None

PLAYERS_PER_PAGE = 6
MONEY_PRESETS = (1_000, 5_000, 25_000, 100_000)

INT_FIELDS = {
    "global_roulette_cost",
    "spin_tier_1",
    "spin_tier_2",
    "spin_tier_3",
    "spin_tier_4",
    "start_balance",
}
FLOAT_FIELDS = {
    "sell_price_multiplier",
    "special_spawn_multiplier",
    "collection_bonus_step",
}


class AdminStates(StatesGroup):
    waiting_money = State()
    waiting_setting = State()
    waiting_price_list = State()
    waiting_search = State()


def init_admin_panel(storage: UserStorage) -> set[int]:
    global _storage, _ADMIN_IDS
    _storage = storage
    raw = os.getenv("ADMIN_IDS", "").strip()
    _ADMIN_IDS = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            _ADMIN_IDS.add(int(part))
    return _ADMIN_IDS


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in _ADMIN_IDS


def admin_home_text() -> str:
    ids_hint = ", ".join(str(i) for i in sorted(_ADMIN_IDS)) or "не заданы"
    return (
        "🛠 <b>Админ-панель</b>\n\n"
        f"Админы: <code>{ids_hint}</code>\n"
        "Игроки появляются в списке после /start."
    )


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎰 Крутить", callback_data="menu:spin")],
            [
                InlineKeyboardButton(text="💰 Баланс", callback_data="menu:balance"),
                InlineKeyboardButton(text="🔐 Сейф", callback_data="menu:vault"),
            ],
            [
                InlineKeyboardButton(text="📖 Правила", callback_data="menu:rules"),
                InlineKeyboardButton(text="🏆 Лидеры", callback_data="menu:leaderboard"),
            ],
            [InlineKeyboardButton(text="🔍 Оценить", callback_data="menu:rate_hint")],
            [InlineKeyboardButton(text="🛠 Админка", callback_data="menu:admin")],
        ]
    )


def _admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Игроки", callback_data="admin:pls:0")],
            [InlineKeyboardButton(text="⚙️ Цены и шансы", callback_data="admin:cfg")],
            [InlineKeyboardButton(text="🏆 Лидеры", callback_data="menu:leaderboard")],
            [InlineKeyboardButton(text="💣 Вайп всех", callback_data="admin:wipe")],
            [InlineKeyboardButton(text="✖️ Закрыть", callback_data="admin:close")],
        ]
    )


def _cancel_kb(back: str = "admin:cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Отмена", callback_data=back)]]
    )


async def _require_admin(event: Message | CallbackQuery) -> int | None:
    user = event.from_user
    if not user or not is_admin(user.id):
        if isinstance(event, CallbackQuery):
            await event.answer("Доступ только для администратора", show_alert=True)
        elif isinstance(event, Message):
            await event.answer("⛔ Команда только для администратора.")
        return None
    return user.id


def _player_label(uid: str, name: str, balance: int) -> str:
    shown = name or f"ID {uid}"
    if len(shown) > 28:
        shown = shown[:25] + "…"
    return f"{shown} · {balance} ₽"


async def _format_user_card(user_id: int) -> str:
    assert _storage is not None
    user = await _storage.get(user_id)
    name = user.display_name or "—"
    best = "—"
    if user.best_plate_key and user.best_plate_price:
        from plates import plate_from_storage_key

        plate = plate_from_storage_key(user.best_plate_key)
        if plate:
            best = f"{plate.formatted()} ({user.best_plate_price:,} ₽)".replace(",", " ")
    return (
        f"👤 <b>{name}</b>\n"
        f"ID: <code>{user_id}</code>\n"
        f"💳 Баланс: <b>{user.balance}</b> ₽\n"
        f"🎲 Прокрутов: <b>{user.spins}</b>\n"
        f"🔐 Сейф: ур. {user.safe_level} · {len(user.safe_items)} шт.\n"
        f"📚 Коллекция: ур. {user.collection_level} · {len(user.collection_items)} шт.\n"
        f"💎 Лучший номер: {best}"
    )


def _player_card_kb(user_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    add_row: list[InlineKeyboardButton] = []
    for amount in MONEY_PRESETS:
        label = f"+{amount // 1000}к" if amount >= 1000 else f"+{amount}"
        add_row.append(InlineKeyboardButton(text=label, callback_data=f"admin:pay:{user_id}:{amount}"))
        if len(add_row) == 2:
            rows.append(add_row)
            add_row = []
    if add_row:
        rows.append(add_row)
    rows.append(
        [
            InlineKeyboardButton(text="➕ Своя сумма", callback_data=f"admin:pcustom:{user_id}:add"),
            InlineKeyboardButton(text="➖ Списать", callback_data=f"admin:pcustom:{user_id}:sub"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="💣 Вайп игрока", callback_data=f"admin:pwipe:{user_id}"),
            InlineKeyboardButton(text="⬅️ К списку", callback_data="admin:pls:0"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_players(callback: CallbackQuery, page: int, query: str = "") -> None:
    assert _storage is not None
    players = await _storage.list_players()
    needle = query.strip().lower().lstrip("@")
    if needle:
        filtered = []
        for uid, user in players:
            name = (user.display_name or "").lower().lstrip("@")
            if needle in name or needle in uid:
                filtered.append((uid, user))
        players = filtered
    total_pages = max(1, (len(players) + PLAYERS_PER_PAGE - 1) // PLAYERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = players[page * PLAYERS_PER_PAGE : (page + 1) * PLAYERS_PER_PAGE]

    lines = [f"👥 <b>Игроки</b> ({len(players)})", "Нажми на игрока — без ввода ID."]
    if needle:
        lines.append(f"Фильтр: <code>{query}</code>")
    lines.append("")
    if not chunk:
        lines.append("Никого нет. Пусть зайдут в бота — они появятся сами.")
    rows: list[list[InlineKeyboardButton]] = []
    for uid, user in chunk:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_player_label(uid, user.display_name, user.balance),
                    callback_data=f"admin:plr:{uid}",
                )
            ]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"admin:pls:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"admin:pls:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(text="🔎 Имя / @ник", callback_data="admin:search"),
            InlineKeyboardButton(text="♻️ Сброс фильтра", callback_data="admin:plsclr"),
        ]
    )
    rows.append([InlineKeyboardButton(text="⬅️ Админка", callback_data="menu:admin")])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _settings_kb() -> InlineKeyboardMarkup:
    s = config_store().get()
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in CONFIG_FIELDS.items():
        value = getattr(s, key)
        rows.append(
            [InlineKeyboardButton(text=f"{label}: {value}", callback_data=f"admin:set:{key}")]
        )
    rows.append(
        [InlineKeyboardButton(text="🔐 Цены сейфа", callback_data="admin:setlist:safe")]
    )
    rows.append(
        [InlineKeyboardButton(text="📚 Цены коллекции", callback_data="admin:setlist:col")]
    )
    rows.append(
        [
            InlineKeyboardButton(text="♻️ Сброс настроек", callback_data="admin:cfgreset"),
            InlineKeyboardButton(text="⬅️ Админка", callback_data="menu:admin"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _apply_delta(target_id: int, delta: int) -> tuple[int, int]:
    assert _storage is not None
    user = await _storage.get(target_id)
    before = user.balance
    after = max(0, before + delta)
    await _storage.update(target_id, balance=after)
    await _storage.save()
    return before, after


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if await _require_admin(message) is None:
        return
    await state.clear()
    await message.answer(admin_home_text(), reply_markup=_admin_kb())


@admin_router.callback_query(F.data == "menu:admin")
async def cb_menu_admin(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(admin_home_text(), reply_markup=_admin_kb())


@admin_router.callback_query(F.data == "admin:close")
async def cb_admin_close(callback: CallbackQuery, state: FSMContext) -> None:
    admin = await _require_admin(callback)
    if admin is None:
        return
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "🇷🇺 <b>Главное меню</b>\n\nВыберите действие:",
            reply_markup=_main_menu_kb(),
        )


@admin_router.callback_query(F.data == "admin:cancel")
async def cb_admin_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.edit_text(admin_home_text(), reply_markup=_admin_kb())


@admin_router.callback_query(F.data.startswith("admin:pls:"))
async def cb_players(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    data = await state.get_data()
    query = str(data.get("player_query") or "")
    await callback.answer()
    await _show_players(callback, int(callback.data.split(":")[2]), query)


@admin_router.callback_query(F.data == "admin:plsclr")
async def cb_players_clear(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.clear()
    await callback.answer("Фильтр сброшен")
    await _show_players(callback, 0, "")


@admin_router.callback_query(F.data == "admin:search")
async def cb_player_search(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.set_state(AdminStates.waiting_search)
    await callback.answer()
    await callback.message.edit_text(
        "🔎 Введите имя, фамилию или @ник игрока.\n"
        "Он должен хотя бы раз зайти в бота.",
        reply_markup=_cancel_kb("admin:pls:0"),
    )


@admin_router.message(AdminStates.waiting_search, F.text)
async def admin_got_search(message: Message, state: FSMContext) -> None:
    if await _require_admin(message) is None:
        return
    query = (message.text or "").strip()
    await state.set_state(None)
    await state.update_data(player_query=query)
    assert _storage is not None
    players = await _storage.list_players()
    needle = query.lower().lstrip("@")
    matches = [
        (uid, user)
        for uid, user in players
        if needle in (user.display_name or "").lower().lstrip("@") or needle in uid
    ]
    if not matches:
        await message.answer(
            f"Никого не нашёл по «{query}».",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="👥 К списку", callback_data="admin:pls:0")]]
            ),
        )
        return
    rows = [
        [
            InlineKeyboardButton(
                text=_player_label(uid, user.display_name, user.balance),
                callback_data=f"admin:plr:{uid}",
            )
        ]
        for uid, user in matches[:12]
    ]
    rows.append([InlineKeyboardButton(text="👥 Весь список", callback_data="admin:plsclr")])
    await message.answer(
        f"🔎 Нашёл: <b>{len(matches)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@admin_router.callback_query(F.data.startswith("admin:plr:"))
async def cb_player_card(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    await state.clear()
    uid = int(callback.data.split(":")[2])
    await callback.answer()
    await callback.message.edit_text(
        await _format_user_card(uid),
        reply_markup=_player_card_kb(uid),
    )


@admin_router.callback_query(F.data.startswith("admin:pay:"))
async def cb_player_pay(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    _, _, uid_s, amount_s = callback.data.split(":")
    uid, amount = int(uid_s), int(amount_s)
    before, after = await _apply_delta(uid, amount)
    await callback.answer(f"+{amount} ₽")
    await callback.message.edit_text(
        f"✅ Начислено <b>{amount}</b> ₽ ({before} → {after})\n\n" + await _format_user_card(uid),
        reply_markup=_player_card_kb(uid),
    )


@admin_router.callback_query(F.data.startswith("admin:pcustom:"))
async def cb_player_custom_money(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    _, _, uid_s, mode = callback.data.split(":")
    await state.set_state(AdminStates.waiting_money)
    await state.update_data(target_id=int(uid_s), mode=mode)
    await callback.answer()
    action = "начислить" if mode == "add" else "списать"
    await callback.message.edit_text(
        f"Введите сумму, чтобы {action} игроку <code>{uid_s}</code>.",
        reply_markup=_cancel_kb(f"admin:plr:{uid_s}"),
    )


@admin_router.message(AdminStates.waiting_money, F.text)
async def admin_got_money(message: Message, state: FSMContext) -> None:
    if await _require_admin(message) is None:
        return
    raw = (message.text or "").replace(" ", "").replace(",", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Нужно целое число больше нуля.")
        return
    data = await state.get_data()
    uid = int(data["target_id"])
    amount = int(raw)
    if data.get("mode") == "sub":
        amount = -amount
    before, after = await _apply_delta(uid, amount)
    await state.clear()
    sign = "+" if amount > 0 else "−"
    await message.answer(
        f"✅ {sign}{abs(amount)} ₽ ({before} → {after})\n\n" + await _format_user_card(uid),
        reply_markup=_player_card_kb(uid),
    )


@admin_router.callback_query(F.data.startswith("admin:pwipe:"))
async def cb_player_wipe_ask(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    uid = int(callback.data.split(":")[2])
    await callback.answer()
    await callback.message.edit_text(
        f"💣 Стереть игрока <code>{uid}</code>? Баланс, сейф и коллекция пропадут.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Стереть", callback_data=f"admin:pwipeok:{uid}"),
                    InlineKeyboardButton(text="↩️ Нет", callback_data=f"admin:plr:{uid}"),
                ]
            ]
        ),
    )


@admin_router.callback_query(F.data.startswith("admin:pwipeok:"))
async def cb_player_wipe_ok(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    assert _storage is not None
    uid = int(callback.data.split(":")[2])
    await _storage.wipe_user(uid)
    await callback.answer("Игрок стёрт")
    await callback.message.edit_text(
        f"💣 Игрок <code>{uid}</code> удалён.",
        reply_markup=_admin_kb(),
    )


@admin_router.callback_query(F.data == "admin:cfg")
async def cb_settings(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(format_config_text(), reply_markup=_settings_kb())


@admin_router.callback_query(F.data.startswith("admin:set:"))
async def cb_set_field(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    key = callback.data.split(":", 2)[2]
    if key not in CONFIG_FIELDS:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_setting)
    await state.update_data(field=key)
    await callback.answer()
    current = getattr(config_store().get(), key)
    hint = "число (можно с точкой)" if key in FLOAT_FIELDS else "целое число"
    await callback.message.edit_text(
        f"{CONFIG_FIELDS[key]}\nСейчас: <b>{current}</b>\n\nОтправьте новое значение ({hint}).",
        reply_markup=_cancel_kb("admin:cfg"),
    )


@admin_router.message(AdminStates.waiting_setting, F.text)
async def admin_got_setting(message: Message, state: FSMContext) -> None:
    if await _require_admin(message) is None:
        return
    data = await state.get_data()
    key = str(data.get("field", ""))
    raw = (message.text or "").strip().replace(",", ".")
    try:
        if key in FLOAT_FIELDS:
            value: int | float = float(raw)
        else:
            value = int(float(raw))
            if value < 0:
                raise ValueError
    except ValueError:
        await message.answer("Не получилось прочитать число.")
        return
    await config_store().set_field(key, value)
    await state.clear()
    await message.answer(
        f"✅ {CONFIG_FIELDS.get(key, key)} = <b>{value}</b>\n\n" + format_config_text(),
        reply_markup=_settings_kb(),
    )


@admin_router.callback_query(F.data.startswith("admin:setlist:"))
async def cb_set_price_list(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    kind = callback.data.split(":")[2]
    s = config_store().get()
    current = s.safe_upgrade_prices if kind == "safe" else s.collection_upgrade_prices
    await state.set_state(AdminStates.waiting_price_list)
    await state.update_data(list_kind=kind)
    await callback.answer()
    title = "сейфа" if kind == "safe" else "коллекции"
    await callback.message.edit_text(
        f"Цены улучшения {title} (4 числа через запятую или пробел).\n"
        f"Сейчас: <code>{current}</code>\n"
        "Пример: <code>5000 18000 45000 100000</code>",
        reply_markup=_cancel_kb("admin:cfg"),
    )


@admin_router.message(AdminStates.waiting_price_list, F.text)
async def admin_got_price_list(message: Message, state: FSMContext) -> None:
    if await _require_admin(message) is None:
        return
    raw = (message.text or "").replace(";", ",").replace(" ", ",")
    parts = [p for p in raw.split(",") if p]
    try:
        values = [int(p) for p in parts]
        if len(values) != 4 or any(v < 0 for v in values):
            raise ValueError
    except ValueError:
        await message.answer("Нужно ровно 4 неотрицательных числа.")
        return
    data = await state.get_data()
    kind = data.get("list_kind")
    field = "safe_upgrade_prices" if kind == "safe" else "collection_upgrade_prices"
    await config_store().set_field(field, values)
    await state.clear()
    await message.answer("✅ Цены обновлены.\n\n" + format_config_text(), reply_markup=_settings_kb())


@admin_router.callback_query(F.data == "admin:cfgreset")
async def cb_cfg_reset_ask(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None:
        return
    await callback.answer()
    await callback.message.edit_text(
        "♻️ Вернуть цены и шансы к значениям по умолчанию?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Сбросить", callback_data="admin:cfgresetok"),
                    InlineKeyboardButton(text="↩️ Нет", callback_data="admin:cfg"),
                ]
            ]
        ),
    )


@admin_router.callback_query(F.data == "admin:cfgresetok")
async def cb_cfg_reset_ok(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None:
        return
    await config_store().reset()
    await callback.answer("Настройки сброшены")
    await callback.message.edit_text(format_config_text(), reply_markup=_settings_kb())


@admin_router.callback_query(F.data == "admin:wipe")
async def cb_wipe_ask(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None:
        return
    await callback.answer()
    await callback.message.edit_text(
        "💣 <b>Вайп всех игроков</b>\n\n"
        "Удалятся балансы, сейфы, коллекции и рекорды.\n"
        "Настройки цен/шансов останутся.\n\n"
        "Это нельзя отменить.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Вайпнуть всех", callback_data="admin:wipeok"),
                    InlineKeyboardButton(text="↩️ Отмена", callback_data="menu:admin"),
                ]
            ]
        ),
    )


@admin_router.callback_query(F.data == "admin:wipeok")
async def cb_wipe_ok(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None:
        return
    assert _storage is not None
    count = await _storage.wipe_all()
    await callback.answer("Вайп выполнен")
    await callback.message.edit_text(
        f"💣 Стерто игроков: <b>{count}</b>.",
        reply_markup=_admin_kb(),
    )


@admin_router.message(Command("admin_top"))
async def cmd_admin_top(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    assert _storage is not None
    rows = await _storage.leaderboard(15)
    await message.answer(format_leaderboard(rows))
