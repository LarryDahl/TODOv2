from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Oppari: Start", callback_data="opp:start")
    kb.button(text="Oppari: End", callback_data="opp:end")
    kb.button(text="Oppari: Status", callback_data="opp:status")
    kb.button(text="Agents", callback_data="admin:agents")
    kb.button(text="Status", callback_data="nav:status")
    kb.adjust(2, 2, 1)
    return kb.as_markup()
