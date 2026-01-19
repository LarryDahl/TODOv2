from __future__ import annotations

from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.ui import edit_list_kb, home_kb, render_edit_header, render_home_header

router = Router()


class Flow(StatesGroup):
    waiting_new_task_text = State()
    waiting_edit_task_text = State()


@dataclass(frozen=True)
class CtxKeys:
    edit_task_id: str = "edit_task_id"


async def _show_home_from_message(message: Message, repo: TasksRepo) -> None:
    tasks = await repo.list_tasks(user_id=message.from_user.id, limit=50)
    await message.answer(render_home_header(), reply_markup=home_kb(tasks))


async def _show_home_from_cb(cb: CallbackQuery, repo: TasksRepo) -> None:
    tasks = await repo.list_tasks(user_id=cb.from_user.id, limit=50)
    if cb.message:
        await cb.message.edit_text(render_home_header(), reply_markup=home_kb(tasks))
    await cb.answer()


async def _show_edit_list(cb: CallbackQuery, repo: TasksRepo) -> None:
    tasks = await repo.list_tasks(user_id=cb.from_user.id, limit=50)
    if cb.message:
        await cb.message.edit_text(render_edit_header(), reply_markup=edit_list_kb(tasks))
    await cb.answer()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    await _show_home_from_message(message, repo)


@router.callback_query(F.data == "home:back")
async def cb_back(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    await _show_home_from_cb(cb, repo)


@router.callback_query(F.data == "home:edit")
async def cb_home_edit(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    await _show_edit_list(cb, repo)


@router.callback_query(F.data == "home:add")
async def cb_home_add(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.set_state(Flow.waiting_new_task_text)
    if cb.message:
        await cb.message.answer("Kirjoita uusi tehtävä viestinä.")
    await cb.answer()


@router.callback_query(F.data.startswith("task:done:"))
async def cb_done(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    _, _, task_id_s = cb.data.split(":", 2)
    try:
        task_id = int(task_id_s)
    except ValueError:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return

    await repo.complete_task(user_id=cb.from_user.id, task_id=task_id)

    # Default UX: paluu kotilistaan aina
    await _show_home_from_cb(cb, repo)


@router.callback_query(F.data.startswith("task:del:"))
async def cb_delete(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    _, _, task_id_s = cb.data.split(":", 2)
    try:
        task_id = int(task_id_s)
    except ValueError:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return

    await repo.delete_task_with_log(user_id=cb.from_user.id, task_id=task_id)

    # Pysytään muokkausnäkymässä poiston jälkeen (kuten nytkin)
    await _show_edit_list(cb, repo)


@router.callback_query(F.data.startswith("task:edit:"))
async def cb_edit(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    _, _, task_id_s = cb.data.split(":", 2)
    try:
        task_id = int(task_id_s)
    except ValueError:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return

    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        return

    await state.set_state(Flow.waiting_edit_task_text)
    await state.update_data({CtxKeys.edit_task_id: task_id})
    if cb.message:
        await cb.message.answer(
            f"Muokkaa tehtävää:\n\nNykyinen:\n{task.text}\n\nKirjoita uusi teksti viestinä."
        )
    await cb.answer()


@router.message(Flow.waiting_new_task_text)
async def msg_new_task(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Tyhjä tehtävä ei kelpaa. Kirjoita tehtävä viestinä.")
        return

    await repo.add_task(user_id=message.from_user.id, text=text)
    await state.clear()
    await _show_home_from_message(message, repo)


@router.message(Flow.waiting_edit_task_text)
async def msg_edit_task(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Tyhjä teksti ei kelpaa. Kirjoita uusi teksti viestinä.")
        return

    data = await state.get_data()
    task_id = data.get(CtxKeys.edit_task_id)
    if not isinstance(task_id, int):
        await state.clear()
        await _show_home_from_message(message, repo)
        return

    await repo.update_task(user_id=message.from_user.id, task_id=task_id, new_text=text)
    await state.clear()
    await _show_home_from_message(message, repo)


@router.message()
async def msg_default_add_task(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    # Default UX: jokainen tavallinen viesti = uusi tehtävä
    if message.text and message.text.startswith("/"):
        await _show_home_from_message(message, repo)
        return

    text = (message.text or "").strip()
    if not text:
        await _show_home_from_message(message, repo)
        return

    await repo.add_task(user_id=message.from_user.id, text=text)
    await state.clear()
    await _show_home_from_message(message, repo)
