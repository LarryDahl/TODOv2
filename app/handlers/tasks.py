"""
Task action handlers (done, delete, edit, restore).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.handlers.common import CtxKeys, Flow, _show_home_from_cb, _show_home_from_message
from app.priority import parse_priority, render_title_with_priority
from app.utils import parse_callback_data, parse_int_safe

router = Router()


@router.callback_query(F.data.startswith("completed:restore:"))
async def cb_restore_completed(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    parts = parse_callback_data(cb.data, 3)
    event_id = parse_int_safe(parts[2]) if parts else None
    
    if event_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return
    
    success = await repo.restore_completed_task(user_id=cb.from_user.id, event_id=event_id)
    if success:
        await _show_home_from_cb(cb, repo, answer_text="Tehtävä palautettu listalle")
    else:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)


@router.callback_query(F.data.startswith("task:done:"))
async def cb_done(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return

    await repo.complete_task(user_id=cb.from_user.id, task_id=task_id)
    await _show_home_from_cb(cb, repo)


@router.callback_query(F.data.startswith("task:del:"))
async def cb_delete(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return

    await repo.delete_task_with_log(user_id=cb.from_user.id, task_id=task_id)
    await _show_home_from_cb(cb, repo)


@router.callback_query(F.data.startswith("task:menu:"))
async def cb_task_menu(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show action menu for a task"""
    from app.ui import task_action_kb
    
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return
    
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        return
    
    if cb.message:
        task_title = render_title_with_priority(task.text, task.priority)
        await cb.message.edit_text(
            f"Tehtävä: {task_title}\n\nValitse toiminto:",
            reply_markup=task_action_kb(task)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("task:edit:"))
async def cb_edit(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return
    
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        return
    
    await state.update_data({CtxKeys.edit_task_id: task_id})
    await state.set_state(Flow.waiting_edit_task_text)
    
    if cb.message:
        task_title = render_title_with_priority(task.text, task.priority)
        await cb.message.edit_text(
            f"Muokkaa tehtävää:\n\nNykyinen: {task_title}\n\nKirjoita uusi teksti viestinä."
        )
    await cb.answer()


@router.message(Flow.waiting_edit_task_text)
async def msg_edit_task(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Tehtävän teksti ei voi olla tyhjä.")
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.edit_task_id)
    
    if not isinstance(task_id, int):
        await message.answer("Virhe: tehtävä-id puuttuu.")
        await state.clear()
        await _show_home_from_message(message, repo)
        return
    
    # Parse priority from text
    clean_text, priority = parse_priority(text)
    
    # Update task
    await repo.update_task(
        user_id=message.from_user.id,
        task_id=task_id,
        new_text=clean_text,
        priority=priority
    )
    
    await state.clear()
    await _show_home_from_message(message, repo)
