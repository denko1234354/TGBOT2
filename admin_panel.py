"""Админ-панель: игроки, экономика, вайп."""

from __future__ import annotations

import asyncio
import os
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
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
FEEDBACK_CHUNK_SIZE = 600
_BROADCAST_LOCK = asyncio.Lock()

INT_FIELDS = {
    "global_roulette_cost",
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
    waiting_promo = State()
    waiting_broadcast = State()


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
            [InlineKeyboardButton(text="🎟 Промокод", callback_data="menu:promo")],
            [InlineKeyboardButton(text="📨 Отзыв / предложение", callback_data="menu:feedback")],
            [InlineKeyboardButton(text="🛠 Админка", callback_data="menu:admin")],
        ]
    )


def _admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Игроки", callback_data="admin:pls:0")],
            [InlineKeyboardButton(text="📣 Рассылка игрокам", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="📨 Отзывы и предложения", callback_data="admin:feedback:0")],
            [InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin:promos")],
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


async def _show_feedback(callback: CallbackQuery, item_index: int, part_index: int = 0) -> None:
    assert _storage is not None
    items = await _storage.list_feedback()
    if not items:
        lines = ["📨 <b>Отзывы и предложения</b> · 0", "", "Пока отзывов нет."]
        rows = [[InlineKeyboardButton(text="⬅️ Админка", callback_data="menu:admin")]]
        await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return

    pages: list[tuple[int, int]] = []
    for idx, item in enumerate(items):
        body = str(item.get("text") or "")
        parts = max(1, (len(body) + FEEDBACK_CHUNK_SIZE - 1) // FEEDBACK_CHUNK_SIZE)
        pages.extend((idx, part) for part in range(parts))
    requested = (max(0, min(item_index, len(items) - 1)), max(0, part_index))
    if requested not in pages:
        requested = (requested[0], 0)
    page = pages.index(requested)
    item_index, part_index = pages[page]
    item = items[item_index]
    raw_body = str(item.get("text") or "")
    part_count = max(1, (len(raw_body) + FEEDBACK_CHUNK_SIZE - 1) // FEEDBACK_CHUNK_SIZE)
    body = escape(raw_body[part_index * FEEDBACK_CHUNK_SIZE : (part_index + 1) * FEEDBACK_CHUNK_SIZE])
    name = escape(str(item.get("display_name") or "Игрок")[:48])
    uid = escape(str(item.get("user_id") or "—"))
    created_at = escape(str(item.get("created_at") or ""))
    lines = [
        f"📨 <b>Отзывы и предложения</b> · {len(items)}",
        f"Сообщение {item_index + 1} из {len(items)} · часть {part_index + 1} из {part_count}",
        "",
        f"<b>{name}</b> · <code>{uid}</code> · <i>{created_at}</i>",
        "",
        body,
    ]
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        prev_item, prev_part = pages[page - 1]
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"admin:feedback:{prev_item}:{prev_part}"))
    if page < len(pages) - 1:
        next_item, next_part = pages[page + 1]
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"admin:feedback:{next_item}:{next_part}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Админка", callback_data="menu:admin")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if await _require_admin(message) is None:
        return
    await state.clear()
    await message.answer(admin_home_text(), reply_markup=_admin_kb())


@admin_router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.answer()
    await callback.message.edit_text(
        "📣 Напишите текст для рассылки всем игрокам. Он будет отправлен как обычный текст.\n"
        "Максимум — 4000 символов. Перед отправкой появится подтверждение.",
        reply_markup=_cancel_kb("admin:broadcast:cancel"),
    )


@admin_router.callback_query(F.data == "admin:broadcast:cancel")
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.clear()
    await callback.answer("Рассылка отменена")
    await callback.message.edit_text(admin_home_text(), reply_markup=_admin_kb())


