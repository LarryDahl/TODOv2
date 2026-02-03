"""
Schedule flow handlers for setting schedules on tasks.

ROUTER MAP:
- task:schedule:<task_id> - Start schedule flow for existing task
- add:scheduled:date:<offset> - Select scheduled date (for new task)
- add:scheduled:time:<time> - Select scheduled time (for new task)
- schedule:type:<kind> - Select schedule type (at_time/time_range/all_day)
- schedule:date:<offset> - Select schedule date (for existing task)
- schedule:time:<time> - Select schedule time (for existing task)
- schedule:time_range:start - Start time for time range
- schedule:time_range:end - End time for time range
- schedule:custom_time - Custom time input
- schedule:back - Back in schedule flow
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.handlers.common import CtxKeys, Flow, return_to_main_menu
from app.handlers.helpers import (
    handle_time_back_custom,
    save_schedule_at_time,
    save_schedule_time_range,
    validate_required_fields,
)
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
from app.ui import date_picker_kb, schedule_type_kb, time_picker_kb

router = Router()


# Schedule flow for existing tasks
@router.callback_query(F.data.startswith("task:schedule:"))
async def cb_schedule_start(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start schedule flow - show schedule type selection"""
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
    
    await state.set_state(Flow.waiting_schedule_type)
    await state.update_data({CtxKeys.schedule_task_id: task_id})
    
    if cb.message:
        task_title = render_title_with_priority(task.text, task.priority)
        await cb.message.edit_text(
            f"🗓 Aikataulu\n\nTehtävä: {task_title}\n\nValitse aikataulutyyppi:",
            reply_markup=schedule_type_kb()
        )
    await cb.answer()


