"""Таблица лидеров по стоимости лучшего номера."""

from __future__ import annotations

from plates import evaluate_plate, plate_from_storage_key, rarity_badge
from storage import UserState


def _format_money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_leaderboard(rows: list[tuple[str, UserState]], *, title: str | None = None) -> str:
    header = title or "🏆 <b>Лидеры по стоимости номера</b>"
    if not rows:
        return f"{header}\n\nПока никто не выбил рекордный номер. Крути рулетку!"

    lines = [header, ""]
    medals = ("🥇", "🥈", "🥉")
    for idx, (uid, user) in enumerate(rows, start=1):
        medal = medals[idx - 1] if idx <= 3 else f"{idx}."
        name = user.display_name or f"ID {uid}"
        price = user.best_plate_price
        lines.append(f"{medal} <b>{name}</b> — <b>{_format_money(price)}</b> ₽")

        plate_line = "   <i>номер не сохранён</i>"
        if user.best_plate_key:
            plate = plate_from_storage_key(user.best_plate_key)
            if plate:
                ev = evaluate_plate(plate)
                plate_line = (
                    f"   {rarity_badge(ev.rarity)} · <code>{plate.formatted()}</code> "
                    f"· {_format_money(price)} ₽"
                )
        lines.append(plate_line)
        lines.append("")

    return "\n".join(lines).strip()
