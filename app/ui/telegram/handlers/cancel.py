from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery

from app.ui.telegram.utils.navigation import go_to_main_menu

router = Router()

CANCEL_WORDS = {"cancel", "peru", "peruuta", "stop"}


@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    await go_to_main_menu(message, state)

@router.message(F.text.casefold().in_(CANCEL_WORDS))
async def cancel_text(message: Message, state: FSMContext):
    await go_to_main_menu(message, state)

@router.callback_query(F.data == "cancel")
async def cancel_cb(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await cb.message.answer("Cancelled.", reply_markup=ReplyKeyboardRemove())
