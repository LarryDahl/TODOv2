"""
View handlers for navigation and display.

ROUTER MAP:
- home:home - Return to home view
- home:refresh - Refresh home view (re-render existing message)
- home:edit - Open edit tasks view
- settings:* - Settings actions (see settings handlers)
- stats:* - Statistics actions (see stats handlers)
- view:* - Legacy view navigation (being phased out)
- done:* - Completed tasks view
- deleted:* - Deleted tasks view
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.handlers.common import CtxKeys, return_to_main_menu
from app.utils import parse_callback_data, parse_int_safe
from app.ui import (
    deleted_tasks_kb,
    done_tasks_kb,
    edit_kb,
    render_edit_header,
    render_settings_header,
    render_stats_header,
    render_all_time_stats,
    render_ai_analysis_header,
    render_ai_analysis_disabled,
    render_ai_analysis_placeholder,
    render_reset_stats_confirm,
    settings_kb,
    stats_ai_period_kb,
    stats_menu_kb,
    stats_reset_confirm_kb,
    stats_kb,
    task_action_kb,
)

router = Router()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    await return_to_main_menu(message, repo, state=state)


@router.callback_query(F.data.in_(["view:home", "home:home"]))
async def cb_home(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Return to home view"""
    await return_to_main_menu(cb, repo, state=state, force_refresh=True)


