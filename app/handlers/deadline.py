"""
Deadline flow handlers for setting deadlines on tasks.

ROUTER MAP:
- task:deadline:<task_id> - Start deadline flow for existing task
- add:deadline:date:<offset> - Select deadline date (for new task)
- add:deadline:time:<time> - Select deadline time (for new task)
- deadline:date:<offset> - Select deadline date (for existing task)
- deadline:time:<time> - Select deadline time (for existing task)
- deadline:custom_time - Custom time input
- deadline:back - Back in deadline flow
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.handlers.common import CtxKeys, Flow, return_to_main_menu
from app.handlers.helpers import handle_time_back_custom, save_deadline_from_time, validate_required_fields
from app.priority import render_title_with_priority
from app.utils import (
    combine_date_time,
    format_datetime_iso,
    get_date_offset_days,
    parse_callback_data,
    parse_int_safe,
    parse_time_input,
    parse_time_string,
)
from app.ui import date_picker_kb, time_picker_kb

router = Router()


# Deadline flow for existing tasks
@router.callback_query(F.data.startswith("task:deadline:"))
async def cb_deadline_start(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start deadline flow - show date picker"""
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    await state.set_state(Flow.waiting_deadline_date)
    await state.update_data({CtxKeys.deadline_task_id: task_id})
    
    if cb.message:
        task_title = render_title_with_priority(task.text, task.priority)
        await cb.message.edit_text(
            f"⏰ Määräaika\n\nTehtävä: {task_title}\n\nValitse päivä:",
            reply_markup=date_picker_kb("deadline:date")
        )
    await cb.answer()


