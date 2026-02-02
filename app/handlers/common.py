"""
Common types, states, and helper functions for handlers.

This module contains:
- Flow: FSM state definitions
- CtxKeys: FSM context data keys
- render_home_message(): Unified home view renderer
- return_to_main_menu(): Unified function to return to home
- _show_home_from_message(): Internal helper for Message
- _show_home_from_cb(): Internal helper for CallbackQuery

ROUTER MAP:
- This module does not define routes, but provides utilities used by all handlers.
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
    # Project step edit states
    waiting_project_step_text = State()  # For adding new project step
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
    waiting_project_rewrite_steps = State()  # For rewriting all project steps
    # Simplified add task flow states (from plus menu)
    waiting_deadline_text = State()  # After date/time selection, ask for text
    waiting_scheduled_text = State()  # After date/time selection, ask for text


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
    add_deadline_time: str = "add_deadline_time"  # Time string after selection
    add_scheduled_date_offset: str = "add_scheduled_date_offset"
    add_scheduled_time: str = "add_scheduled_time"  # Time string after selection
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
    import traceback
    
    # Debug log to track which renderer is called and from where
    # Get caller info (skip this function and _show_home_* functions)
    stack = traceback.extract_stack()
    caller = stack[-3] if len(stack) >= 3 else None
    caller_info = f"{caller.filename}:{caller.lineno} in {caller.name}" if caller else "unknown"
    
    logging.info(
        f"[MAIN_MENU] render_home_message called for user {user_id} "
        f"(force_refresh={force_refresh}) from {caller_info}"
    )
    
    # Get user settings (for show_done_in_home)
    settings = await repo.get_user_settings(user_id=user_id)
    show_done = settings.get('show_done_in_home', True)
    
    # Fetch data
    completed = await repo.list_completed_tasks(user_id=user_id, limit=3) if show_done else []
    active = await repo.list_tasks(user_id=user_id, limit=50)  # Get more for proper sorting
    active_steps = await repo.get_active_project_steps()
    
    # Count completed tasks today (for progress bar) - all tasks, not just visible ones
    completed_count_today = await repo.count_completed_tasks_today(user_id=user_id)
    active_count = len(active)
    
    # Build header text with progress bar
    header_text = render_home_text(
        completed_count=completed_count_today,
        active_count=active_count,
        active_steps=active_steps,
        force_refresh=force_refresh
    )
    
    # Build keyboard with new order
    keyboard = build_home_keyboard(
        completed_tasks=completed if show_done else [],
        active_tasks=active,
        active_steps=active_steps
    )
    
    return header_text, keyboard


async def _show_home_from_message(message: Message, repo: TasksRepo, state: FSMContext | None = None) -> None:
    """Show default home view from message. Always clears state and returns to main menu."""
    import logging
    import traceback
    
    # Get caller info
    stack = traceback.extract_stack()
    caller = stack[-2] if len(stack) >= 2 else None
    caller_info = f"{caller.filename}:{caller.lineno} in {caller.name}" if caller else "unknown"
    
    logging.info(
        f"[MAIN_MENU] _show_home_from_message called (user_id={message.from_user.id}) from {caller_info}"
    )
    
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
    import traceback
    from aiogram.exceptions import TelegramBadRequest
    
    # Get caller info
    stack = traceback.extract_stack()
    caller = stack[-2] if len(stack) >= 2 else None
    caller_info = f"{caller.filename}:{caller.lineno} in {caller.name}" if caller else "unknown"
    
    logging.info(
        f"[MAIN_MENU] _show_home_from_cb called (user_id={cb.from_user.id}, "
        f"force_refresh={force_refresh}, callback_data={cb.data}) from {caller_info}"
    )
    
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
    
    This is the ONLY entry point for returning to the main menu. All handlers should use this.
    
    Args:
        cb: CallbackQuery or Message
        repo: TasksRepo instance
        state: Optional FSMContext to clear
        answer_text: Optional text for callback answer
        force_refresh: Whether to force refresh the message
    """
    import logging
    import traceback
    from aiogram.types import CallbackQuery, Message
    
    # Get caller info for debugging
    stack = traceback.extract_stack()
    caller = stack[-2] if len(stack) >= 2 else None
    caller_info = f"{caller.filename}:{caller.lineno} in {caller.name}" if caller else "unknown"
    
    cb_type = "CallbackQuery" if isinstance(cb, CallbackQuery) else "Message"
    cb_data = getattr(cb, 'data', None) if isinstance(cb, CallbackQuery) else None
    
    logging.info(
        f"[MAIN_MENU] return_to_main_menu called ({cb_type}, "
        f"user_id={cb.from_user.id}, force_refresh={force_refresh}, "
        f"callback_data={cb_data}) from {caller_info}"
    )
    
    if isinstance(cb, CallbackQuery):
        await _show_home_from_cb(cb, repo, state=state, answer_text=answer_text, force_refresh=force_refresh)
    elif isinstance(cb, Message):
        await _show_home_from_message(cb, repo, state=state)
    else:
        raise TypeError(f"Expected CallbackQuery or Message, got {type(cb)}")
