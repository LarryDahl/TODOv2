"""
Centralized text message handler.
Ensures "free message = new task" only when user is NOT in FSM state.

ROUTER MAP:
- @router.message() - Catch-all for text messages (MUST be registered last)
  - If user is NOT in FSM state: create regular task
  - If user IS in FSM state: let FSM state handlers process it
"""
from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.db import TasksRepo
from app.handlers.common import Flow, return_to_main_menu

router = Router()


# List of all FSM states that should NOT trigger "free message = new task"
# If user is in any of these states, text message is treated as input for that flow
FSM_INPUT_STATES = {
    Flow.waiting_new_task_text,
    Flow.waiting_edit_task_text,
    Flow.waiting_task_type,
    Flow.waiting_task_difficulty,
    Flow.waiting_task_difficulty_custom,
    Flow.waiting_task_category,
    Flow.waiting_task_deadline,
    Flow.waiting_task_scheduled,
    Flow.waiting_deadline_date,
    Flow.waiting_deadline_time,
    Flow.waiting_deadline_custom_time,
    Flow.waiting_deadline_text,
    Flow.waiting_schedule_type,
    Flow.waiting_schedule_date,
    Flow.waiting_schedule_time,
    Flow.waiting_schedule_time_range_start,
    Flow.waiting_schedule_time_range_end,
    Flow.waiting_schedule_custom_time,
    Flow.waiting_scheduled_text,
    Flow.waiting_delete_reason,
    Flow.waiting_project_name,
    Flow.waiting_project_steps,
    Flow.waiting_project_step_text,
    Flow.waiting_project_rewrite_steps,
    Flow.waiting_routine_add_text,
    Flow.waiting_routine_edit_text,
    Flow.waiting_morning_start,
    Flow.waiting_morning_end,
    Flow.waiting_evening_start,
    Flow.waiting_evening_end,
}


@router.message()
async def msg_text_handler(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """
    Centralized text message handler.
    
    Invariant:
    - If user is NOT in FSM input state: create regular task (free message = new task)
    - If user IS in FSM input state: do nothing (let FSM state handlers process it)
    
    This handler must be registered LAST (after all FSM state handlers) so that
    FSM state handlers get priority.
    """
    # Skip if message is a command
    if message.text and message.text.startswith("/"):
        # Commands are handled by Command handlers, not here
        return
    
    # Check current FSM state
    # If state is None, user is not in any FSM state -> proceed to create task
    if state:
        current_state = await state.get_state()
        
        # If user is in any FSM input state, do NOT create a task
        # Let the FSM state handlers process the message
        if current_state in FSM_INPUT_STATES:
            # FSM state handler will process this message
            # We don't need to do anything here
            return
    
    # User is NOT in FSM state -> "free message = new task"
    text = (message.text or "").strip()
    if not text:
        # Empty message, just return to home
        await return_to_main_menu(message, repo, state=state)
        return
    
    # Create regular task with defaults
    await repo.add_task(
        user_id=message.from_user.id,
        text=text,
        task_type='regular',
        difficulty=5,
        category=''
    )
    
    # Return to home with confirmation
    await return_to_main_menu(
        message, repo, state=state, 
        answer_text="Tehtävä lisätty", 
        force_refresh=True
    )
