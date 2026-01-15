from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def tasks_list_kb(items: list[dict]) -> InlineKeyboardMarkup:
    """
    items: [{"job_id": "...", "title": "..."}]
    """
    kb = InlineKeyboardBuilder()
    for it in items:
        job_id = it["job_id"]
        title = it["title"] or "(tyhjä)"

        kb.button(text=title, callback_data=f"td:done:{job_id}")
        kb.button(text="✏️", callback_data=f"td:edit:{job_id}")
        kb.button(text="🗑️", callback_data=f"td:del:{job_id}")
        kb.adjust(3)

    return kb.as_markup()