@router.callback_query(F.data.startswith("deadline:date:"))
async def cb_deadline_date(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle deadline date selection"""
    parts = parse_callback_data(cb.data, 3)
    date_option = parts[2] if parts else None
    if not date_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        return
    
    data = await validate_required_fields(cb, state, repo, deadline_task_id=int)
    if not data:
        return
    
    task_id = data[CtxKeys.deadline_task_id]
    
    if date_option == "none":
        await repo.clear_deadline(task_id=task_id, user_id=cb.from_user.id)
        await return_to_main_menu(cb, repo, state=state, answer_text="Määräaika poistettu", force_refresh=True)
        return
    
    date_offset = parse_int_safe(date_option)
    if date_offset is None:
        await cb.answer("Virheellinen päivä.", show_alert=True)
        return
    
    await state.update_data({CtxKeys.deadline_date_offset: date_offset})
    await state.set_state(Flow.waiting_deadline_time)
    
    if cb.message:
        await cb.message.edit_text("⏰ Määräaika\n\nValitse aika:", reply_markup=time_picker_kb("deadline:time"))
    await cb.answer()


@router.callback_query(F.data.startswith("deadline:time:"))
async def cb_deadline_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle deadline time selection"""
    parts = parse_callback_data(cb.data, 3)
    time_option = parts[2] if parts else None
    if not time_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        return
    
    data = await validate_required_fields(cb, state, repo, deadline_task_id=int, deadline_date_offset=int)
    if not data:
        return
    
    task_id = data[CtxKeys.deadline_task_id]
    date_offset = data[CtxKeys.deadline_date_offset]
    
    # Handle back/custom
    if time_option == "back":
        await state.set_state(Flow.waiting_deadline_date)
        if cb.message:
            task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
            task_title = render_title_with_priority(task.text, task.priority) if task else "Tehtävä"
            await cb.message.edit_text(
                f"⏰ Määräaika\n\nTehtävä: {task_title}\n\nValitse päivä:",
                reply_markup=date_picker_kb("deadline:date")
            )
        await cb.answer()
        return
    
    if time_option == "custom":
        await state.set_state(Flow.waiting_deadline_custom_time)
        if cb.message:
            await cb.message.answer("Kirjoita aika muodossa HHMM tai HH:MM (esim. 0930 tai 09:30):")
        await cb.answer()
        return
    
    # Save deadline
    await save_deadline_from_time(cb, state, repo, task_id, date_offset, time_option)


@router.message(Flow.waiting_deadline_custom_time)
async def msg_deadline_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for deadline (existing task)"""
    time_str = parse_time_input((message.text or "").strip())
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.deadline_task_id)
    date_offset = data.get(CtxKeys.deadline_date_offset)
    
    if not isinstance(task_id, int) or date_offset is None:
        await return_to_main_menu(message, repo, state=state)
        return
    
    date_dt = get_date_offset_days(date_offset)
    deadline_iso = format_datetime_iso(combine_date_time(date_dt, time_str))
    
    success = await repo.set_deadline(task_id=task_id, user_id=message.from_user.id, deadline_utc=deadline_iso)
    if success:
        await return_to_main_menu(message, repo, state=state)
    else:
        await message.answer("Virhe: määräaikaa ei voitu asettaa.")
        await return_to_main_menu(message, repo, state=state)


# Deadline flow for adding new tasks
@router.callback_query(F.data.startswith("add:deadline:date:"))
async def cb_add_deadline_date(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle deadline date selection when adding task"""
    parts = parse_callback_data(cb.data, 4)
    date_option = parts[3] if parts else None
    data = await state.get_data()
    
    date_offset = parse_int_safe(date_option)
    if date_offset is None:
        await cb.answer("Virheellinen päivä.", show_alert=True)
        return
    
    await state.update_data({CtxKeys.add_deadline_date_offset: date_offset})
    await state.set_state(Flow.waiting_task_deadline)
    
    if cb.message:
        await cb.message.edit_text("⏰ Määräaika\n\nValitse aika:", reply_markup=time_picker_kb("add:deadline:time"))
    await cb.answer()


@router.callback_query(F.data.startswith("add:deadline:time:"))
async def cb_add_deadline_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle deadline time selection when adding task"""
    from app.handlers.common import Flow
    
    parts = parse_callback_data(cb.data, 4)
    time_option = parts[3] if parts else None
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_deadline_date_offset)
    
    if date_offset is None or not time_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    if time_option == "back":
        # Go back to date selection
        from app.ui import date_picker_kb
        if cb.message:
            await cb.message.edit_text(
                "⏰ Määräaikainen tehtävä\n\nValitse päivämäärä:",
                reply_markup=date_picker_kb("add:deadline:date")
            )
        await cb.answer()
        return
    
    if time_option == "custom":
        # Store that we're waiting for custom time input
        await state.set_state(Flow.waiting_task_deadline)
        if cb.message:
            await cb.message.answer("Kirjoita aika muodossa HHMM tai HH:MM (esim. 0930 tai 09:30):")
        await cb.answer()
        return
    
    # Store time and move to text input state
    await state.update_data({CtxKeys.add_deadline_time: time_option})
    await state.set_state(Flow.waiting_deadline_text)
    
    if cb.message:
        await cb.message.answer("Kirjoita tehtävän teksti viestinä:")
    await cb.answer()


@router.message(Flow.waiting_task_deadline)
async def msg_add_deadline_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for deadline when adding task"""
    time_str = parse_time_input((message.text or "").strip())
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    # Store time and move to text input state
    await state.update_data({CtxKeys.add_deadline_time: time_str})
    await state.set_state(Flow.waiting_deadline_text)
    
    await message.answer("Kirjoita tehtävän teksti viestinä:")


@router.message(Flow.waiting_deadline_text)
async def msg_add_deadline_text(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle text input for deadline task (after date/time selection)"""
    from app.handlers.common import return_to_main_menu
    
    task_text = (message.text or "").strip()
    if not task_text:
        await message.answer("Tyhjä tehtävä ei kelpaa. Kirjoita tehtävä viestinä.")
        return
    
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_deadline_date_offset)
    time_str = data.get(CtxKeys.add_deadline_time)
    
    if date_offset is None or not time_str:
        await message.answer("Virhe: päivämäärä tai aika puuttuu.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    date_dt = get_date_offset_days(date_offset)
    deadline_iso = format_datetime_iso(combine_date_time(date_dt, time_str))
    
    await repo.add_task(
        user_id=message.from_user.id,
        text=task_text,
        task_type='deadline',
        difficulty=5,
        category='',
        deadline=deadline_iso
    )
    await return_to_main_menu(message, repo, state=state, answer_text="Tehtävä lisätty", force_refresh=True)