@router.callback_query(F.data.startswith("schedule:type:"))
async def cb_schedule_type(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle schedule type selection"""
    parts = parse_callback_data(cb.data, 3)
    schedule_type = parts[2] if parts else "none"
    
    data = await validate_required_fields(cb, state, repo, schedule_task_id=int)
    if not data:
        return
    
    task_id = data[CtxKeys.schedule_task_id]
    
    if schedule_type == "none":
        await repo.clear_schedule(task_id=task_id, user_id=cb.from_user.id)
        await return_to_main_menu(cb, repo, state=state, answer_text="Aikataulu poistettu", force_refresh=True)
        return
    
    await state.update_data({CtxKeys.schedule_kind: schedule_type})
    await state.set_state(Flow.waiting_schedule_date)
    
    if cb.message:
        await cb.message.edit_text("🗓 Aikataulu\n\nValitse päivä:", reply_markup=date_picker_kb("schedule:date", include_none=False))
    await cb.answer()


@router.callback_query(F.data.startswith("schedule:date:"))
async def cb_schedule_date(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle schedule date selection"""
    parts = parse_callback_data(cb.data, 3)
    date_option = parts[2] if parts else None
    if not date_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        return
    
    data = await validate_required_fields(cb, state, repo, schedule_task_id=int, schedule_kind=str)
    if not data:
        return
    
    task_id = data[CtxKeys.schedule_task_id]
    schedule_kind = data[CtxKeys.schedule_kind]
    
    date_offset = parse_int_safe(date_option)
    if date_offset is None:
        await cb.answer("Virheellinen päivä.", show_alert=True)
        return
    
    await state.update_data({CtxKeys.schedule_date_offset: date_offset})
    
    if schedule_kind == "all_day":
        date_dt = get_date_offset_days(date_offset)
        schedule_payload = {"date": date_dt.strftime("%Y-%m-%d")}
        success = await repo.set_schedule(task_id=task_id, user_id=cb.from_user.id, schedule_kind="all_day", schedule_payload=schedule_payload)
        if success:
            await return_to_main_menu(cb, repo, state=state, answer_text="Aikataulu asetettu", force_refresh=True)
        else:
            await cb.answer("Virhe: aikataulua ei voitu asettaa.", show_alert=True)
            await return_to_main_menu(cb, repo, state=state)
        return
    
    if schedule_kind == "at_time":
        await state.set_state(Flow.waiting_schedule_time)
        if cb.message:
            await cb.message.edit_text("🗓 Aikataulu\n\nValitse aika:", reply_markup=time_picker_kb("schedule:time"))
        await cb.answer()
        return
    
    if schedule_kind == "time_range":
        await state.set_state(Flow.waiting_schedule_time_range_start)
        if cb.message:
            await cb.message.edit_text("🗓 Aikataulu\n\nValitse alkamisaika:", reply_markup=time_picker_kb("schedule:start"))
        await cb.answer()
        return


@router.callback_query(F.data.startswith("schedule:time:"))
async def cb_schedule_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle schedule time selection for 'at_time'"""
    parts = parse_callback_data(cb.data, 3)
    time_option = parts[2] if parts else None
    if not time_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        return
    
    data = await validate_required_fields(cb, state, repo, schedule_task_id=int, schedule_date_offset=int)
    if not data:
        return
    
    task_id = data[CtxKeys.schedule_task_id]
    date_offset = data[CtxKeys.schedule_date_offset]
    
    # Handle back/custom
    if await handle_time_back_custom(
        cb, state, time_option,
        Flow.waiting_schedule_date,
        "🗓 Aikataulu\n\nValitse päivä:",
        date_picker_kb("schedule:date", include_none=False),
        Flow.waiting_schedule_custom_time,
        "Kirjoita aika muodossa HHMM tai HH:MM (esim. 0930 tai 09:30):"
    ):
        return
    
    # Save schedule
    await save_schedule_at_time(cb, state, repo, task_id, date_offset, time_option)


@router.callback_query(F.data.startswith("schedule:start:"))
async def cb_schedule_start_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle start time selection for time range"""
    parts = parse_callback_data(cb.data, 3)
    time_option = parts[2] if parts else None
    if not time_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        return
    
    data = await validate_required_fields(cb, state, repo, schedule_task_id=int, schedule_date_offset=int)
    if not data:
        return
    
    # Handle back/custom
    if await handle_time_back_custom(
        cb, state, time_option,
        Flow.waiting_schedule_date,
        "🗓 Aikataulu\n\nValitse päivä:",
        date_picker_kb("schedule:date", include_none=False),
        Flow.waiting_schedule_time_range_start,
        "Kirjoita alkamisaika muodossa HHMM tai HH:MM (esim. 0930):"
    ):
        return
    
    # Parse and store start time
    if not parse_time_string(time_option):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return
    
    await state.update_data({CtxKeys.schedule_start_time: time_option})
    await state.set_state(Flow.waiting_schedule_time_range_end)
    
    if cb.message:
        await cb.message.edit_text("🗓 Aikataulu\n\nValitse päättymisaika:", reply_markup=time_picker_kb("schedule:end"))
    await cb.answer()


@router.callback_query(F.data.startswith("schedule:end:"))
async def cb_schedule_end_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle end time selection for time range"""
    parts = parse_callback_data(cb.data, 3)
    time_option = parts[2] if parts else None
    if not time_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        return
    
    data = await validate_required_fields(cb, state, repo, schedule_task_id=int, schedule_date_offset=int, schedule_start_time=str)
    if not data:
        return
    
    task_id = data[CtxKeys.schedule_task_id]
    date_offset = data[CtxKeys.schedule_date_offset]
    start_time = data[CtxKeys.schedule_start_time]
    
    # Handle back/custom
    if await handle_time_back_custom(
        cb, state, time_option,
        Flow.waiting_schedule_time_range_start,
        "🗓 Aikataulu\n\nValitse alkamisaika:",
        time_picker_kb("schedule:start"),
        Flow.waiting_schedule_time_range_end,
        "Kirjoita päättymisaika muodossa HHMM tai HH:MM (esim. 1800):"
    ):
        return
    
    # Save time range
    await save_schedule_time_range(cb, state, repo, task_id, date_offset, start_time, time_option)


@router.message(Flow.waiting_schedule_custom_time)
async def msg_schedule_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for 'at_time' schedule (existing task)"""
    time_str = parse_time_input((message.text or "").strip())
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    date_offset = data.get(CtxKeys.schedule_date_offset)
    
    if not isinstance(task_id, int) or date_offset is None:
        await return_to_main_menu(message, repo, state=state)
        return
    
    date_dt = get_date_offset_days(date_offset)
    schedule_payload = {"timestamp": format_datetime_iso(combine_date_time(date_dt, time_str))}
    
    success = await repo.set_schedule(task_id=task_id, user_id=message.from_user.id, schedule_kind="at_time", schedule_payload=schedule_payload)
    if success:
        await return_to_main_menu(message, repo, state=state)
    else:
        await message.answer("Virhe: aikataulua ei voitu asettaa.")
        await return_to_main_menu(message, repo, state=state)


@router.message(Flow.waiting_schedule_time_range_start)
async def msg_schedule_start_custom(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom start time input for time range"""
    text = (message.text or "").strip()
    time_str = parse_time_input(text)
    
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930).")
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    date_offset = data.get(CtxKeys.schedule_date_offset)
    
    if not isinstance(task_id, int) or date_offset is None:
        await return_to_main_menu(message, repo, state=state)
        return
    
    await state.update_data({CtxKeys.schedule_start_time: time_str})
    await state.set_state(Flow.waiting_schedule_time_range_end)
    await message.answer(
        "Valitse päättymisaika:",
        reply_markup=time_picker_kb("schedule:end")
    )


@router.message(Flow.waiting_schedule_time_range_end)
async def msg_schedule_end_custom(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom end time input for time range"""
    time_str = parse_time_input((message.text or "").strip())
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 1800).")
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    date_offset = data.get(CtxKeys.schedule_date_offset)
    start_time = data.get(CtxKeys.schedule_start_time)
    
    if not isinstance(task_id, int) or date_offset is None or not start_time:
        await return_to_main_menu(message, repo, state=state)
        return
    
    date_dt = get_date_offset_days(date_offset)
    schedule_payload = {
        "start_time": format_datetime_iso(combine_date_time(date_dt, start_time)),
        "end_time": format_datetime_iso(combine_date_time(date_dt, time_str))
    }
    
    success = await repo.set_schedule(task_id=task_id, user_id=message.from_user.id, schedule_kind="time_range", schedule_payload=schedule_payload)
    if success:
        await return_to_main_menu(message, repo, state=state)
    else:
        await message.answer("Virhe: aikataulua ei voitu asettaa.")
        await return_to_main_menu(message, repo, state=state)


# Schedule flow for adding new tasks
@router.callback_query(F.data.startswith("add:scheduled:date:"))
async def cb_add_scheduled_date(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle scheduled date selection when adding task"""
    parts = parse_callback_data(cb.data, 4)
    date_option = parts[3] if parts else None
    data = await state.get_data()
    
    date_offset = parse_int_safe(date_option)
    if date_offset is None:
        await cb.answer("Virheellinen päivä.", show_alert=True)
        return
    
    await state.update_data({CtxKeys.add_scheduled_date_offset: date_offset})
    await state.set_state(Flow.waiting_task_scheduled)
    
    if cb.message:
        await cb.message.edit_text(
            "🗓 Aikataulu\n\nValitse aika:",
            reply_markup=time_picker_kb("add:scheduled:time")
        )
    await cb.answer()


@router.callback_query(F.data.startswith("add:scheduled:time:"))
async def cb_add_scheduled_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle scheduled time selection when adding task"""
    from app.handlers.common import Flow
    
    parts = parse_callback_data(cb.data, 4)
    time_option = parts[3] if parts else None
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_scheduled_date_offset)
    
    if date_offset is None:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    if time_option == "back":
        # Go back to date selection
        from app.ui import date_picker_kb
        if cb.message:
            await cb.message.edit_text(
                "🗓 Ajastettu tehtävä\n\nValitse päivämäärä:",
                reply_markup=date_picker_kb("add:scheduled:date", include_none=False)
            )
        await cb.answer()
        return
    
    if time_option == "custom":
        # Store that we're waiting for custom time input
        await state.set_state(Flow.waiting_task_scheduled)
        if cb.message:
            await cb.message.answer("Kirjoita aika muodossa HHMM tai HH:MM (esim. 0930 tai 09:30):")
        await cb.answer()
        return
    
    # Store time and move to text input state
    await state.update_data({CtxKeys.add_scheduled_time: time_option})
    await state.set_state(Flow.waiting_scheduled_text)
    
    if cb.message:
        await cb.message.answer("Kirjoita tehtävän teksti viestinä:")
    await cb.answer()


@router.message(Flow.waiting_task_scheduled)
async def msg_add_scheduled_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for scheduled when adding task"""
    time_str = parse_time_input((message.text or "").strip())
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    # Store time and move to text input state
    await state.update_data({CtxKeys.add_scheduled_time: time_str})
    await state.set_state(Flow.waiting_scheduled_text)
    
    await message.answer("Kirjoita tehtävän teksti viestinä:")


@router.message(Flow.waiting_scheduled_text)
async def msg_add_scheduled_text(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle text input for scheduled task (after date/time selection)"""
    from app.handlers.common import return_to_main_menu
    
    task_text = (message.text or "").strip()
    if not task_text:
        await message.answer("Tyhjä tehtävä ei kelpaa. Kirjoita tehtävä viestinä.")
        return
    
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_scheduled_date_offset)
    time_str = data.get(CtxKeys.add_scheduled_time)
    
    if date_offset is None or not time_str:
        await message.answer("Virhe: päivämäärä tai aika puuttuu.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    date_dt = get_date_offset_days(date_offset)
    schedule_payload = {"timestamp": format_datetime_iso(combine_date_time(date_dt, time_str))}
    
    task_id = await repo.add_task(
        user_id=message.from_user.id,
        text=task_text,
        task_type='scheduled',
        difficulty=5,
        category=''
    )
    
    await repo.set_schedule(task_id=task_id, user_id=message.from_user.id, schedule_kind="at_time", schedule_payload=schedule_payload)
    await return_to_main_menu(message, repo, state=state, answer_text="Tehtävä lisätty", force_refresh=True)