@admin_router.message(AdminStates.waiting_broadcast, F.text)
async def admin_broadcast_preview(message: Message, state: FSMContext) -> None:
    if await _require_admin(message) is None:
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст пустой. Отправьте сообщение для рассылки.")
        return
    if len(text.encode("utf-16-le")) // 2 > 4000:
        await message.answer("Слишком длинное сообщение. Максимум — 4000 символов.")
        return
    assert _storage is not None
    players = await _storage.list_players()
    await state.update_data(broadcast_text=text, broadcast_count=len(players))
    await state.set_state(None)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Отправить ({len(players)} игрокам)", callback_data="admin:broadcast:confirm")],
        [InlineKeyboardButton(text="↩️ Отмена", callback_data="admin:broadcast:cancel")],
    ])
    preview = text if len(text) <= 1800 else text[:1800] + "\n… (предпросмотр обрезан)"
    await message.answer(
        f"Предпросмотр рассылки · получателей: {len(players)}\n\n{preview}",
        reply_markup=markup,
    )


@admin_router.callback_query(F.data == "admin:broadcast:confirm")
async def cb_broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if await _require_admin(callback) is None:
        return
    if _BROADCAST_LOCK.locked():
        await callback.answer("Рассылка уже выполняется", show_alert=True)
        return
    await _BROADCAST_LOCK.acquire()
    try:
        data = await state.get_data()
        text = str(data.get("broadcast_text") or "")
        if not text:
            await callback.answer("Черновик рассылки не найден", show_alert=True)
            return
        await state.clear()
        assert _storage is not None
        players = await _storage.list_players()
        await callback.answer("Рассылка началась")
        if callback.message:
            await callback.message.edit_text(
                f"📣 Отправляю сообщение игрокам: 0/{len(players)}",
                parse_mode=None,
            )
        sent = 0
        failed = 0
        for index, (user_id, _user) in enumerate(players, start=1):
            while True:
                try:
                    await bot.send_message(chat_id=int(user_id), text=text, parse_mode=None)
                    sent += 1
                    break
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(exc.retry_after + 0.2)
                except TelegramAPIError:
                    failed += 1
                    break
            if index % 25 == 0 or index == len(players):
                if callback.message:
                    await callback.message.edit_text(
                        f"📣 Рассылка: {index}/{len(players)}\n"
                        f"✅ Доставлено: {sent}\n❌ Не доставлено: {failed}",
                        parse_mode=None,
                    )
            await asyncio.sleep(0.05)
        if callback.message:
            await callback.message.edit_text(
                f"✅ Рассылка завершена.\nПолучателей: {len(players)}\n"
                f"Доставлено: {sent}\nНе доставлено: {failed}",
                reply_markup=_admin_kb(),
                parse_mode=None,
            )
    finally:
        _BROADCAST_LOCK.release()


async def _show_promos(target: Message | CallbackQuery) -> None:
    assert _storage is not None
    promos = await _storage.list_promos()
    lines = ["🎟 <b>Промокоды</b>", "Формат создания: КОД СУММА ЛИМИТ (0 — без лимита).", ""]
    if not promos:
        lines.append("Промокодов пока нет.")
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin:promo:add")]
    ]
    for code, promo in promos:
        redeemed = promo.get("redeemed_by", [])
        redeemed_count = len(redeemed) if isinstance(redeemed, list) else 0
        maximum = int(promo.get("max_uses", 0))
        limit = str(maximum) if maximum else "∞"
        active = bool(promo.get("active", True))
        status = "включён" if active else "выключен"
        lines.append(
            f"<code>{escape(code)}</code> · {int(promo.get('reward', 0))} ₽ · "
            f"{redeemed_count}/{limit} · {status}"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="⏸ Выключить" if active else "▶️ Включить",
                    callback_data=f"admin:promo:toggle:{code}",
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"admin:promo:delete:{code}",
                ),
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Админка", callback_data="menu:admin")])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if isinstance(target, CallbackQuery):
        if target.message:
            await target.message.edit_text("\n".join(lines), reply_markup=markup)
    else:
        await target.answer("\n".join(lines), reply_markup=markup)


