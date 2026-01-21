from __future__ import annotations

from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.ui import (
    add_task_category_kb,
    add_task_difficulty_kb,
    add_task_type_kb,
    default_kb,
    edit_kb,
    render_add_category_header,
    render_add_difficulty_header,
    render_add_type_header,
    render_default_header,
    render_edit_header,
    render_settings_header,
    render_stats_header,
    settings_kb,
    stats_kb,
)

router = Router()


class Flow(StatesGroup):
    waiting_new_task_text = State()
    waiting_edit_task_text = State()
    waiting_task_type = State()
    waiting_task_difficulty = State()
    waiting_task_difficulty_custom = State()
    waiting_task_category = State()
    waiting_task_deadline = State()
    waiting_task_scheduled = State()


@dataclass(frozen=True)
class CtxKeys:
    edit_task_id: str = "edit_task_id"
    add_task_type: str = "add_task_type"
    add_task_difficulty: str = "add_task_difficulty"
    add_task_category: str = "add_task_category"
    add_task_text: str = "add_task_text"
    add_task_deadline: str = "add_task_deadline"
    add_task_scheduled: str = "add_task_scheduled"


async def _show_home_from_message(message: Message, repo: TasksRepo) -> None:
    """Show default home view from message"""
    completed = await repo.list_completed_tasks(user_id=message.from_user.id, limit=3)
    active = await repo.list_tasks(user_id=message.from_user.id, limit=7)
    await message.answer(render_default_header(), reply_markup=default_kb(completed, active))


async def _show_home_from_cb(cb: CallbackQuery, repo: TasksRepo) -> None:
    """Show default home view from callback"""
    completed = await repo.list_completed_tasks(user_id=cb.from_user.id, limit=3)
    active = await repo.list_tasks(user_id=cb.from_user.id, limit=7)
    if cb.message:
        await cb.message.edit_text(render_default_header(), reply_markup=default_kb(completed, active))
    await cb.answer()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    await _show_home_from_message(message, repo)


