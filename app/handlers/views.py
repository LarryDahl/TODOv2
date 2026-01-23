"""
View handlers for navigation and display.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.handlers.common import CtxKeys, _show_home_from_cb, _show_home_from_message
from app.utils import parse_callback_data, parse_int_safe
from app.ui import (
    deleted_tasks_kb,
    done_tasks_kb,
    edit_kb,
    render_edit_header,
    render_settings_header,
    render_stats_header,
    settings_kb,
    stats_kb,
)

router = Router()


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
    days_str = parts[1] if len(parts) > 1 else "7"
    days = parse_int_safe(days_str, default=7)
    
    stats = await repo.get_statistics(user_id=cb.from_user.id, days=days)
    if cb.message:
        await cb.message.edit_text(render_stats_header(stats), reply_markup=stats_kb())
    await cb.answer()
