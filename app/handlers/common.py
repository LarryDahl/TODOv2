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
from app.ui import build_main_keyboard_6_3, render_home_text


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
    # Routine edit/add
    waiting_routine_add_text = State()
    waiting_routine_edit_text = State()
    # Routine time window (aamu): kaksivaiheinen syöttö
    waiting_morning_start = State()
    waiting_morning_end = State()
    # Routine time window (ilta): kaksivaiheinen syöttö
    waiting_evening_start = State()
    waiting_evening_end = State()


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
    # Routine edit/add
    routine_type: str = "routine_type"
    routine_task_id: str = "routine_task_id"
    # Routine time window (aamu/ilta): tallennettu aloitusaika
    routine_morning_start: str = "routine_morning_start"
    routine_evening_start: str = "routine_evening_start"
    routine_windows: str = "routine_windows"  # get_routine_windows dict for prompts


async def _get_routine_view_if_active(user_id: int, repo: TasksRepo) -> tuple[str, InlineKeyboardMarkup] | None:
    """
    Jos aika + asetus + ei kuitattu -> palauta (header, kb) rutiininäkymälle.
    Muuten None. Rutiinit overridee kaiken muun kunnes päivä on kuitattu.
    Rutiinien tehty/tekemätön -tila: user_routine_completions (päiväkohtainen).
    """
    import logging
    from app.ui import render_routine_active_header, routine_active_kb

    settings = await repo.get_user_settings(user_id=user_id)
    # Truthy: 1, True; falsy: 0, None, False
    morning_enabled = bool(settings.get("morning_routines_enabled") or 0)
    evening_enabled = bool(settings.get("evening_routines_enabled") or 0)
    today = await repo.get_today_date_user_tz(user_id)
    tz = settings.get("timezone") or "Europe/Helsinki"

    if not morning_enabled:
        logging.info(f"[ROUTINE] user_id={user_id} morning: enabled=False (asetus pois tai ei riviä) tz={tz}")
    if morning_enabled:
        in_morning = await repo.is_in_morning_window(user_id)
        quitted = await repo.get_routine_quitted(user_id, "morning", today)
        logging.info(
            f"[ROUTINE] user_id={user_id} morning: enabled={morning_enabled} in_window={in_morning} quitted={quitted} today={today} tz={tz}"
        )
        if in_morning and not quitted:
            await repo.ensure_default_routine_tasks(user_id, "morning")
            morning_tasks = await repo.list_routine_tasks(user_id, "morning")
            morning_done = await repo.get_routine_completions_for_date(user_id, today)
            all_done = len(morning_tasks) > 0 and len(morning_done) >= len(morning_tasks)
            header = render_routine_active_header("morning", all_done)
            kb = routine_active_kb("morning", morning_tasks, morning_done, all_done)
            return header, kb

    if evening_enabled:
        in_evening = await repo.is_in_evening_window(user_id)
        quitted = await repo.get_routine_quitted(user_id, "evening", today)
        if in_evening and not quitted:
            await repo.ensure_default_routine_tasks(user_id, "evening")
            evening_tasks = await repo.list_routine_tasks(user_id, "evening")
            evening_done = await repo.get_routine_completions_for_date(user_id, today)
            all_done = len(evening_tasks) > 0 and len(evening_done) >= len(evening_tasks)
            header = render_routine_active_header("evening", all_done)
            kb = routine_active_kb("evening", evening_tasks, evening_done, all_done)
            return header, kb

    return None