@router.callback_query(F.data.in_(["view:refresh", "home:refresh"]))
async def cb_refresh(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """
    Refresh the main menu task list to show latest changes and approaching deadlines.
    Re-renders existing message if possible.
    """
    await return_to_main_menu(cb, repo, state=state, answer_text="Lista päivitetty", force_refresh=True)


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data == "view:settings")
async def cb_settings(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open settings view"""
    await state.clear()
    
    settings = await repo.get_user_settings(user_id=cb.from_user.id)
    
    if cb.message:
        await cb.message.edit_text(
            render_settings_header(settings),
            reply_markup=settings_kb(show_done=settings.get('show_done_in_home', True))
        )
    await cb.answer()


@router.callback_query(F.data == "settings:timezone")
async def cb_settings_timezone(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open timezone selection"""
    from app.ui import settings_timezone_kb, render_timezone_selection_header
    
    await state.clear()
    
    if cb.message:
        await cb.message.edit_text(
            render_timezone_selection_header(),
            reply_markup=settings_timezone_kb()
        )
    await cb.answer()


@router.callback_query(F.data.startswith("settings:tz:"))
async def cb_settings_timezone_set(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Set user timezone"""
    from app.ui import render_timezone_set, render_settings_header, settings_kb
    
    await state.clear()
    
    parts = cb.data.split(":", 2)
    timezone = parts[2] if len(parts) > 2 else "Europe/Helsinki"
    
    success = await repo.set_user_timezone(user_id=cb.from_user.id, timezone=timezone)
    
    if cb.message:
        if success:
            # Refresh settings view
            settings = await repo.get_user_settings(user_id=cb.from_user.id)
            await cb.message.edit_text(
                render_settings_header(settings),
                reply_markup=settings_kb(show_done=settings.get('show_done_in_home', True))
            )
            await cb.answer(render_timezone_set(timezone))
        else:
            await cb.answer("Virhe: Aikavyöhykkeen asetus epäonnistui.", show_alert=True)


@router.callback_query(F.data == "settings:toggle_show_done")
async def cb_settings_toggle_show_done(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Toggle show_done_in_home setting"""
    from app.ui import render_settings_header, settings_kb
    
    await state.clear()
    
    new_value = await repo.toggle_show_done_in_home(user_id=cb.from_user.id)
    
    if cb.message:
        settings = await repo.get_user_settings(user_id=cb.from_user.id)
        await cb.message.edit_text(
            render_settings_header(settings),
            reply_markup=settings_kb(show_done=new_value)
        )
        status = "näytetään" if new_value else "piilotettu"
        await cb.answer(f"Tehdyt {status} päänäkymässä")


@router.callback_query(F.data == "settings:export_db")
async def cb_settings_export_db(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Export DB (placeholder)"""
    from app.ui import render_export_db_placeholder, settings_kb
    
    await state.clear()
    
    if cb.message:
        settings = await repo.get_user_settings(user_id=cb.from_user.id)
        await cb.message.edit_text(
            render_export_db_placeholder(),
            reply_markup=settings_kb(show_done=settings.get('show_done_in_home', True))
        )
    await cb.answer("Tulossa myöhemmin")


@router.callback_query(F.data == "settings:reset")
async def cb_reset(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    await repo.reset_all_data(user_id=cb.from_user.id)
    if cb.message:
        await cb.message.edit_text("✅ Kaikki tiedot nollattu.", reply_markup=settings_kb())
    await cb.answer("Tiedot nollattu")


@router.callback_query(F.data.in_(["view:edit", "home:edit"]))
async def cb_edit_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open edit tasks view (from home or plus menu)"""
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
        header = f"✅ Tehdyt tehtävät\n\nYhteensä: {len(tasks)} tehtävää\n\nKlikkaa tehtävää palauttaaksesi sen aktiiviseksi."
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
        await return_to_main_menu(cb, repo, state=state)
        return
    
    tasks = await repo.list_done_tasks(user_id=cb.from_user.id, limit=50, offset=offset)
    if cb.message:
        await cb.message.edit_text(
            f"✅ Tehdyt tehtävät\n\nSivu {offset // 50 + 1}\n\nKlikkaa tehtävää palauttaaksesi sen aktiiviseksi.",
            reply_markup=done_tasks_kb(tasks, offset=offset)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("done:restore:"))
async def cb_done_restore(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Restore a completed task to active list"""
    from app.handlers.common import return_to_main_menu
    
    parts = parse_callback_data(cb.data, 3)
    event_id = parse_int_safe(parts[2]) if parts else None
    
    if event_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Restore the task
    success = await repo.restore_completed_task(user_id=cb.from_user.id, event_id=event_id)
    
    if success:
        await return_to_main_menu(
            cb, repo, state=state, answer_text="Tehtävä palautettu aktiiviseksi", force_refresh=True
        )
    else:
        # Task might already be active, deleted, or event not found
        await cb.answer("Tehtävä on jo aktiivinen, poistettu, tai sitä ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


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
        await return_to_main_menu(cb, repo, state=state)
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
    parts = parse_callback_data(cb.data, 3)
    event_id = parse_int_safe(parts[2]) if parts else None
    
    if event_id is None:
        await cb.answer("Virheellinen tehtävä-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    success = await repo.restore_deleted_task(user_id=cb.from_user.id, event_id=event_id)
    if success:
        await return_to_main_menu(cb, repo, state=state, answer_text="Tehtävä palautettu", force_refresh=True)
    else:
        await cb.answer("Tehtävää ei voitu palauttaa.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)


@router.callback_query(F.data == "view:stats")
async def cb_stats_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open stats main menu"""
    from app.ui import stats_menu_kb, render_stats_menu_header
    
    await state.clear()
    if cb.message:
        await cb.message.edit_text(render_stats_menu_header(), reply_markup=stats_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "stats:all_time")
async def cb_stats_all_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show all time statistics"""
    await state.clear()
    
    stats = await repo.get_all_time_stats(user_id=cb.from_user.id)
    
    if cb.message:
        await cb.message.edit_text(
            render_all_time_stats(stats),
            reply_markup=stats_menu_kb()
        )
    await cb.answer()


@router.callback_query(F.data == "stats:ai")
async def cb_stats_ai(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show AI analysis period selection"""
    import os
    
    await state.clear()
    
    # Check if OpenAI API key is configured
    api_key = os.getenv("OPENAI_API_KEY")
    
    if cb.message:
        if not api_key:
            await cb.message.edit_text(
                render_ai_analysis_disabled(),
                reply_markup=stats_menu_kb()
            )
        else:
            await cb.message.edit_text(
                render_ai_analysis_header(),
                reply_markup=stats_ai_period_kb()
            )
    await cb.answer()


@router.callback_query(F.data.startswith("stats:ai:"))
async def cb_stats_ai_period(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle AI analysis period selection"""
    import os
    
    await state.clear()
    
    parts = cb.data.split(":", 2)
    period_str = parts[2] if len(parts) > 2 else "7"
    
    # Check if OpenAI API key is configured
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        if cb.message:
            await cb.message.edit_text(
                render_ai_analysis_disabled(),
                reply_markup=stats_menu_kb()
            )
        await cb.answer()
        return
    
    # Map period to readable text
    period_map = {
        "1": "1 päivä",
        "7": "1 viikko",
        "30": "1 kuukausi",
        "365": "1 vuosi",
        "custom": "Muu ajanjakso"
    }
    period_text = period_map.get(period_str, f"{period_str} päivää")
    
    # Placeholder implementation (AI analysis not yet implemented)
    if cb.message:
        await cb.message.edit_text(
            render_ai_analysis_placeholder(period_text),
            reply_markup=stats_menu_kb()
        )
    await cb.answer()


@router.callback_query(F.data == "stats:reset")
async def cb_stats_reset(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show reset stats confirmation"""
    await state.clear()
    
    if cb.message:
        await cb.message.edit_text(
            render_reset_stats_confirm(),
            reply_markup=stats_reset_confirm_kb()
        )
    await cb.answer()


@router.callback_query(F.data == "stats:reset_confirm")
async def cb_stats_reset_confirm(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Confirm and execute stats reset"""
    await state.clear()
    
    success = await repo.reset_stats(user_id=cb.from_user.id)
    
    if cb.message:
        if success:
            await cb.message.edit_text(
                "✅ Tilastot nollattu\n\nTilastot ja lokit on poistettu. Tehtävät säilyvät.",
                reply_markup=stats_menu_kb()
            )
        else:
            await cb.message.edit_text(
                "❌ Virhe: Tilastojen nollaus epäonnistui.",
                reply_markup=stats_menu_kb()
            )
    await cb.answer("Tilastot nollattu" if success else "Virhe")


@router.callback_query(F.data.startswith("stats:"))
async def cb_stats_period(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Legacy stats period handler (for backward compatibility) - matches stats:7, stats:30, etc."""
    # Skip if it's one of the new handlers
    if cb.data in ("stats:all_time", "stats:ai", "stats:reset", "stats:reset_confirm"):
        return
    if cb.data.startswith("stats:ai:"):
        return
    
    await state.clear()
    parts = cb.data.split(":", 1)
    days_str = parts[1] if len(parts) > 1 else "7"
    days = parse_int_safe(days_str, default=7)
    
    stats = await repo.get_statistics(user_id=cb.from_user.id, days=days)
    if cb.message:
        await cb.message.edit_text(render_stats_header(stats), reply_markup=stats_kb())
    await cb.answer()
