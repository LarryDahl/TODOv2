from __future__ import annotations

from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
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
from app.ui import (
    add_task_category_kb,
    add_task_difficulty_kb,
    add_task_type_kb,
    date_picker_kb,
    default_kb,
    deleted_tasks_kb,
    done_tasks_kb,
    edit_kb,
    render_add_category_header,
    render_add_difficulty_header,
    render_add_type_header,
    render_default_header,
    render_edit_header,
    render_settings_header,
    render_stats_header,
    schedule_type_kb,
    settings_kb,
    stats_kb,
    time_picker_kb,
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
    # Deadline flow states
    waiting_deadline_date = State()
    waiting_deadline_time = State()
    waiting_deadline_custom_time = State()
    # Schedule flow states
    waiting_schedule_type = State()
    waiting_schedule_date = State()
    waiting_schedule_time = State()
    waiting_schedule_time_range_start = State()
    waiting_schedule_time_range_end = State()
    waiting_schedule_custom_time = State()


@dataclass(frozen=True)
class CtxKeys:
    edit_task_id: str = "edit_task_id"
    add_task_type: str = "add_task_type"
    add_task_difficulty: str = "add_task_difficulty"
    add_task_category: str = "add_task_category"
    add_task_text: str = "add_task_text"
    add_task_deadline: str = "add_task_deadline"
    add_task_scheduled: str = "add_task_scheduled"
    # Deadline flow keys
    deadline_task_id: str = "deadline_task_id"
    deadline_date_offset: str = "deadline_date_offset"
    # Add task deadline/scheduled keys
    add_deadline_date_offset: str = "add_deadline_date_offset"
    add_scheduled_date_offset: str = "add_scheduled_date_offset"
    add_scheduled_kind: str = "add_scheduled_kind"
    # Schedule flow keys
    schedule_task_id: str = "schedule_task_id"
    schedule_kind: str = "schedule_kind"
    schedule_date_offset: str = "schedule_date_offset"
    schedule_time: str = "schedule_time"
    schedule_start_time: str = "schedule_start_time"


async def _show_home_from_message(message: Message, repo: TasksRepo) -> None:
    """Show default home view from message"""
    completed = await repo.list_completed_tasks(user_id=message.from_user.id, limit=3)
    active = await repo.list_tasks(user_id=message.from_user.id, limit=7)
    daily_progress = await repo.get_daily_progress(user_id=message.from_user.id)
    
    # Add separator text between lists if both exist
    header_text = render_default_header(daily_progress)
    if completed and active:
        header_text += "\n\n─────────────"
    
    await message.answer(header_text, reply_markup=default_kb(completed, active))


async def _show_home_from_cb(cb: CallbackQuery, repo: TasksRepo, answer_text: str | None = None, force_refresh: bool = False) -> None:
    """Show default home view from callback"""
    from aiogram.exceptions import TelegramBadRequest
    
    completed = await repo.list_completed_tasks(user_id=cb.from_user.id, limit=3)
    active = await repo.list_tasks(user_id=cb.from_user.id, limit=7)
    daily_progress = await repo.get_daily_progress(user_id=cb.from_user.id)
    
    # Add separator text between lists if both exist
    header_text = render_default_header(daily_progress)
    if completed and active:
        header_text += "\n\n─────────────"
    
    # If force refresh, add invisible character to force update
    if force_refresh:
        header_text += "\u200b"  # Zero-width space
    
    if cb.message:
        try:
            await cb.message.edit_text(header_text, reply_markup=default_kb(completed, active))
        except TelegramBadRequest as e:
            # If message is not modified and we're forcing refresh, try with reply_markup only
            if "message is not modified" in str(e).lower() and force_refresh:
                try:
                    # Force update by editing reply markup separately
                    await cb.message.edit_reply_markup(reply_markup=default_kb(completed, active))
                except Exception:
                    pass  # If still fails, just answer
            elif "message is not modified" in str(e).lower():
                pass  # Message is already up to date
            else:
                raise  # Re-raise other errors
        except Exception:
            pass  # Ignore other errors and just answer
    
    # Answer callback - use provided text or default
    if answer_text:
        await cb.answer(answer_text)
    else:
        await cb.answer()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    await _show_home_from_message(message, repo)


@router.callback_query(F.data == "view:home")
async def cb_home(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    # Force refresh to ensure list shows correct order after edits
    await _show_home_from_cb(cb, repo, force_refresh=True)


@router.callback_query(F.data == "view:refresh")
async def cb_refresh(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Refresh the main menu task list to show latest changes and approaching deadlines"""
    await state.clear()
    # Force refresh to ensure list updates visibly
    await _show_home_from_cb(cb, repo, answer_text="Lista päivitetty", force_refresh=True)


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
    tasks = await repo.list_tasks(user_id=cb.from_user.id)
    if cb.message:
        await cb.message.edit_text(render_edit_header(), reply_markup=edit_kb(tasks))
    await cb.answer()


@router.callback_query(F.data == "view:done")
async def cb_done_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show done tasks view"""
    await state.clear()
    tasks = await repo.list_done_tasks(user_id=cb.from_user.id, limit=50, offset=0)
    if cb.message:
        header = f"✅ Tehdyt tehtävät\n\nYhteensä: {len(tasks)} tehtävää"
        await cb.message.edit_text(header, reply_markup=done_tasks_kb(tasks, offset=0))
    await cb.answer()


@router.callback_query(F.data.startswith("done:page:"))
async def cb_done_page(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show next page of done tasks"""
    await state.clear()
    parts = parse_callback_data(cb.data, 3)
    offset = parse_int_safe(parts[2]) if parts else None
    
    if offset is None:
        await cb.answer("Virheellinen sivu.", show_alert=True)
        return
    
    tasks = await repo.list_done_tasks(user_id=cb.from_user.id, limit=50, offset=offset)
    if cb.message:
        await cb.message.edit_text(
            f"✅ Tehdyt tehtävät\n\nSivu {offset // 50 + 1}",
            reply_markup=done_tasks_kb(tasks, offset=offset)
        )
    await cb.answer()


@router.callback_query(F.data == "view:deleted")
async def cb_deleted_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show deleted tasks view"""
    await state.clear()
    tasks = await repo.list_deleted_tasks(user_id=cb.from_user.id, limit=50, offset=0)
    if cb.message:
        header = f"🗑 Poistetut tehtävät\n\nYhteensä: {len(tasks)} tehtävää\n\nKlikkaa 'Palauta' palauttaaksesi tehtävän."
        await cb.message.edit_text(header, reply_markup=deleted_tasks_kb(tasks, offset=0))
    await cb.answer()


@router.callback_query(F.data.startswith("deleted:page:"))
async def cb_deleted_page(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show next page of deleted tasks"""
    await state.clear()
    parts = parse_callback_data(cb.data, 3)
    offset = parse_int_safe(parts[2]) if parts else None
    
    if offset is None:
        await cb.answer("Virheellinen sivu.", show_alert=True)
        return
    
    tasks = await repo.list_deleted_tasks(user_id=cb.from_user.id, limit=50, offset=offset)
    if cb.message:
        await cb.message.edit_text(
            f"🗑 Poistetut tehtävät\n\nSivu {offset // 50 + 1}\n\nKlikkaa tehtävää palauttaaksesi sen.",
            reply_markup=deleted_tasks_kb(tasks, offset=offset)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("deleted:restore:"))
async def cb_restore_deleted(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Restore a deleted task"""
    await state.clear()
    parts = parse_callback_data(cb.data, 3)
    event_id = parse_int_safe(parts[2]) if parts else None
    
    if event_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return
    
    success = await repo.restore_deleted_task(user_id=cb.from_user.id, event_id=event_id)
    if success:
        tasks = await repo.list_deleted_tasks(user_id=cb.from_user.id, limit=50, offset=0)
        if cb.message:
            await cb.message.edit_text(
                f"🗑 Poistetut tehtävät\n\nYhteensä: {len(tasks)} tehtävää\n\nKlikkaa tehtävää palauttaaksesi sen.",
                reply_markup=deleted_tasks_kb(tasks, offset=0)
            )
        await cb.answer("Tehtävä palautettu")
    else:
        await cb.answer("Tehtävää ei voitu palauttaa.", show_alert=True)


@router.callback_query(F.data == "view:stats")
async def cb_stats_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    if cb.message:
        await cb.message.edit_text("Tilastot\n\nValitse ajanjakso analyysille.", reply_markup=stats_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("stats:"))
async def cb_stats_period(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    parts = cb.data.split(":", 1)
    days = parse_int_safe(parts[1] if len(parts) > 1 else "")
    
    if days is None:
        await cb.answer("Virheellinen ajanjakso.", show_alert=True)
        return
    
    stats = await repo.get_statistics(user_id=cb.from_user.id, days=days)
    if cb.message:
        await cb.message.edit_text(render_stats_header(stats), reply_markup=stats_kb())
    await cb.answer()


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


# Deadline flow handlers
@router.callback_query(F.data.startswith("task:deadline:"))
async def cb_deadline_start(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start deadline flow - show date picker"""
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        return
    
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
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
    data = await state.get_data()
    task_id = data.get(CtxKeys.deadline_task_id)
    
    if not isinstance(task_id, int) or not date_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await state.clear()
        await _show_home_from_cb(cb, repo)
        return
    
    if date_option == "none":
        await repo.clear_deadline(task_id=task_id, user_id=cb.from_user.id)
        await state.clear()
        await _show_home_from_cb(cb, repo, answer_text="Määräaika poistettu")
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
    data = await state.get_data()
    task_id = data.get(CtxKeys.deadline_task_id)
    date_offset = data.get(CtxKeys.deadline_date_offset)
    
    if not isinstance(task_id, int) or date_offset is None or not time_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await state.clear()
        await _show_home_from_cb(cb, repo)
        return
    
    if time_option == "back":
        # Go back to date selection
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
        # Request custom time input
        await state.set_state(Flow.waiting_deadline_custom_time)
        if cb.message:
            await cb.message.answer("Kirjoita aika muodossa HHMM tai HH:MM (esim. 0930 tai 09:30):")
        await cb.answer()
        return
    
    # Parse and save time
    if not parse_time_string(time_option):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return
    
    date_dt = get_date_offset_days(date_offset)
    deadline_dt = combine_date_time(date_dt, time_option)
    deadline_iso = format_datetime_iso(deadline_dt)
    
    success = await repo.set_deadline(task_id=task_id, user_id=cb.from_user.id, deadline_utc=deadline_iso)
    if success:
        await state.clear()
        await _show_home_from_cb(cb, repo, answer_text="Määräaika asetettu")
    else:
        await cb.answer("Virhe: määräaikaa ei voitu asettaa.", show_alert=True)


@router.message(Flow.waiting_deadline_custom_time)
async def msg_deadline_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for deadline (existing task)"""
    text = (message.text or "").strip()
    time_str = parse_time_input(text)
    
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.deadline_task_id)
    date_offset = data.get(CtxKeys.deadline_date_offset)
    
    if not isinstance(task_id, int) or date_offset is None:
        await state.clear()
        await _show_home_from_message(message, repo)
        return
    
    # Combine date and time
    date_dt = get_date_offset_days(date_offset)
    deadline_dt = combine_date_time(date_dt, time_str)
    deadline_iso = format_datetime_iso(deadline_dt)
    
    # Save deadline
    success = await repo.set_deadline(task_id=task_id, user_id=message.from_user.id, deadline_utc=deadline_iso)
    if success:
        await state.clear()
        await _show_home_from_message(message, repo)
    else:
        await message.answer("Virhe: määräaikaa ei voitu asettaa.")


@router.message(Flow.waiting_task_deadline)
async def msg_add_task_deadline_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for deadline when adding new task"""
    text = (message.text or "").strip()
    time_str = parse_time_input(text)
    
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_deadline_date_offset)
    
    if date_offset is None:
        await state.clear()
        await _show_home_from_message(message, repo)
        return
    
    # Combine date and time
    date_dt = get_date_offset_days(date_offset)
    deadline_dt = combine_date_time(date_dt, time_str)
    deadline_iso = format_datetime_iso(deadline_dt)
    
    # Add task with deadline
    task_type = data.get(CtxKeys.add_task_type, 'regular')
    difficulty = data.get(CtxKeys.add_task_difficulty, 5)
    task_text = data.get(CtxKeys.add_task_text)
    category = data.get(CtxKeys.add_task_category, '')
    
    if not task_text:
        await message.answer("Virhe: tehtävän teksti puuttuu.")
        return
    
    await repo.add_task(
        user_id=message.from_user.id,
        text=task_text,
        task_type=task_type,
        difficulty=difficulty,
        category=category,
        deadline=deadline_iso
    )
    await state.clear()
    await _show_home_from_message(message, repo)


# Schedule flow handlers
@router.callback_query(F.data.startswith("task:schedule:"))
async def cb_schedule_start(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start schedule flow - show schedule type selection"""
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
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    
    if not isinstance(task_id, int):
        await cb.answer("Virhe: tehtävä-id puuttuu.", show_alert=True)
        await state.clear()
        await _show_home_from_cb(cb, repo)
        return
    
    if schedule_type == "none":
        # Clear schedule
        await repo.clear_schedule(task_id=task_id, user_id=cb.from_user.id)
        await state.clear()
        await _show_home_from_cb(cb, repo, answer_text="Aikataulu poistettu")
        return
    
    await state.update_data({CtxKeys.schedule_kind: schedule_type})
    await state.set_state(Flow.waiting_schedule_date)
    
    if cb.message:
        await cb.message.edit_text(
            "🗓 Aikataulu\n\nValitse päivä:",
            reply_markup=date_picker_kb("schedule:date", include_none=False)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("schedule:date:"))
async def cb_schedule_date(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle schedule date selection"""
    parts = parse_callback_data(cb.data, 3)
    date_option = parts[2] if parts else None
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    schedule_kind = data.get(CtxKeys.schedule_kind)
    
    if not isinstance(task_id, int) or not schedule_kind:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await state.clear()
        await _show_home_from_cb(cb, repo)
        return
    
    date_offset = parse_int_safe(date_option)
    if date_offset is None:
        await cb.answer("Virheellinen päivä.", show_alert=True)
        return
    
    await state.update_data({CtxKeys.schedule_date_offset: date_offset})
    
    if schedule_kind == "all_day":
        # All day - just save the date
        date_dt = get_date_offset_days(date_offset)
        schedule_payload = {"date": date_dt.strftime("%Y-%m-%d")}
        success = await repo.set_schedule(
            task_id=task_id,
            user_id=cb.from_user.id,
            schedule_kind="all_day",
            schedule_payload=schedule_payload
        )
        if success:
            await state.clear()
            await _show_home_from_cb(cb, repo, answer_text="Aikataulu asetettu")
        else:
            await cb.answer("Virhe: aikataulua ei voitu asettaa.", show_alert=True)
        return
    
    if schedule_kind == "at_time":
        # At time - need time selection
        await state.set_state(Flow.waiting_schedule_time)
        if cb.message:
            await cb.message.edit_text(
                "🗓 Aikataulu\n\nValitse aika:",
                reply_markup=time_picker_kb("schedule:time")
            )
        await cb.answer()
        return
    
    if schedule_kind == "time_range":
        # Time range - need start time
        await state.set_state(Flow.waiting_schedule_time_range_start)
        if cb.message:
            await cb.message.edit_text(
                "🗓 Aikataulu\n\nValitse alkamisaika:",
                reply_markup=time_picker_kb("schedule:start")
            )
        await cb.answer()
        return


@router.callback_query(F.data.startswith("schedule:time:"))
async def cb_schedule_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle schedule time selection for 'at_time'"""
    parts = parse_callback_data(cb.data, 3)
    time_option = parts[2] if parts else None
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    date_offset = data.get(CtxKeys.schedule_date_offset)
    
    if not isinstance(task_id, int) or date_offset is None or not time_option:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await state.clear()
        await _show_home_from_cb(cb, repo)
        return
    
    if time_option == "back":
        # Go back to date selection
        await state.set_state(Flow.waiting_schedule_date)
        if cb.message:
            await cb.message.edit_text(
                "🗓 Aikataulu\n\nValitse päivä:",
                reply_markup=date_picker_kb("schedule:date", include_none=False)
            )
        await cb.answer()
        return
    
    if time_option == "custom":
        # Request custom time input
        await state.set_state(Flow.waiting_schedule_custom_time)
        if cb.message:
            await cb.message.answer("Kirjoita aika muodossa HHMM tai HH:MM (esim. 0930 tai 09:30):")
        await cb.answer()
        return
    
    # Parse and save time
    if not parse_time_string(time_option):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return
    
    date_dt = get_date_offset_days(date_offset)
    schedule_dt = combine_date_time(date_dt, time_option)
    schedule_payload = {"timestamp": format_datetime_iso(schedule_dt)}
    
    success = await repo.set_schedule(task_id=task_id, user_id=cb.from_user.id, schedule_kind="at_time", schedule_payload=schedule_payload)
    if success:
        await state.clear()
        await _show_home_from_cb(cb, repo, answer_text="Aikataulu asetettu")
    else:
        await cb.answer("Virhe: aikataulua ei voitu asettaa.", show_alert=True)


@router.callback_query(F.data.startswith("schedule:start:"))
async def cb_schedule_start_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle start time selection for time range"""
    _, _, time_option = cb.data.split(":", 2)
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    date_offset = data.get(CtxKeys.schedule_date_offset)
    
    if not isinstance(task_id, int) or date_offset is None:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await state.clear()
        await _show_home_from_cb(cb, repo)
        return
    
    if time_option == "back":
        # Go back to date selection
        await state.set_state(Flow.waiting_schedule_date)
        if cb.message:
            await cb.message.edit_text(
                "🗓 Aikataulu\n\nValitse päivä:",
                reply_markup=date_picker_kb("schedule:date", include_none=False)
            )
        await cb.answer()
        return
    
    if time_option == "custom":
        # Request custom time input for start
        await state.set_state(Flow.waiting_schedule_time_range_start)
        if cb.message:
            await cb.message.answer("Kirjoita alkamisaika muodossa HHMM tai HH:MM (esim. 0930):")
        await cb.answer()
        return
    
    # Parse time
    if not parse_time_string(time_option):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return
    
    await state.update_data({CtxKeys.schedule_start_time: time_option})
    await state.set_state(Flow.waiting_schedule_time_range_end)
    
    if cb.message:
        await cb.message.edit_text(
            "🗓 Aikataulu\n\nValitse päättymisaika:",
            reply_markup=time_picker_kb("schedule:end")
        )
    await cb.answer()


@router.callback_query(F.data.startswith("schedule:end:"))
async def cb_schedule_end_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle end time selection for time range"""
    parts = parse_callback_data(cb.data, 3)
    time_option = parts[2] if parts else None
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    date_offset = data.get(CtxKeys.schedule_date_offset)
    start_time = data.get(CtxKeys.schedule_start_time)
    
    if not isinstance(task_id, int) or date_offset is None or not start_time:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await state.clear()
        await _show_home_from_cb(cb, repo)
        return
    
    if time_option == "back":
        # Go back to start time selection
        await state.set_state(Flow.waiting_schedule_time_range_start)
        if cb.message:
            await cb.message.edit_text(
                "🗓 Aikataulu\n\nValitse alkamisaika:",
                reply_markup=time_picker_kb("schedule:start")
            )
        await cb.answer()
        return
    
    if time_option == "custom":
        # Request custom time input for end
        await state.set_state(Flow.waiting_schedule_time_range_end)
        if cb.message:
            await cb.message.answer("Kirjoita päättymisaika muodossa HHMM tai HH:MM (esim. 1800):")
        await cb.answer()
        return
    
    # Parse time
    if not parse_time_string(time_option):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return
    
    date_dt = get_date_offset_days(date_offset)
    start_dt = combine_date_time(date_dt, start_time)
    end_dt = combine_date_time(date_dt, time_option)
    
    schedule_payload = {
        "start_time": format_datetime_iso(start_dt),
        "end_time": format_datetime_iso(end_dt)
    }
    
    success = await repo.set_schedule(
        task_id=task_id,
        user_id=cb.from_user.id,
        schedule_kind="time_range",
        schedule_payload=schedule_payload
    )
    if success:
        await state.clear()
        await _show_home_from_cb(cb, repo, answer_text="Aikataulu asetettu")
    else:
        await cb.answer("Virhe: aikataulua ei voitu asettaa.", show_alert=True)


@router.message(Flow.waiting_schedule_custom_time)
async def msg_schedule_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for 'at_time' schedule (existing task)"""
    text = (message.text or "").strip()
    time_str = parse_time_input(text)
    
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    date_offset = data.get(CtxKeys.schedule_date_offset)
    
    if not isinstance(task_id, int) or date_offset is None:
        await state.clear()
        await _show_home_from_message(message, repo)
        return
    
    date_dt = get_date_offset_days(date_offset)
    schedule_dt = combine_date_time(date_dt, time_str)
    schedule_payload = {"timestamp": format_datetime_iso(schedule_dt)}
    
    success = await repo.set_schedule(
        task_id=task_id,
        user_id=message.from_user.id,
        schedule_kind="at_time",
        schedule_payload=schedule_payload
    )
    if success:
        await state.clear()
        await _show_home_from_message(message, repo)
    else:
        await message.answer("Virhe: aikataulua ei voitu asettaa.")


@router.message(Flow.waiting_task_scheduled)
async def msg_add_task_scheduled_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for scheduled when adding new task"""
    text = (message.text or "").strip()
    time_str = parse_time_input(text)
    
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_scheduled_date_offset)
    
    if date_offset is None:
        await state.clear()
        await _show_home_from_message(message, repo)
        return
    
    # Combine date and time
    date_dt = get_date_offset_days(date_offset)
    schedule_dt = combine_date_time(date_dt, time_str)
    schedule_payload = {"timestamp": format_datetime_iso(schedule_dt)}
    
    # Add task with schedule
    task_type = data.get(CtxKeys.add_task_type, 'regular')
    difficulty = data.get(CtxKeys.add_task_difficulty, 5)
    task_text = data.get(CtxKeys.add_task_text)
    category = data.get(CtxKeys.add_task_category, '')
    
    if not task_text:
        await message.answer("Virhe: tehtävän teksti puuttuu.")
        return
    
    # Create task first, then set schedule
    task_id = await repo.add_task(
        user_id=message.from_user.id,
        text=task_text,
        task_type=task_type,
        difficulty=difficulty,
        category=category
    )
    
    # Set schedule
    await repo.set_schedule(
        task_id=task_id,
        user_id=message.from_user.id,
        schedule_kind="at_time",
        schedule_payload=schedule_payload
    )
    
    await state.clear()
    await _show_home_from_message(message, repo)


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
        await state.clear()
        await _show_home_from_message(message, repo)
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
    text = (message.text or "").strip()
    time_str = parse_time_input(text)
    
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 1800).")
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.schedule_task_id)
    date_offset = data.get(CtxKeys.schedule_date_offset)
    start_time = data.get(CtxKeys.schedule_start_time)
    
    if not isinstance(task_id, int) or date_offset is None or not start_time:
        await state.clear()
        await _show_home_from_message(message, repo)
        return
    
    date_dt = get_date_offset_days(date_offset)
    schedule_payload = {
        "start_time": format_datetime_iso(combine_date_time(date_dt, start_time)),
        "end_time": format_datetime_iso(combine_date_time(date_dt, time_str))
    }
    
    success = await repo.set_schedule(task_id=task_id, user_id=message.from_user.id, schedule_kind="time_range", schedule_payload=schedule_payload)
    if success:
        await state.clear()
        await _show_home_from_message(message, repo)
    else:
        await message.answer("Virhe: aikataulua ei voitu asettaa.")


# Add task deadline/scheduled handlers
@router.callback_query(F.data.startswith("add:deadline:date:"))
async def cb_add_deadline_date(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle deadline date selection when adding task"""
    _, _, _, date_option = cb.data.split(":", 3)
    data = await state.get_data()
    
    if date_option == "none":
        # No deadline - add task immediately
        task_type = data.get(CtxKeys.add_task_type, 'regular')
        difficulty = data.get(CtxKeys.add_task_difficulty, 5)
        task_text = data.get(CtxKeys.add_task_text)
        category = data.get(CtxKeys.add_task_category, '')
        
        if not task_text:
            await cb.answer("Virhe: tehtävän teksti puuttuu.", show_alert=True)
            return
        
        await repo.add_task(
            user_id=cb.from_user.id,
            text=task_text,
            task_type=task_type,
            difficulty=difficulty,
            category=category
        )
        await state.clear()
        await _show_home_from_cb(cb, repo, answer_text="Tehtävä lisätty", force_refresh=True)
        return
    
    date_offset = parse_int_safe(date_option)
    if date_offset is None:
        await cb.answer("Virheellinen päivä.", show_alert=True)
        return
    
    await state.update_data({CtxKeys.add_deadline_date_offset: date_offset})
    await state.set_state(Flow.waiting_task_deadline)
    
    if cb.message:
        await cb.message.edit_text(
            "⏰ Määräaika\n\nValitse aika:",
            reply_markup=time_picker_kb("add:deadline:time")
        )
    await cb.answer()


@router.callback_query(F.data.startswith("add:deadline:time:"))
async def cb_add_deadline_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle deadline time selection when adding task"""
    _, _, _, time_option = cb.data.split(":", 3)
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_deadline_date_offset)
    
    if date_offset is None:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await state.clear()
        await _show_home_from_cb(cb, repo)
        return
    
    if time_option == "back":
        await state.set_state(Flow.waiting_task_deadline)
        if cb.message:
            task_text = data.get(CtxKeys.add_task_text, '')
            await cb.message.edit_text(
                f"Tehtävä: {task_text}\n\n⏰ Valitse määräaika:",
                reply_markup=date_picker_kb("add:deadline:date")
            )
        await cb.answer()
        return
    
    if time_option == "custom":
        # Keep same state for custom time input
        if cb.message:
            await cb.message.answer("Kirjoita aika muodossa HHMM tai HH:MM (esim. 0930 tai 09:30):")
        await cb.answer()
        return
    
    # Parse and add task with deadline
    if not parse_time_string(time_option):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return
    
    task_text = data.get(CtxKeys.add_task_text)
    if not task_text:
        await cb.answer("Virhe: tehtävän teksti puuttuu.", show_alert=True)
        return
    
    date_dt = get_date_offset_days(date_offset)
    deadline_iso = format_datetime_iso(combine_date_time(date_dt, time_option))
    
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


@router.message(Flow.waiting_task_deadline)
async def msg_add_deadline_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for deadline when adding task"""
    text = (message.text or "").strip()
    time_str = parse_time_input(text)
    
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_deadline_date_offset)
    
    if date_offset is None:
        await state.clear()
        await _show_home_from_message(message, repo)
        return
    
    # Combine date and time
    date_dt = get_date_offset_days(date_offset)
    deadline_dt = combine_date_time(date_dt, time_str)
    deadline_iso = format_datetime_iso(deadline_dt)
    
    # Add task with deadline
    task_type = data.get(CtxKeys.add_task_type, 'regular')
    difficulty = data.get(CtxKeys.add_task_difficulty, 5)
    task_text = data.get(CtxKeys.add_task_text)
    category = data.get(CtxKeys.add_task_category, '')
    
    if not task_text:
        await message.answer("Virhe: tehtävän teksti puuttuu.")
        return
    
    await repo.add_task(
        user_id=message.from_user.id,
        text=task_text,
        task_type=task_type,
        difficulty=difficulty,
        category=category,
        deadline=deadline_iso
    )
    await state.clear()
    await _show_home_from_message(message, repo)


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
    parts = parse_callback_data(cb.data, 4)
    time_option = parts[3] if parts else None
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_scheduled_date_offset)
    
    if date_offset is None:
        await cb.answer("Virhe: tietoja puuttuu.", show_alert=True)
        await state.clear()
        await _show_home_from_cb(cb, repo)
        return
    
    if time_option == "back":
        await state.set_state(Flow.waiting_task_scheduled)
        if cb.message:
            task_text = data.get(CtxKeys.add_task_text, '')
            await cb.message.edit_text(
                f"Tehtävä: {task_text}\n\n🗓 Valitse päivämäärä:",
                reply_markup=date_picker_kb("add:scheduled:date", include_none=False)
            )
        await cb.answer()
        return
    
    if time_option == "custom":
        # Keep same state for custom time input
        if cb.message:
            await cb.message.answer("Kirjoita aika muodossa HHMM tai HH:MM (esim. 0930 tai 09:30):")
        await cb.answer()
        return
    
    # Parse and add task with schedule
    if not parse_time_string(time_option):
        await cb.answer("Virheellinen aika.", show_alert=True)
        return
    
    task_text = data.get(CtxKeys.add_task_text)
    if not task_text:
        await cb.answer("Virhe: tehtävän teksti puuttuu.", show_alert=True)
        return
    
    date_dt = get_date_offset_days(date_offset)
    schedule_payload = {"timestamp": format_datetime_iso(combine_date_time(date_dt, time_option))}
    
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


@router.message(Flow.waiting_task_scheduled)
async def msg_add_scheduled_custom_time(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle custom time input for scheduled when adding task"""
    text = (message.text or "").strip()
    time_str = parse_time_input(text)
    
    if not time_str:
        await message.answer("Virheellinen aika. Käytä muotoa HHMM tai HH:MM (esim. 0930 tai 09:30).")
        return
    
    data = await state.get_data()
    date_offset = data.get(CtxKeys.add_scheduled_date_offset)
    
    if date_offset is None:
        await state.clear()
        await _show_home_from_message(message, repo)
        return
    
    # Combine date and time
    date_dt = get_date_offset_days(date_offset)
    schedule_dt = combine_date_time(date_dt, time_str)
    schedule_payload = {"timestamp": format_datetime_iso(schedule_dt)}
    
    # Add task with schedule
    task_type = data.get(CtxKeys.add_task_type, 'regular')
    difficulty = data.get(CtxKeys.add_task_difficulty, 5)
    task_text = data.get(CtxKeys.add_task_text)
    category = data.get(CtxKeys.add_task_category, '')
    
    if not task_text:
        await message.answer("Virhe: tehtävän teksti puuttuu.")
        return
    
    # Create task first, then set schedule
    task_id = await repo.add_task(
        user_id=message.from_user.id,
        text=task_text,
        task_type=task_type,
        difficulty=difficulty,
        category=category
    )
    
    # Set schedule
    await repo.set_schedule(
        task_id=task_id,
        user_id=message.from_user.id,
        schedule_kind="at_time",
        schedule_payload=schedule_payload
    )
    
    await state.clear()
    await _show_home_from_message(message, repo)


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

    await state.set_state(Flow.waiting_edit_task_text)
    await state.update_data({CtxKeys.edit_task_id: task_id})
    if cb.message:
        # Show current task with priority indicators
        current_title = render_title_with_priority(task.text, task.priority)
        await cb.message.answer(
            f"Muokkaa tehtävää:\n\nNykyinen:\n{current_title}\n\nKirjoita uusi teksti viestinä."
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
    parts = parse_callback_data(cb.data, 3)
    task_type = parts[2] if parts else 'regular'
    await state.update_data({CtxKeys.add_task_type: task_type})
    await state.set_state(Flow.waiting_new_task_text)
    
    if cb.message:
        await cb.message.answer(
            f"Tehtävätyyppi: {task_type}\n\nKirjoita tehtävän teksti viestinä."
        )
    await cb.answer()


@router.callback_query(F.data.startswith("add:difficulty:"))
async def cb_add_difficulty(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    parts = parse_callback_data(cb.data, 3)
    difficulty_str = parts[2] if parts else "custom"
    
    if difficulty_str == "custom":
        await state.set_state(Flow.waiting_task_difficulty_custom)
        if cb.message:
            await cb.message.answer("Kirjoita haastavuus prosentteina (esim. 15):")
    else:
        difficulty = parse_int_safe(difficulty_str)
        if difficulty is not None:
            await state.update_data({CtxKeys.add_task_difficulty: difficulty})
            await state.set_state(Flow.waiting_task_category)
            data = await state.get_data()
            task_text = data.get(CtxKeys.add_task_text, '')
            if cb.message:
                await cb.message.edit_text(
                    f"Tehtävä: {task_text}\n\n" + render_add_category_header(),
                    reply_markup=add_task_category_kb()
                )
        else:
            await cb.answer("Virheellinen haastavuus.", show_alert=True)
            return
    
    await cb.answer()


@router.callback_query(F.data.startswith("add:category:"))
async def cb_add_category(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    parts = parse_callback_data(cb.data, 3)
    category = parts[2] if parts else ''
    data = await state.get_data()
    
    task_type = data.get(CtxKeys.add_task_type, 'regular')
    difficulty = data.get(CtxKeys.add_task_difficulty, 5)
    task_text = data.get(CtxKeys.add_task_text)
    
    if not task_text:
        await cb.answer("Virhe: tehtävän teksti puuttuu.", show_alert=True)
        return
    
    # If deadline or scheduled type, ask for date/time first
    if task_type in ('deadline', 'scheduled'):
        await state.update_data({CtxKeys.add_task_category: category})
        if task_type == 'deadline':
            await state.set_state(Flow.waiting_task_deadline)
            if cb.message:
                await cb.message.edit_text(
                    f"Tehtävä: {task_text}\n\n⏰ Valitse määräaika:",
                    reply_markup=date_picker_kb("add:deadline:date")
                )
        else:  # scheduled
            await state.set_state(Flow.waiting_task_scheduled)
            if cb.message:
                await cb.message.edit_text(
                    f"Tehtävä: {task_text}\n\n🗓 Valitse päivämäärä:",
                    reply_markup=date_picker_kb("add:scheduled:date", include_none=False)
                )
        await cb.answer()
        return
    
    # Regular task - add immediately
    await repo.add_task(
        user_id=cb.from_user.id,
        text=task_text,
        task_type=task_type,
        difficulty=difficulty,
        category=category
    )
    await state.clear()
    await _show_home_from_cb(cb, repo, answer_text="Tehtävä lisätty", force_refresh=True)


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
