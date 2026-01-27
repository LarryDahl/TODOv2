"""
Task action handlers (done, delete, edit, restore).

ROUTER MAP:
- task:done:<task_id> - Mark task as done
- task:del:<task_id> - Delete task
- task:deadline:<task_id> - Set deadline for task
- task:schedule:<task_id> - Set schedule for task
- edit:task:<task_id> - Open task edit menu
- edit:del:<task_id> - Delete task from edit view
- edit:back - Back to edit list
- done:page:<offset> - Pagination for completed tasks
- done:restore:<event_id> - Restore completed task
- deleted:page:<offset> - Pagination for deleted tasks
- deleted:restore:<event_id> - Restore deleted task
- completed:restore:<event_id> - Legacy restore completed (use done:restore:)
- p:<project_id> - Legacy project detail (use proj:detail:)
- ps:<step_id> - Mark project step as done
- ps:del:<step_id> - Delete project step
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.clock import SystemClock
from app.db import TasksRepo
from app.handlers.common import CtxKeys, Flow, return_to_main_menu
from app.priority import parse_priority, render_title_with_priority
from app.utils import parse_callback_data, parse_int_safe

router = Router()


@router.callback_query(F.data.startswith("completed:restore:"))
async def cb_restore_completed(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    from app.handlers.common import return_to_main_menu
    
    parts = parse_callback_data(cb.data, 3)
    event_id = parse_int_safe(parts[2]) if parts else None
    
    if event_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    success = await repo.restore_completed_task(user_id=cb.from_user.id, event_id=event_id)
    if success:
        await return_to_main_menu(cb, repo, state=state, answer_text="Tehtävä palautettu listalle", force_refresh=True)
    else:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data.startswith("task:done:") | F.data.startswith("t:") | F.data.startswith("ps:"))
async def cb_done(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """
    Unified handler for marking tasks and project steps as done.
    Supports:
    - task:done:<task_id> (existing format)
    - t:<task_id> (new format)
    - ps:<step_id> (project step format)
    """
    import logging
    from app.handlers.common import return_to_main_menu
    
    callback_data = cb.data
    
    # Branch based on callback prefix
    if callback_data.startswith("ps:"):
        # Handle project step
        parts = parse_callback_data(callback_data, 2)
        step_id = parse_int_safe(parts[1]) if parts else None
        
        if step_id is None:
            logging.warning(f"Invalid project step ID in callback: {callback_data}")
            await return_to_main_menu(cb, repo, state=state, force_refresh=True)
            return
        
        try:
            now = repo._now_iso()
            result = await repo.advance_project_step(step_id=step_id, now=now)
            
            # Log result for debugging
            logging.info(f"Project step {step_id} advanced: {result.get('action', 'unknown')}")
            
            # If project was completed, show summary
            if result.get('action') == 'completed_project':
                project_id = result.get('project_id')
                if project_id:
                    # Get project and steps for summary
                    project = await repo.get_project(project_id)
                    if project:
                        steps = await repo.get_project_steps(project_id)
                        from app.ui import render_project_completion_summary
                        summary = render_project_completion_summary(project, steps)
                        
                        # Show summary as callback answer (toast notification)
                        await cb.answer(summary, show_alert=True)
            
            # Always refresh list (idempotent: even if noop, refresh to show current state)
            await return_to_main_menu(cb, repo, state=state, force_refresh=True)
        except ValueError as e:
            # Step not found or other validation error
            logging.warning(f"Error advancing project step {step_id}: {e}")
            await return_to_main_menu(cb, repo, state=state, force_refresh=True)
        except Exception as e:
            # Unexpected error - log and refresh without crashing
            logging.error(f"Unexpected error advancing project step {step_id}: {e}", exc_info=True)
            await return_to_main_menu(cb, repo, state=state, force_refresh=True)
    
    else:
        # Handle task (both task:done: and t: formats)
        if callback_data.startswith("task:done:"):
            parts = parse_callback_data(callback_data, 3)
            task_id = parse_int_safe(parts[2]) if parts else None
        else:  # t: format
            parts = parse_callback_data(callback_data, 2)
            task_id = parse_int_safe(parts[1]) if parts else None
        
        if task_id is None:
            await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
            await return_to_main_menu(cb, repo, state=state)
            return
        
        success = await repo.complete_task(user_id=cb.from_user.id, task_id=task_id)
        if success:
            await return_to_main_menu(cb, repo, state=state, answer_text="Tehtävä merkitty tehdyksi", force_refresh=True)
        else:
            await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
            await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data.startswith("p:"))
async def cb_project_detail(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show project detail view with all steps"""
    from app.ui import project_detail_kb, render_project_detail
    
    parts = parse_callback_data(cb.data, 2)
    project_id = parse_int_safe(parts[1]) if parts else None
    
    if project_id is None:
        await cb.answer("Virheellinen projektin-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Get project and steps
    project = await repo.get_project(project_id)
    if not project:
        await cb.answer("Projektia ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    steps = await repo.get_project_steps(project_id)
    
    if cb.message:
        text = render_project_detail(project, steps)
        await cb.message.edit_text(text, reply_markup=project_detail_kb())
    await cb.answer()


@router.callback_query(F.data.startswith("ps:del:"))
async def cb_delete_project_step(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Delete a project step. If active, automatically advances the project."""
    parts = parse_callback_data(cb.data, 3)
    step_id = parse_int_safe(parts[2]) if parts else None
    
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Delete step (automatically advances if active)
    success = await repo.delete_project_step(step_id=step_id)
    
    if success:
        await return_to_main_menu(cb, repo, state=state, answer_text="Askel poistettu", force_refresh=True)
    else:
        await cb.answer("Askelia ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data.startswith("p:del:"))
async def cb_cancel_project(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Cancel a project - marks it as cancelled and hides all steps"""
    parts = parse_callback_data(cb.data, 3)
    project_id = parse_int_safe(parts[2]) if parts else None
    
    if project_id is None:
        await cb.answer("Virheellinen projektin-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Cancel project
    now = repo._now_iso()
    success = await repo.cancel_project(project_id=project_id, now=now)
    
    if success:
        await return_to_main_menu(cb, repo, state=state, answer_text="Projekti peruutettu", force_refresh=True)
    else:
        await cb.answer("Projektia ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data.startswith("task:del:"))
async def cb_delete(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start delete flow - prompt user for deletion reason"""
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Check if task exists and belongs to user
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt tai se on jo poistettu.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Store task_id in state and prompt for reason
    await state.update_data({CtxKeys.delete_task_id: task_id})
    await state.set_state(Flow.waiting_delete_reason)
    
    if cb.message:
        task_title = render_title_with_priority(task.text, task.priority)
        await cb.message.edit_text(
            f"Poista tehtävä:\n\n{task_title}\n\n"
            f"Kirjoita poiston syy (valinnainen).\n"
            f"Lähetä tyhjä viesti tai '/peruuta' peruuttaaksesi."
        )
    await cb.answer()


@router.message(Flow.waiting_delete_reason)
async def msg_delete_reason(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle delete reason submission or cancellation"""
    from app.handlers.common import return_to_main_menu
    
    text = (message.text or "").strip()
    
    # Handle cancellation: /peruuta or /cancel
    if text.lower() in ("/peruuta", "/cancel", "/peru"):
        await return_to_main_menu(message, repo, state=state)
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.delete_task_id)
    
    if not isinstance(task_id, int):
        await message.answer("Virhe: tehtävä-id puuttuu.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    # Double-check task still exists (guard against race conditions)
    task = await repo.get_task(user_id=message.from_user.id, task_id=task_id)
    if not task:
        await message.answer("Tehtävää ei löytynyt tai se on jo poistettu.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    # Use text as reason (empty string if user sent empty message)
    reason = text if text else ""
    
    # Delete task with reason
    success = await repo.delete_task_with_log(
        user_id=message.from_user.id,
        task_id=task_id,
        reason=reason
    )
    
    if success:
        await return_to_main_menu(message, repo, state=state)
    else:
        await message.answer("Tehtävää ei voitu poistaa.")
        await return_to_main_menu(message, repo, state=state)


@router.callback_query(F.data.startswith("task:menu:"))
async def cb_task_menu(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show action menu for a task"""
    from app.ui import task_action_kb
    
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
    
    if cb.message:
        task_title = render_title_with_priority(task.text, task.priority)
        await cb.message.edit_text(
            f"Tehtävä: {task_title}\n\nValitse toiminto:",
            reply_markup=task_action_kb(task)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("task:edit_menu:"))
async def cb_edit_menu(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show edit menu for a task"""
    from app.ui import task_edit_menu_kb, render_task_edit_menu_header
    
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
    
    if cb.message:
        await cb.message.edit_text(
            render_task_edit_menu_header(task),
            reply_markup=task_edit_menu_kb(task)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("task:edit_text:"))
async def cb_edit_text(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start edit task text flow - prompt user for new text"""
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
    
    await state.update_data({CtxKeys.edit_task_id: task_id})
    await state.set_state(Flow.waiting_edit_task_text)
    
    if cb.message:
        task_title = render_title_with_priority(task.text, task.priority)
        await cb.message.edit_text(
            f"Muokkaa tehtävää:\n\nNykyinen: {task_title}\n\n"
            f"Kirjoita uusi teksti viestinä.\n"
            f"(Voit käyttää '!' merkkejä prioriteetin asettamiseen, esim. 'Tehtävä!!!' = prioriteetti 3)\n\n"
            f"Lähetä tyhjä viesti tai '/peruuta' peruuttaaksesi."
        )
    await cb.answer()


@router.message(Flow.waiting_edit_task_text)
async def msg_edit_task(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle task edit submission or cancellation"""
    from app.handlers.common import return_to_main_menu
    
    text = (message.text or "").strip()
    
    # Handle cancellation: empty text or /peruuta or /cancel
    if not text or text.lower() in ("/peruuta", "/cancel", "/peru"):
        await return_to_main_menu(message, repo, state=state)
        return
    
    data = await state.get_data()
    task_id = data.get(CtxKeys.edit_task_id)
    
    if not isinstance(task_id, int):
        await message.answer("Virhe: tehtävä-id puuttuu.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    # Verify task still exists and belongs to user (safety check)
    task = await repo.get_task(user_id=message.from_user.id, task_id=task_id)
    if not task:
        await message.answer("Tehtävää ei löytynyt tai se on jo poistettu.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    # Update task in database (priority is parsed automatically from text in update_task)
    success = await repo.update_task(
        user_id=message.from_user.id,
        task_id=task_id,
        new_text=text
    )
    
    if success:
        await return_to_main_menu(message, repo, state=state, force_refresh=True)
    else:
        await message.answer("Virhe: tehtävää ei voitu päivittää.")
        await return_to_main_menu(message, repo, state=state)


@router.callback_query(F.data.startswith("task:priority_up:"))
async def cb_priority_up(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Increase task priority by 1"""
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Verify task exists
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Update priority
    success = await repo.update_task_meta(
        user_id=cb.from_user.id,
        task_id=task_id,
        patch={'increment_priority': True}
    )
    
    if success:
        await return_to_main_menu(
            cb, repo, state=state, answer_text="Prioriteetti nostettu", force_refresh=True
        )
    else:
        await cb.answer("Virhe: prioriteettia ei voitu päivittää.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data.startswith("task:priority_down:"))
async def cb_priority_down(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Decrease task priority by 1"""
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Verify task exists
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Update priority
    success = await repo.update_task_meta(
        user_id=cb.from_user.id,
        task_id=task_id,
        patch={'decrement_priority': True}
    )
    
    if success:
        await return_to_main_menu(
            cb, repo, state=state, answer_text="Prioriteetti laskettu", force_refresh=True
        )
    else:
        await cb.answer("Virhe: prioriteettia ei voitu päivittää.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data.startswith("task:dl_plus1h:"))
async def cb_dl_plus1h(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Set or push deadline by +1 hour from now (Helsinki time)"""
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Verify task exists
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Calculate new deadline: +1 hour from now (Helsinki time, stored as UTC)
    new_deadline = SystemClock.add_hours_helsinki(1)
    
    # If task already has deadline, use the later of (current deadline, new deadline)
    if task.deadline:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        try:
            current_deadline = datetime.fromisoformat(task.deadline.replace('Z', '+00:00'))
            new_deadline_dt = datetime.fromisoformat(new_deadline.replace('Z', '+00:00'))
            # Use the later deadline
            if current_deadline > new_deadline_dt:
                new_deadline = task.deadline
        except (ValueError, AttributeError):
            pass  # Use new_deadline if parsing fails
    
    # Update deadline
    success = await repo.update_task_meta(
        user_id=cb.from_user.id,
        task_id=task_id,
        patch={'deadline': new_deadline}
    )
    
    if success:
        await return_to_main_menu(
            cb, repo, state=state, answer_text="Määräaika asetettu +1h", force_refresh=True
        )
    else:
        await cb.answer("Virhe: määräaikaa ei voitu päivittää.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data.startswith("task:dl_plus24h:"))
async def cb_dl_plus24h(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Set or push deadline by +24 hours from now (Helsinki time)"""
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Verify task exists
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Calculate new deadline: +24 hours from now (Helsinki time, stored as UTC)
    new_deadline = SystemClock.add_hours_helsinki(24)
    
    # If task already has deadline, use the later of (current deadline, new deadline)
    if task.deadline:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        try:
            current_deadline = datetime.fromisoformat(task.deadline.replace('Z', '+00:00'))
            new_deadline_dt = datetime.fromisoformat(new_deadline.replace('Z', '+00:00'))
            # Use the later deadline
            if current_deadline > new_deadline_dt:
                new_deadline = task.deadline
        except (ValueError, AttributeError):
            pass  # Use new_deadline if parsing fails
    
    # Update deadline
    success = await repo.update_task_meta(
        user_id=cb.from_user.id,
        task_id=task_id,
        patch={'deadline': new_deadline}
    )
    
    if success:
        await return_to_main_menu(
            cb, repo, state=state, answer_text="Määräaika asetettu +24h", force_refresh=True
        )
    else:
        await cb.answer("Virhe: määräaikaa ei voitu päivittää.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data.startswith("task:dl_remove:"))
async def cb_dl_remove(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Remove deadline from task"""
    parts = parse_callback_data(cb.data, 3)
    task_id = parse_int_safe(parts[2]) if parts else None
    
    if task_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Verify task exists
    task = await repo.get_task(user_id=cb.from_user.id, task_id=task_id)
    if not task:
        await cb.answer("Tehtävää ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Remove deadline
    success = await repo.update_task_meta(
        user_id=cb.from_user.id,
        task_id=task_id,
        patch={'deadline': None}
    )
    
    if success:
        await return_to_main_menu(
            cb, repo, state=state, answer_text="Määräaika poistettu", force_refresh=True
        )
    else:
        await cb.answer("Virhe: määräaikaa ei voitu poistaa.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
