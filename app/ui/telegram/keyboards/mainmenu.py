from __future__ import annotations

from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()

    kb.button(text="Agentit")
    kb.button(text="Asetukset")
    kb.button(text="Tilastot")
    kb.button(text="Lisää tehtävä")

    # 2x2 grid
    kb.adjust(2, 2)

    return kb.as_markup(resize_keyboard=True, one_time_keyboard=False)
