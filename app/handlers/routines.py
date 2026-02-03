"""
Routine (aamu/ilta) edit and add FSM handlers.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.handlers.common import CtxKeys, Flow
from app.ui import routine_list_edit_kb, render_routine_list_edit_header

router = Router()


async def start_edit_routine_task(
    cb: CallbackQuery,
    state: FSMContext,
    repo: TasksRepo,
    routine_type: str,
    task_id: int,
) -> None:
    """Ask for new text and set state waiting_routine_edit_text."""
    await state.set_state(Flow.waiting_routine_edit_text)
    await state.update_data(
        routine_type=routine_type,
        routine_task_id=task_id,
    )
    if cb.message:
        await cb.message.edit_text(
            "Kirjoita uusi teksti rutiinille:\n\nLähetä tyhjä viesti tai /peruuta peruuttaaksesi."
        )
    await cb.answer()


async def start_add_routine_task(
    cb: CallbackQuery,
    state: FSMContext,
    repo: TasksRepo,
    routine_type: str,
) -> None:
    """Ask for new routine name and set state waiting_routine_add_text."""
    await state.set_state(Flow.waiting_routine_add_text)
    await state.update_data(routine_type=routine_type)
    if cb.message:
        await cb.message.edit_text(
            "Kirjoita uusi rutiinin nimi:\n\nLähetä tyhjä viesti tai /peruuta peruuttaaksesi."
        )
    await cb.answer()


@router.message(Flow.waiting_routine_edit_text, F.text)
async def msg_routine_edit_text(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle routine task edit text submission."""
    text = (message.text or "").strip()
    if not text or text.lower() in ("/peruuta", "/cancel", "/peru"):
        from app.handlers.common import return_to_main_menu
        await return_to_main_menu(message, repo, state=state)
        return
    data = await state.get_data()
    routine_type = data.get(CtxKeys.routine_type) or "morning"
    task_id = data.get(CtxKeys.routine_task_id)
    if task_id is None:
        await state.clear()
        await message.answer("Virhe: tunniste puuttuu.")
        return
    success = await repo.update_routine_task(message.from_user.id, int(task_id), text)
    await state.clear()
    tasks = await repo.list_routine_tasks(message.from_user.id, routine_type)
    await message.answer(
        render_routine_list_edit_header(routine_type),
        reply_markup=routine_list_edit_kb(routine_type, tasks),
    )
    if not success:
        await message.answer("Virhe: rutiinia ei voitu päivittää.")


@router.message(Flow.waiting_routine_add_text, F.text)
async def msg_routine_add_text(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle new routine task name submission."""
    text = (message.text or "").strip()
    if not text or text.lower() in ("/peruuta", "/cancel", "/peru"):
        from app.handlers.common import return_to_main_menu
        await return_to_main_menu(message, repo, state=state)
        return
    data = await state.get_data()
    routine_type = data.get(CtxKeys.routine_type) or "morning"
    await repo.add_routine_task(message.from_user.id, routine_type, text)
    await state.clear()
    tasks = await repo.list_routine_tasks(message.from_user.id, routine_type)
    await message.answer(
        render_routine_list_edit_header(routine_type),
        reply_markup=routine_list_edit_kb(routine_type, tasks),
    )
