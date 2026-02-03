"""
Add task flow handlers.

ROUTER MAP:
- home:plus - Open plus menu (add task/project/edit)
- add:task_type - Open task type selection
- add:regular - Start regular task flow
- add:scheduled - Start scheduled task flow
- add:deadline - Start deadline task flow
- add:project - Start project creation flow
- add:type:<type> - Set task type (legacy)
- add:difficulty:<n> - Set difficulty (legacy)
- add:category:<cat> - Set category (legacy)
- add:scheduled:date:<offset> - Select scheduled date
- add:scheduled:time:<time> - Select scheduled time
- add:deadline:date:<offset> - Select deadline date
- add:deadline:time:<time> - Select deadline time
- view:add_backlog - Legacy add project (use add:project)
"""
from __future__ import annotations

import aiosqlite

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.handlers.common import CtxKeys, Flow, return_to_main_menu
from app.utils import parse_callback_data, parse_int_safe
from app.ui import (
    add_task_category_kb,
    add_task_difficulty_kb,
    add_task_type_kb,
    date_picker_kb,
    render_add_category_header,
    render_add_difficulty_header,
    render_add_type_header,
)

router = Router()


@router.callback_query(F.data.in_(["view:add", "home:plus"]))
async def cb_plus_menu(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open plus menu with main options"""
    from app.ui import plus_menu_kb, render_plus_menu_header
    
    await state.clear()  # Clear any existing state
    if cb.message:
        await cb.message.edit_text(render_plus_menu_header(), reply_markup=plus_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "add:task_type")
async def cb_add_task_type(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open task type selection submenu"""
    from app.ui import add_task_type_kb, render_add_type_header
    
    await state.clear()
    if cb.message:
        await cb.message.edit_text(render_add_type_header(), reply_markup=add_task_type_kb())
    await cb.answer()


@router.callback_query(F.data == "add:regular")
async def cb_add_regular(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start regular task flow - just ask for text"""
    await state.clear()
    await state.set_state(Flow.waiting_new_task_text)
    # Store that this is a regular task (no type/difficulty/category selection)
    await state.update_data({
        CtxKeys.add_task_type: 'regular',
        CtxKeys.add_task_difficulty: 5,
        CtxKeys.add_task_category: ''
    })
    
    if cb.message:
        await cb.message.answer("Kirjoita tehtävän teksti viestinä:")
    await cb.answer()


@router.callback_query(F.data == "add:scheduled")
async def cb_add_scheduled(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start scheduled task flow - date -> time -> text"""
    from app.ui import date_picker_kb
    
    await state.clear()
    # Store that this is a scheduled task
    await state.update_data({
        CtxKeys.add_task_type: 'scheduled',
        CtxKeys.add_task_difficulty: 5,
        CtxKeys.add_task_category: ''
    })
    
    if cb.message:
        await cb.message.edit_text(
            "🗓 Ajastettu tehtävä\n\nValitse päivämäärä:",
            reply_markup=date_picker_kb("add:scheduled:date", include_none=False)
        )
    await cb.answer()


@router.callback_query(F.data == "add:deadline")
async def cb_add_deadline(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start deadline task flow - date -> time -> text"""
    from app.ui import date_picker_kb
    
    await state.clear()
    # Store that this is a deadline task
    await state.update_data({
        CtxKeys.add_task_type: 'deadline',
        CtxKeys.add_task_difficulty: 5,
        CtxKeys.add_task_category: ''
    })
    
    if cb.message:
        await cb.message.edit_text(
            "⏰ Määräaikainen tehtävä\n\nValitse päivämäärä:",
            reply_markup=date_picker_kb("add:deadline:date")
        )
    await cb.answer()


@router.callback_query(F.data == "add:project")
async def cb_add_project(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start project creation flow (same as view:add_backlog)"""
    await state.clear()
    await state.set_state(Flow.waiting_project_name)
    if cb.message:
        await cb.message.answer("Projektin nimi?")
    await cb.answer()


@router.callback_query(F.data == "home:edit")
async def cb_edit_from_plus(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open edit tasks view from plus menu"""
    from app.ui import edit_kb, render_edit_header
    
    await state.clear()
    tasks = await repo.list_tasks(user_id=cb.from_user.id)
    if cb.message:
        await cb.message.edit_text(render_edit_header(), reply_markup=edit_kb(tasks))
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
    
    # Regular task - add immediately (priority will be parsed in add_task)
    await repo.add_task(
        user_id=cb.from_user.id,
        text=task_text,
        task_type=task_type,
        difficulty=difficulty,
        category=category
    )
    await return_to_main_menu(cb, repo, state=state, answer_text="Tehtävä lisätty", force_refresh=True)


@router.message(Flow.waiting_new_task_text)
async def msg_new_task(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """
    Handle new task text input.
    
    This handler is used for:
    - Regular tasks from plus menu (add:regular) - adds immediately
    - Old flow with type/difficulty/category selection (legacy, still supported)
    """
    text = (message.text or "").strip()
    if not text:
        await message.answer("Tyhjä tehtävä ei kelpaa. Kirjoita tehtävä viestinä.")
        return

    data = await state.get_data()
    
    # Check if we're in the simplified flow (from plus menu)
    # If add_task_type is 'regular' and we have default difficulty/category, add immediately
    task_type = data.get(CtxKeys.add_task_type, 'regular')
    difficulty = data.get(CtxKeys.add_task_difficulty, 5)
    category = data.get(CtxKeys.add_task_category, '')
    
    # If it's a regular task with defaults, add immediately (simplified flow)
    if task_type == 'regular' and difficulty == 5 and category == '':
        await repo.add_task(
            user_id=message.from_user.id,
            text=text,
            task_type='regular',
            difficulty=5,
            category=''
        )
        await return_to_main_menu(message, repo, state=state, answer_text="Tehtävä lisätty", force_refresh=True)
        return
    
    # Legacy flow: continue to difficulty selection if type is set but not defaults
    if CtxKeys.add_task_type in data:
        # Store text and continue to difficulty selection (priority parsed in add_task)
        await state.update_data({CtxKeys.add_task_text: text})
        await state.set_state(Flow.waiting_task_difficulty)
        await message.answer(render_add_difficulty_header(), reply_markup=add_task_difficulty_kb())
        return
    
    # Fallback: add as regular task (shouldn't happen in normal flow)
    await repo.add_task(
        user_id=message.from_user.id,
        text=text,
        task_type='regular',
        difficulty=5,
        category=''
    )
    await return_to_main_menu(message, repo, state=state)


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


@router.callback_query(F.data == "view:add_backlog")
async def cb_add_backlog(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start backlog project creation flow"""
    await state.set_state(Flow.waiting_project_name)
    if cb.message:
        await cb.message.answer("Projektin nimi?")
    await cb.answer()


@router.message(Flow.waiting_project_name)
async def msg_project_name(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle project name input"""
    from app.handlers.common import return_to_main_menu
    
    project_name = (message.text or "").strip()
    
    # Handle cancellation
    if not project_name or project_name.lower() in ("/peruuta", "/cancel", "/peru"):
        await return_to_main_menu(message, repo, state=state)
        return
    
    # Store project name and ask for steps
    await state.update_data({CtxKeys.project_name: project_name})
    await state.set_state(Flow.waiting_project_steps)
    await message.answer("Lähetä askeleet, yksi per rivi:")


@router.message(Flow.waiting_project_steps)
async def msg_project_steps(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle project steps input"""
    from app.handlers.common import return_to_main_menu
    
    text = message.text or ""
    
    # Handle cancellation
    if text.strip().lower() in ("/peruuta", "/cancel", "/peru"):
        await return_to_main_menu(message, repo, state=state)
        return
    
    # Parse steps (one per line, trim empty lines)
    steps = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Validate: need at least 2 steps
    if len(steps) < 2:
        await message.answer("Tarvitaan vähintään 2 askelta. Lähetä askeleet, yksi per rivi:")
        return
    
    # Get project name from state
    data = await state.get_data()
    project_name = data.get(CtxKeys.project_name)
    
    if not project_name:
        await message.answer("Virhe: projektin nimi puuttuu.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    # Create project
    now = repo._now_iso()
    project_id = await repo.create_project(title=project_name, now=now)
    
    # Add steps
    await repo.add_project_steps(project_id=project_id, list_of_texts=steps, now=now)
    
    # Activate first step atomically (ensures consistency)
    success = await repo.activate_first_project_step(project_id=project_id, now=now)
    if not success:
        await message.answer("Virhe: ensimmäistä askelta ei voitu aktivoida.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    await return_to_main_menu(message, repo, state=state, answer_text="Projekti luotu", force_refresh=True)


# REMOVED: msg_default_add_task handler
# This functionality is now handled by app/handlers/text_messages.py
# which ensures "free message = new task" only when user is NOT in FSM state.
# The centralized handler checks FSM state before creating a task.
