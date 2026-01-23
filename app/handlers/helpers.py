"""
Helper functions for handlers to reduce code duplication.
"""
from __future__ import annotations

from typing import Any, Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.db import TasksRepo
from app.handlers.common import _show_home_from_cb
from app.utils import combine_date_time, format_datetime_iso, get_date_offset_days, parse_time_string


async def validate_required_fields(
    cb: CallbackQuery,
    state: FSMContext,
    repo: TasksRepo,
    **fields: Any
) -> Optional[dict]:
    """Validate required fields from state. Returns data if valid, None otherwise."""
    data = await state.get_data()
    for key, expected_type in fields.items():
        value = data.get(key)
        if value is None or (expected_type is not None and not isinstance(value, expected_type)):
            await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
            await state.clear()
            await _show_home_from_cb(cb, repo)
            return None
    return data


async def handle_time_back_custom(
    cb: CallbackQuery,
    state: FSMContext,
    time_option: str,
    back_state: Any,
    back_text: str,
    back_kb: Any,
    custom_state: Any,
    custom_prompt: str
) -> bool:
    """Handle 'back' or 'custom' time option. Returns True if handled."""
    if time_option == "back":
        await state.set_state(back_state)
        if cb.message:
            await cb.message.edit_text(back_text, reply_markup=back_kb)
        await cb.answer()
        return True
    
    if time_option == "custom":
        await state.set_state(custom_state)
        if cb.message:
            await cb.message.answer(custom_prompt)
        await cb.answer()
        return True
    
    return False


async def save_deadline_from_time(
    cb: CallbackQuery,
    state: FSMContext,
    repo: TasksRepo,
    task_id: int,
    date_offset: int,
    time_str: str
) -> bool:
    """Save deadline from time string. Returns True if successful."""
    if not parse_time_string(time_str):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return False
    
    date_dt = get_date_offset_days(date_offset)
    deadline_iso = format_datetime_iso(combine_date_time(date_dt, time_str))
    
    success = await repo.set_deadline(task_id=task_id, user_id=cb.from_user.id, deadline_utc=deadline_iso)
    if success:
        await state.clear()
        await _show_home_from_cb(cb, repo, answer_text="Määräaika asetettu")
        return True
    else:
        await cb.answer("Virhe: määräaikaa ei voitu asettaa.", show_alert=True)
        return False


async def save_schedule_at_time(
    cb: CallbackQuery,
    state: FSMContext,
    repo: TasksRepo,
    task_id: int,
    date_offset: int,
    time_str: str
) -> bool:
    """Save schedule 'at_time' from time string. Returns True if successful."""
    if not parse_time_string(time_str):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return False
    
    date_dt = get_date_offset_days(date_offset)
    schedule_payload = {"timestamp": format_datetime_iso(combine_date_time(date_dt, time_str))}
    
    success = await repo.set_schedule(task_id=task_id, user_id=cb.from_user.id, schedule_kind="at_time", schedule_payload=schedule_payload)
    if success:
        await state.clear()
        await _show_home_from_cb(cb, repo, answer_text="Aikataulu asetettu")
        return True
    else:
        await cb.answer("Virhe: aikataulua ei voitu asettaa.", show_alert=True)
        return False


async def save_schedule_time_range(
    cb: CallbackQuery,
    state: FSMContext,
    repo: TasksRepo,
    task_id: int,
    date_offset: int,
    start_time: str,
    end_time: str
) -> bool:
    """Save schedule 'time_range'. Returns True if successful."""
    if not parse_time_string(start_time) or not parse_time_string(end_time):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return False
    
    date_dt = get_date_offset_days(date_offset)
    schedule_payload = {
        "start_time": format_datetime_iso(combine_date_time(date_dt, start_time)),
        "end_time": format_datetime_iso(combine_date_time(date_dt, end_time))
    }
    
    success = await repo.set_schedule(task_id=task_id, user_id=cb.from_user.id, schedule_kind="time_range", schedule_payload=schedule_payload)
    if success:
        await state.clear()
        await _show_home_from_cb(cb, repo, answer_text="Aikataulu asetettu")
        return True
    else:
        await cb.answer("Virhe: aikataulua ei voitu asettaa.", show_alert=True)
        return False


async def add_task_with_deadline(
    cb: CallbackQuery,
    state: FSMContext,
    repo: TasksRepo,
    data: dict,
    date_offset: int,
    time_str: str
) -> bool:
    """Add task with deadline. Returns True if successful."""
    from app.handlers.common import CtxKeys
    
    if not parse_time_string(time_str):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return False
    
    task_text = data.get(CtxKeys.add_task_text)
    if not task_text:
        await cb.answer("Virhe: tehtävän teksti puuttuu.", show_alert=True)
        return False
    
    date_dt = get_date_offset_days(date_offset)
    deadline_iso = format_datetime_iso(combine_date_time(date_dt, time_str))
    
    await repo.add_task(
        user_id=cb.from_user.id,
        text=task_text,
        task_type=data.get(CtxKeys.add_task_type, 'regular'),
        difficulty=data.get(CtxKeys.add_task_difficulty, 5),
        category=data.get(CtxKeys.add_task_category, ''),
        deadline=deadline_iso
    )
    await state.clear()
    await _show_home_from_cb(cb, repo, answer_text="Tehtävä lisätty", force_refresh=True)
    return True


async def add_task_with_schedule(
    cb: CallbackQuery,
    state: FSMContext,
    repo: TasksRepo,
    data: dict,
    date_offset: int,
    time_str: str
) -> bool:
    """Add task with schedule. Returns True if successful."""
    from app.handlers.common import CtxKeys
    
    if not parse_time_string(time_str):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return False
    
    task_text = data.get(CtxKeys.add_task_text)
    if not task_text:
        await cb.answer("Virhe: tehtävän teksti puuttuu.", show_alert=True)
        return False
    
    date_dt = get_date_offset_days(date_offset)
    schedule_payload = {"timestamp": format_datetime_iso(combine_date_time(date_dt, time_str))}
    
    task_id = await repo.add_task(
        user_id=cb.from_user.id,
        text=task_text,
        task_type=data.get(CtxKeys.add_task_type, 'regular'),
        difficulty=data.get(CtxKeys.add_task_difficulty, 5),
        category=data.get(CtxKeys.add_task_category, '')
    )
    
    await repo.set_schedule(task_id=task_id, user_id=cb.from_user.id, schedule_kind="at_time", schedule_payload=schedule_payload)
    await state.clear()
    await _show_home_from_cb(cb, repo, answer_text="Tehtävä lisätty", force_refresh=True)
    return True