async def render_home_message(
    user_id: int,
    repo: TasksRepo,
    force_refresh: bool = False,
    shuffle_suggestions: bool = False,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Ensin: jos rutiinit aktiiviset (aika + päällä + ei kuitattu) -> vain rutiininäkymä.
    Muuten: default view (1 tehty, 9 aktiivista/ehdotusta, nav).
    shuffle_suggestions: if True, call shuffle_suggestion_slots (e.g. from refresh) instead of fill_suggestion_slots.
    """
    import logging
    import traceback
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from app.db import Task

    stack = traceback.extract_stack()
    caller = stack[-3] if len(stack) >= 3 else None
    caller_info = f"{caller.filename}:{caller.lineno} in {caller.name}" if caller else "unknown"
    logging.info(
        f"[MAIN_MENU] render_home_message called for user {user_id} "
        f"(force_refresh={force_refresh}, shuffle_suggestions={shuffle_suggestions}) from {caller_info}"
    )

    # 1) Rutiinit etusijalla: aikavälillä + päällä + ei kuitattu -> vain rutiinilista
    routine_view = await _get_routine_view_if_active(user_id, repo)
    if routine_view is not None:
        return routine_view

    settings = await repo.get_user_settings(user_id=user_id)
    show_done = settings.get("show_done_in_home", True)
    now = repo._now_iso()

    active_tasks = await repo.get_active_tasks(user_id, limit=9)
    need_suggestions = 9 - len(active_tasks)
    if shuffle_suggestions:
        await repo.shuffle_suggestion_slots(user_id, now, need_suggestions)
    else:
        await repo.fill_suggestion_slots(user_id, now)
    slot_ids = await repo.get_suggestion_slots(user_id)
    tids_in_order = [slot_ids[i] if i < len(slot_ids) else None for i in range(need_suggestions)]
    ids_to_fetch = [tid for tid in tids_in_order if tid is not None]
    task_map = await repo.get_tasks_by_ids(user_id, ids_to_fetch)
    suggestion_tasks: list["Task | None"] = [
        task_map.get(tid) if tid is not None else None for tid in tids_in_order
    ]

    completed = await repo.list_completed_tasks(user_id=user_id, limit=1) if show_done else []
    completed_count_today = await repo.count_completed_tasks_today(user_id=user_id)
    active_count = len(active_tasks) + sum(1 for t in suggestion_tasks if t is not None)

    header_text = render_home_text(
        completed_count=completed_count_today,
        active_count=active_count,
        active_steps=[],
        force_refresh=force_refresh,
    )
    keyboard = build_main_keyboard_6_3(
        active_tasks=active_tasks,
        suggestion_tasks=suggestion_tasks,
        completed_tasks=completed if show_done else [],
    )
    return header_text, keyboard


async def _show_home_from_message(message: Message, repo: TasksRepo, state: FSMContext | None = None) -> None:
    """Show default home view from message. Always clears state and returns to main menu."""
    import logging
    import traceback

    stack = traceback.extract_stack()
    caller = stack[-2] if len(stack) >= 2 else None
    caller_info = f"{caller.filename}:{caller.lineno} in {caller.name}" if caller else "unknown"
    logging.info(
        f"[MAIN_MENU] _show_home_from_message called (user_id={message.from_user.id}) from {caller_info}"
    )

    if state:
        await state.clear()

    user_id = message.from_user.id
    header_text, keyboard = await render_home_message(
        user_id=user_id, repo=repo, force_refresh=False
    )
    await message.answer(header_text, reply_markup=keyboard)


async def _show_home_from_cb(
    cb: CallbackQuery,
    repo: TasksRepo,
    state: FSMContext | None = None,
    answer_text: str | None = None,
    force_refresh: bool = False,
    shuffle_suggestions: bool = False,
) -> None:
    """Show default home view from callback. Always clears state, answers callback, and returns to main menu."""
    import logging
    import traceback
    from aiogram.exceptions import TelegramBadRequest

    stack = traceback.extract_stack()
    caller = stack[-2] if len(stack) >= 2 else None
    caller_info = f"{caller.filename}:{caller.lineno} in {caller.name}" if caller else "unknown"
    logging.info(
        f"[MAIN_MENU] _show_home_from_cb called (user_id={cb.from_user.id}, "
        f"force_refresh={force_refresh}, shuffle_suggestions={shuffle_suggestions}, callback_data={cb.data}) from {caller_info}"
    )

    if state:
        await state.clear()

    user_id = cb.from_user.id
    header_text, keyboard = await render_home_message(
        user_id=user_id, repo=repo, force_refresh=force_refresh, shuffle_suggestions=shuffle_suggestions
    )

    if cb.message:
        try:
            await cb.message.edit_text(header_text, reply_markup=keyboard)
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower() and force_refresh:
                try:
                    await cb.message.edit_reply_markup(reply_markup=keyboard)
                except Exception:
                    pass
            elif "message is not modified" in str(e).lower():
                pass
            else:
                raise
        except Exception:
            pass

    if answer_text:
        await cb.answer(answer_text)
    else:
        await cb.answer()


async def return_to_main_menu(
    cb: CallbackQuery | Message,
    repo: TasksRepo,
    state: FSMContext | None = None,
    answer_text: str | None = None,
    force_refresh: bool = False,
    shuffle_suggestions: bool = False,
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
        shuffle_suggestions: If True, reshuffle suggestion slots (e.g. from refresh button only)
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
        f"user_id={cb.from_user.id}, force_refresh={force_refresh}, shuffle_suggestions={shuffle_suggestions}, "
        f"callback_data={cb_data}) from {caller_info}"
    )
    
    if isinstance(cb, CallbackQuery):
        await _show_home_from_cb(
            cb, repo, state=state, answer_text=answer_text,
            force_refresh=force_refresh, shuffle_suggestions=shuffle_suggestions,
        )
    elif isinstance(cb, Message):
        await _show_home_from_message(cb, repo, state=state)
    else:
        raise TypeError(f"Expected CallbackQuery or Message, got {type(cb)}")
