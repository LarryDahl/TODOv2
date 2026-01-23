"""
Handlers for task suggestions feature.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.db import TasksRepo
from app.handlers.common import return_to_main_menu
from app.suggestions import select_suggestions
from app.ui import render_suggestions_header, suggestions_kb
from app.utils import parse_callback_data, parse_int_safe

router = Router()


@router.callback_query(F.data == "view:suggestions")
async def cb_suggestions_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show suggestions view"""
    await state.clear()
    
    # Get backlog tasks
    completed, deleted = await repo.get_backlog_tasks(user_id=cb.from_user.id, limit=50)
    
    # Get recently snoozed event IDs to exclude
    snoozed_ids = await repo.get_snoozed_event_ids(user_id=cb.from_user.id, days=7)
    
    # Filter out snoozed tasks
    completed_filtered = [t for t in completed if t.get('id') not in snoozed_ids]
    deleted_filtered = [t for t in deleted if t.get('id') not in snoozed_ids]
    
    # Select suggestions
    suggestions = select_suggestions(
        completed_tasks=completed_filtered,
        deleted_tasks=deleted_filtered,
        max_suggestions=7,
        min_suggestions=3,
    )
    
    if cb.message:
        if suggestions:
            header = render_suggestions_header(len(suggestions))
            await cb.message.edit_text(header, reply_markup=suggestions_kb(suggestions))
            
            # Log suggestion shown (non-blocking)
            await repo.log_action(
                user_id=cb.from_user.id,
                action='suggestion_shown',
                payload={'count': len(suggestions), 'event_ids': [s.get('event_id') for s in suggestions]},
            )
        else:
            await cb.message.edit_text(
                "💡 Ehdotukset\n\nEi ehdotuksia tällä hetkellä.\n\nKun olet tehnyt tai poistanut tehtäviä, ne voivat ilmestyä ehdotuksina.",
                reply_markup=suggestions_kb([])
            )
    await cb.answer()


@router.callback_query(F.data.startswith("suggestion:accept:"))
async def cb_suggestion_accept(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Accept a suggestion - restore task to backlog"""
    parts = parse_callback_data(cb.data, 3)
    event_id = parse_int_safe(parts[2]) if parts else None
    
    if event_id is None:
        await cb.answer("Virheellinen ehdotus-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Log the acceptance
    await repo.log_suggestion_action(user_id=cb.from_user.id, event_id=event_id, action="accepted")
    
    # Restore the task (try completed first, then deleted)
    success = await repo.restore_completed_task(user_id=cb.from_user.id, event_id=event_id)
    if not success:
        success = await repo.restore_deleted_task(user_id=cb.from_user.id, event_id=event_id)
    
    # Log action (non-blocking)
    if success:
        restored_task_id = None
        # Try to get the restored task ID (it's a new task, so we'd need to track it)
        # For now, we'll log with event_id
        await repo.log_action(
            user_id=cb.from_user.id,
            action='suggestion_accepted',
            payload={'event_id': event_id},
        )
    
    if success:
        await return_to_main_menu(
            cb, repo, state=state, answer_text="Tehtävä lisätty tehtävälistaan", force_refresh=True
        )
    else:
        await cb.answer("Tehtävää ei voitu palauttaa.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data.startswith("suggestion:snooze:"))
async def cb_suggestion_snooze(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Snooze a suggestion - hide it for 7 days"""
    parts = parse_callback_data(cb.data, 3)
    event_id = parse_int_safe(parts[2]) if parts else None
    
    if event_id is None:
        await cb.answer("Virheellinen ehdotus-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Answer promptly
    await cb.answer("Ehdotus ohitettu")
    
    # Log the snooze
    await repo.log_suggestion_action(user_id=cb.from_user.id, event_id=event_id, action="snoozed")
    
    # Log action (non-blocking)
    await repo.log_action(
        user_id=cb.from_user.id,
        action='suggestion_ignored',
        payload={'event_id': event_id},
    )
    
    # Return to suggestions view (refresh to hide snoozed item)
    await cb_suggestions_view(cb, state, repo)
