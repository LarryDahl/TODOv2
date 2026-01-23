"""
Common types, states, and helper functions for handlers.
"""
from __future__ import annotations

from dataclasses import dataclass

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.ui import default_kb, render_default_header


class Flow(StatesGroup):
    """FSM states for task flows"""
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
    # Delete flow state
    waiting_delete_reason = State()


@dataclass(frozen=True)
class CtxKeys:
    """Keys for FSM context data"""
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
    # Delete flow keys
    delete_task_id: str = "delete_task_id"


async def _show_home_from_message(message: Message, repo: TasksRepo, state: FSMContext | None = None) -> None:
    """Show default home view from message. Always clears state and returns to main menu."""
    if state:
        await state.clear()
    
    completed = await repo.list_completed_tasks(user_id=message.from_user.id, limit=3)
    active = await repo.list_tasks(user_id=message.from_user.id, limit=7)
    daily_progress = await repo.get_daily_progress(user_id=message.from_user.id)
    
    # Add separator text between lists if both exist
    header_text = render_default_header(daily_progress)
    if completed and active:
        header_text += "\n\n─────────────"
    
    await message.answer(header_text, reply_markup=default_kb(completed, active))


async def _show_home_from_cb(
    cb: CallbackQuery, 
    repo: TasksRepo, 
    state: FSMContext | None = None,
    answer_text: str | None = None, 
    force_refresh: bool = False
) -> None:
    """Show default home view from callback. Always clears state, answers callback, and returns to main menu."""
    from aiogram.exceptions import TelegramBadRequest
    
    if state:
        await state.clear()
    
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
    
    # Always answer callback - use provided text or default
    if answer_text:
        await cb.answer(answer_text)
    else:
        await cb.answer()


async def return_to_main_menu(
    cb: CallbackQuery | Message,
    repo: TasksRepo,
    state: FSMContext | None = None,
    answer_text: str | None = None,
    force_refresh: bool = False
) -> None:
    """
    Unified function to return to main menu after any operation.
    Handles both CallbackQuery and Message, always clears state, answers callbacks.
    
    Args:
        cb: CallbackQuery or Message
        repo: TasksRepo instance
        state: Optional FSMContext to clear
        answer_text: Optional text for callback answer
        force_refresh: Whether to force refresh the message
    """
    from aiogram.types import CallbackQuery, Message
    
    if isinstance(cb, CallbackQuery):
        await _show_home_from_cb(cb, repo, state=state, answer_text=answer_text, force_refresh=force_refresh)
    elif isinstance(cb, Message):
        await _show_home_from_message(cb, repo, state=state)
    else:
        raise TypeError(f"Expected CallbackQuery or Message, got {type(cb)}")
