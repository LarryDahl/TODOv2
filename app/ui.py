from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import Task


def _label(text: str, max_len: int = 48) -> str:
    t = text.strip()
    return t[:max_len] + ("…" if len(t) > max_len else "")


def home_kb(tasks: list[Task]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # Tehtävät: yksi nappi per rivi, klikkaus = suoritettu
    for t in tasks:
        kb.row(
            InlineKeyboardButton(
                text=_label(t.text),
                callback_data=f"task:done:{t.id}",
            )
        )

    # Alarivi: [Lisää][Muokkaa]
    kb.row(
        InlineKeyboardButton(text="Lisää", callback_data="home:add"),
        InlineKeyboardButton(text="Muokkaa", callback_data="home:edit"),
        width=2,
    )
    return kb.as_markup()


def edit_list_kb(tasks: list[Task]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # [tehtävä (done)][muokkaa][poista]
    for t in tasks:
        kb.row(
            InlineKeyboardButton(text=_label(t.text, 32), callback_data=f"task:done:{t.id}"),
            InlineKeyboardButton(text="muokkaa", callback_data=f"task:edit:{t.id}"),
            InlineKeyboardButton(text="poista", callback_data=f"task:del:{t.id}"),
            width=3,
        )

    kb.row(InlineKeyboardButton(text="Takaisin", callback_data="home:back"))
    return kb.as_markup()


def render_home_header() -> str:
    return "Tekemättömät tehtävät\n\n"


def render_edit_header() -> str:
    return "Muokkausnäkymä"
