"""
Common types, states, and helper functions for handlers.
"""
from __future__ import annotations

from dataclasses import dataclass

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.db import TasksRepo
from app.ui import build_home_keyboard, render_home_text


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
    # Backlog project flow states
    waiting_project_name = State()
    waiting_project_steps = State()


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
    # Backlog project flow keys
    project_name: str = "project_name"


async def render_home_message(
    user_id: int,
    repo: TasksRepo,
    force_refresh: bool = False
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Unified function to render the main menu/home view.
    This is the ONLY function that should render the main menu.
    
    Returns:
        Tuple of (header_text, keyboard)
    """
    import logging
    
    # Debug log to track which renderer is called
    logging.info(f"[MAIN_MENU] render_home_message called for user {user_id} (force_refresh={force_refresh})")
    
    # Fetch data
    completed = await repo.list_completed_tasks(user_id=user_id, limit=3)
    active = await repo.list_tasks(user_id=user_id, limit=50)  # Get more for proper sorting
    active_steps = await repo.get_active_project_steps()
    
    # Count completed and active tasks for progress calculation
    completed_count = len(completed)
    active_count = len(active)
    
    # Build header text with progress bar
    header_text = render_home_text(
        completed_count=completed_count,
        active_count=active_count,
        active_steps=active_steps,
        force_refresh=force_refresh
    )
    
    # Build keyboard with new order
    keyboard = build_home_keyboard(
        completed_tasks=completed,
        active_tasks=active,
        active_steps=active_steps
    )
    
    return header_text, keyboard


async def _show_home_from_message(message: Message, repo: TasksRepo, state: FSMContext | None = None) -> None:
    """Show default home view from message. Always clears state and returns to main menu."""
    import logging
    
    logging.info(f"[MAIN_MENU] _show_home_from_message called (user_id={message.from_user.id})")
    
    if state:
        await state.clear()
    
    header_text, keyboard = await render_home_message(
        user_id=message.from_user.id,
        repo=repo,
        force_refresh=False
    )
    
    await message.answer(header_text, reply_markup=keyboard)


async def _show_home_from_cb(
    cb: CallbackQuery, 
    repo: TasksRepo, 
    state: FSMContext | None = None,
    answer_text: str | None = None, 
    force_refresh: bool = False
) -> None:
    """Show default home view from callback. Always clears state, answers callback, and returns to main menu."""
    import logging
    from aiogram.exceptions import TelegramBadRequest
    
    logging.info(f"[MAIN_MENU] _show_home_from_cb called (user_id={cb.from_user.id}, force_refresh={force_refresh})")
    
    if state:
        await state.clear()
    
    header_text, keyboard = await render_home_message(
        user_id=cb.from_user.id,
        repo=repo,
        force_refresh=force_refresh
    )
    
    if cb.message:
        try:
            await cb.message.edit_text(header_text, reply_markup=keyboard)
        except TelegramBadRequest as e:
            # If message is not modified and we're forcing refresh, try with reply_markup only
            if "message is not modified" in str(e).lower() and force_refresh:
                try:
                    # Force update by editing reply markup separately
                    await cb.message.edit_reply_markup(reply_markup=keyboard)
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
