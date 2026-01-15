from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any


class OwnerOnlyMiddleware(BaseMiddleware):
    def __init__(self, owner_id: int):
        self._owner_id = owner_id

    async def __call__(self, handler: Callable, event, data: Dict[str, Any]):
        user_id = None
        chat_id = None

        if isinstance(event, Message):
            user_id = event.from_user.id
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            chat_id = event.message.chat.id if event.message else None

        if user_id != self._owner_id:
            print(f"[AUTH] blocked user_id={user_id} owner_id={self._owner_id} chat_id={chat_id}")
            # debug-vaiheessa voit myös vastata:
            if isinstance(event, Message):
                await event.answer("Not authorized (debug).")
            elif isinstance(event, CallbackQuery) and event.message:
                await event.answer("Not authorized (debug).", show_alert=True)
            return

        return await handler(event, data)
