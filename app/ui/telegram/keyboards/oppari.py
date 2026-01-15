from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def now_or_manual_kb(prefix: str) -> InlineKeyboardMarkup:
    """
    prefix examples:
      - "opp:start_time"
      - "opp:end_time"
    callback_data will be:
      - f"{prefix}:now"
      - f"{prefix}:manual"
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="Now", callback_data=f"{prefix}:now")
    kb.button(text="Enter time", callback_data=f"{prefix}:manual")
    kb.adjust(2)
    return kb.as_markup()


def yes_no_kb(prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Yes", callback_data=f"{prefix}:yes")
    kb.button(text="No", callback_data=f"{prefix}:no")
    kb.adjust(2)
    return kb.as_markup()


def cancel_kb(prefix: str = "opp:cancel") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Cancel", callback_data=prefix)
    kb.adjust(1)
    return kb.as_markup()