@router.callback_query(F.data == "view:home")
async def cb_home(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    await _show_home_from_cb(cb, repo)


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data == "view:settings")
async def cb_settings(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    if cb.message:
        await cb.message.edit_text(render_settings_header(), reply_markup=settings_kb())
    await cb.answer()


@router.callback_query(F.data == "settings:reset")
async def cb_reset(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    await repo.reset_all_data(user_id=cb.from_user.id)
    if cb.message:
        await cb.message.edit_text("✅ Kaikki tiedot nollattu.", reply_markup=settings_kb())
    await cb.answer("Tiedot nollattu")


@router.callback_query(F.data == "view:edit")
async def cb_edit_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    tasks = await repo.list_tasks(user_id=cb.from_user.id, limit=10)
    if cb.message:
        await cb.message.edit_text(render_edit_header(), reply_markup=edit_kb(tasks))
    await cb.answer()


@router.callback_query(F.data == "view:stats")
async def cb_stats_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    if cb.message:
        await cb.message.edit_text("Tilastot\n\nValitse ajanjakso analyysille.", reply_markup=stats_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("stats:"))
async def cb_stats_period(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    _, days_str = cb.data.split(":", 1)
    try:
        days = int(days_str)
    except ValueError:
        await cb.answer("Virheellinen ajanjakso.", show_alert=True)
        return
    
    stats = await repo.get_statistics(user_id=cb.from_user.id, days=days)
    if cb.message:
        await cb.message.edit_text(render_stats_header(stats), reply_markup=stats_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("completed:restore:"))
async def cb_restore_completed(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    _, _, event_id_str = cb.data.split(":", 2)
    try:
        event_id = int(event_id_str)
    except ValueError:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return
    
    success = await repo.restore_completed_task(user_id=cb.from_user.id, event_id=event_id)
    if success:
        await _show_home_from_cb(cb, repo)
        await cb.answer("Tehtävä palautettu listalle")
    else:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)


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
    await _show_home_from_cb(cb, repo)


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


@router.callback_query(F.data == "view:add")
async def cb_add_task(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.set_state(Flow.waiting_task_type)
    if cb.message:
        await cb.message.edit_text(render_add_type_header(), reply_markup=add_task_type_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("add:type:"))
async def cb_add_type(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    _, _, task_type = cb.data.split(":", 2)
    await state.update_data({CtxKeys.add_task_type: task_type})
    await state.set_state(Flow.waiting_new_task_text)
    
    if cb.message:
        await cb.message.answer(
            f"Tehtävätyyppi: {task_type}\n\nKirjoita tehtävän teksti viestinä."
        )
    await cb.answer()


@router.callback_query(F.data.startswith("add:difficulty:"))
async def cb_add_difficulty(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    _, _, difficulty_str = cb.data.split(":", 2)
    
    if difficulty_str == "custom":
        await state.set_state(Flow.waiting_task_difficulty_custom)
        if cb.message:
            await cb.message.answer("Kirjoita haastavuus prosentteina (esim. 15):")
    else:
        try:
            difficulty = int(difficulty_str)
            await state.update_data({CtxKeys.add_task_difficulty: difficulty})
            await state.set_state(Flow.waiting_task_category)
            data = await state.get_data()
            task_text = data.get(CtxKeys.add_task_text, '')
            if cb.message:
                await cb.message.edit_text(
                    f"Tehtävä: {task_text}\n\n" + render_add_category_header(),
                    reply_markup=add_task_category_kb()
                )
        except ValueError:
            await cb.answer("Virheellinen haastavuus.", show_alert=True)
            return
    
    await cb.answer()


@router.callback_query(F.data.startswith("add:category:"))
async def cb_add_category(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    _, _, category = cb.data.split(":", 2)
    data = await state.get_data()
    
    task_type = data.get(CtxKeys.add_task_type, 'regular')
    difficulty = data.get(CtxKeys.add_task_difficulty, 5)
    task_text = data.get(CtxKeys.add_task_text)
    
    if not task_text:
        await cb.answer("Virhe: tehtävän teksti puuttuu.", show_alert=True)
        return
    
    # We have all the data, add the task
    await repo.add_task(
        user_id=cb.from_user.id,
        text=task_text,
        task_type=task_type,
        difficulty=difficulty,
        category=category
    )
    await state.clear()
    await _show_home_from_cb(cb, repo)
    await cb.answer("Tehtävä lisätty")


@router.message(Flow.waiting_new_task_text)
async def msg_new_task(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Tyhjä tehtävä ei kelpaa. Kirjoita tehtävä viestinä.")
        return

    data = await state.get_data()
    
    # Check if we're in the add task flow
    if CtxKeys.add_task_type in data:
        # Store text and continue to difficulty selection
        await state.update_data({CtxKeys.add_task_text: text})
        await state.set_state(Flow.waiting_task_difficulty)
        await message.answer(render_add_difficulty_header(), reply_markup=add_task_difficulty_kb())
        return
    
    # This is edit task flow
    task_id = data.get(CtxKeys.edit_task_id)
    if isinstance(task_id, int):
        await repo.update_task(user_id=message.from_user.id, task_id=task_id, new_text=text)
        await state.clear()
        await _show_home_from_message(message, repo)
        return
    
    # Fallback: add as regular task (shouldn't happen in normal flow)
    await repo.add_task(
        user_id=message.from_user.id,
        text=text,
        task_type='regular',
        difficulty=5,
        category=''
    )
    await state.clear()
    await _show_home_from_message(message, repo)


@router.message(Flow.waiting_task_difficulty_custom)
async def msg_custom_difficulty(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    text = (message.text or "").strip()
    try:
        difficulty = int(text)
        if difficulty < 1 or difficulty > 100:
            await message.answer("Haastavuuden tulee olla 1-100 prosenttia.")
            return
    except ValueError:
        await message.answer("Kirjoita numero (esim. 15).")
        return
    
    await state.update_data({CtxKeys.add_task_difficulty: difficulty})
    await state.set_state(Flow.waiting_task_category)
    data = await state.get_data()
    task_text = data.get(CtxKeys.add_task_text, '')
    await message.answer(
        f"Tehtävä: {task_text}\n\n" + render_add_category_header(),
        reply_markup=add_task_category_kb()
    )


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
    """Default: any text message = new task (by default)"""
    if message.text and message.text.startswith("/"):
        await _show_home_from_message(message, repo)
        return

    text = (message.text or "").strip()
    if not text:
        await _show_home_from_message(message, repo)
        return

    # Add as regular task with defaults
    await repo.add_task(
        user_id=message.from_user.id,
        text=text,
        task_type='regular',
        difficulty=5,
        category=''
    )
    await state.clear()
    await _show_home_from_message(message, repo)