@admin_router.callback_query(F.data.startswith("admin:promo:toggle:"))
async def cb_admin_promo_toggle(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    assert _storage is not None
    code = callback.data.removeprefix("admin:promo:toggle:")
    promos = dict(await _storage.list_promos())
    promo = promos.get(code)
    if promo is None:
        await callback.answer("Промокод не найден", show_alert=True)
        return
    active = not bool(promo.get("active", True))
    if not await _storage.set_promo_active(code, active):
        await callback.answer("Промокод не найден", show_alert=True)
        return
    await callback.answer("Промокод включён" if active else "Промокод выключен")
    await _show_promos(callback)


@admin_router.callback_query(F.data.startswith("admin:promo:delete:"))
async def cb_admin_promo_delete_prompt(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    code = callback.data.removeprefix("admin:promo:delete:")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"Удалить промокод <code>{escape(code)}</code>?\n"
            "Его больше нельзя будет активировать.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"admin:promo:delconfirm:{code}")],
                    [InlineKeyboardButton(text="↩️ Отмена", callback_data="admin:promos")],
                ]
            ),
        )


@admin_router.callback_query(F.data.startswith("admin:promo:delconfirm:"))
async def cb_admin_promo_delete_confirm(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    assert _storage is not None
    code = callback.data.removeprefix("admin:promo:delconfirm:")
    deleted = await _storage.delete_promo(code)
    await callback.answer("Промокод удалён" if deleted else "Промокод уже отсутствует")
    await _show_promos(callback)


@admin_router.callback_query(F.data == "admin:promos")
async def cb_admin_promos(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.clear()
    await callback.answer()
    await _show_promos(callback)


@admin_router.callback_query(F.data == "admin:promo:add")
async def cb_admin_promo_add(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.set_state(AdminStates.waiting_promo)
    await callback.answer()
    await callback.message.edit_text(
        "Отправьте одной строкой: <code>КОД НАГРАДА ЛИМИТ</code>\n"
        "Например: <code>START500 500 100</code>\n"
        "Лимит 0 означает неограниченное число активаций.",
        reply_markup=_cancel_kb("admin:promos"),
    )


@admin_router.message(AdminStates.waiting_promo, F.text)
async def admin_create_promo(message: Message, state: FSMContext) -> None:
    if await _require_admin(message) is None:
        return
    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        await message.answer("Нужны три значения: КОД НАГРАДА ЛИМИТ. Пример: <code>START500 500 100</code>")
        return
    code = parts[0].upper()
    if not (3 <= len(code) <= 32) or not all(ch.isalnum() or ch in "_-" for ch in code):
        await message.answer("Код должен быть длиной 3–32 символа и содержать только буквы, цифры, _ или -.")
        return
    try:
        reward, max_uses = int(parts[1]), int(parts[2])
    except ValueError:
        await message.answer("Награда и лимит должны быть целыми числами.")
        return
    if reward <= 0 or max_uses < 0:
        await message.answer("Награда должна быть больше нуля, лимит — ноль или больше.")
        return
    assert _storage is not None
    created = await _storage.add_promo(code, reward, max_uses)
    if not created:
        await message.answer("Такой код уже существует. Используйте другое название.")
        return
    await state.clear()
    await message.answer(f"✅ Промокод <code>{escape(code)}</code> создан.")
    await _show_promos(message)


@admin_router.callback_query(F.data == "menu:admin")
async def cb_menu_admin(callback: CallbackQuery, state: FSMContext) -> None:
    if await _require_admin(callback) is None:
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(admin_home_text(), reply_markup=_admin_kb())


@admin_router.callback_query(F.data.startswith("admin:feedback:"))
async def cb_admin_feedback(callback: CallbackQuery) -> None:
    if await _require_admin(callback) is None or not callback.data:
        return
    await callback.answer()
    parts = callback.data.split(":")
    item_index = int(parts[2]) if len(parts) > 2 else 0
    part_index = int(parts[3]) if len(parts) > 3 else 0
    await _show_feedback(callback, item_index, part_index)


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
    value = getattr(config_store().get(), key)
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
