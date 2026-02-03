# -*- coding: utf-8 -*-
"""
Shared keyboard builder: ButtonSpec and build_kb for inline keyboards.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


@dataclass
class ButtonSpec:
    """Spec for one inline button: text and callback_data."""
    text: str
    callback_data: str
    width: Optional[int] = None  # unused per-button; row width is set via build_kb row_widths


def build_kb(
    rows: list[list[ButtonSpec]],
    row_widths: Optional[list[int]] = None,
) -> InlineKeyboardMarkup:
    """
    Build InlineKeyboardMarkup from rows of ButtonSpec.
    row_widths[i] = width for row i (e.g. 5 for five buttons in one row); None = default (one per row or pack).
    """
    kb = InlineKeyboardBuilder()
    for i, row in enumerate(rows):
        buttons = [InlineKeyboardButton(text=b.text, callback_data=b.callback_data) for b in row]
        w = row_widths[i] if row_widths and i < len(row_widths) else None
        if w is not None:
            kb.row(*buttons, width=w)
        else:
            kb.row(*buttons)
    return kb.as_markup()
