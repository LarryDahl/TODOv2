"""
Project edit handlers for managing project steps.

ROUTER MAP:
- edit:projects - Show list of all projects for editing
- edit:project:<project_id> - Show project steps edit view
- edit:project:rewrite:<project_id> - Start rewriting all project steps
- edit:step:menu:<step_id> - Show step edit menu
- edit:step:text:<step_id> - Start editing step text
- edit:step:add:<project_id> - Add new step to project
- edit:step:delete:<step_id> - Delete step
- edit:step:activate:<step_id> - Activate step
- edit:step:deactivate:<step_id> - Deactivate step (set to pending)
- edit:step:complete:<step_id> - Mark step as completed
- edit:step:move_up:<step_id> - Move step up in order
- edit:step:move_down:<step_id> - Move step down in order
- edit:step:reorder:<project_id> - Reorder all steps
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db import TasksRepo
from app.handlers.common import CtxKeys, Flow, return_to_main_menu
from app.ui import (
    project_steps_edit_kb,
    projects_edit_kb,
    render_project_steps_edit_header,
    render_projects_edit_header,
    step_edit_menu_kb,
)
from app.utils import parse_callback_data, parse_int_safe

router = Router()


@router.callback_query(F.data == "edit:projects")
async def cb_edit_projects(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show list of all projects for editing"""
    await state.clear()
    projects = await repo.list_all_projects()
    
    if cb.message:
        await cb.message.edit_text(
            render_projects_edit_header(),
            reply_markup=projects_edit_kb(projects)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("edit:project:rewrite:"))
async def cb_project_rewrite(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start rewriting all project steps"""
    parts = parse_callback_data(cb.data, 4)
    project_id = parse_int_safe(parts[3]) if parts else None
    
    if project_id is None:
        await cb.answer("Virheellinen projektin-id.", show_alert=True)
        return
    
    # Verify project exists
    project = await repo.get_project(project_id)
    if not project:
        await cb.answer("Projektia ei löytynyt.", show_alert=True)
        return
    
    # Store project_id in state
    await state.update_data({CtxKeys.edit_task_id: project_id})  # Reuse edit_task_id key
    await state.set_state(Flow.waiting_project_rewrite_steps)
    
    if cb.message:
        await cb.message.edit_text(
            "Uudelleenkirjoita projektin askeleet\n\n"
            "Lähetä askeleet, yksi per rivi:\n"
            "(Nykyiset askeleet korvataan uusilla)"
        )
    await cb.answer()


@router.callback_query(F.data.startswith("edit:project:delete:"))
async def cb_edit_project_delete(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Delete project and all its steps; return to edit projects list or project list"""
    await state.clear()
    parts = parse_callback_data(cb.data, 4)
    project_id = parse_int_safe(parts[3]) if parts and len(parts) >= 4 else None
    if project_id is None:
        await cb.answer("Virheellinen projektin-id.", show_alert=True)
        return
    success = await repo.delete_project(project_id)
    if not success:
        await cb.answer("Projektia ei löytynyt.", show_alert=True)
        return
    projects = await repo.list_all_projects()
    from app.ui import render_projects_edit_header, projects_edit_kb
    if cb.message:
        await cb.message.edit_text(
            render_projects_edit_header(),
            reply_markup=projects_edit_kb(projects),
        )
    await cb.answer("Projekti poistettu")


@router.callback_query(F.data.startswith("edit:project:"))
async def cb_edit_project_steps(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show project steps edit view (edit:project:<id>; delete/rewrite have own handlers)"""
    await state.clear()

    parts = parse_callback_data(cb.data, 3)
    project_id = parse_int_safe(parts[2]) if parts else None

    if project_id is None:
        await cb.answer("Virheellinen projektin-id.", show_alert=True)
        return

    # Get project and steps
    project = await repo.get_project(project_id)
    if not project:
        await cb.answer("Projektia ei löytynyt.", show_alert=True)
        return

    steps = await repo.get_project_steps(project_id)

    if cb.message:
        await cb.message.edit_text(
            render_project_steps_edit_header(project, steps),
            reply_markup=project_steps_edit_kb(project, steps)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("edit:step:menu:"))
async def cb_step_edit_menu(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show step edit menu"""
    await state.clear()
    
    parts = parse_callback_data(cb.data, 4)
    step_id = parse_int_safe(parts[3]) if parts else None
    
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Get step and project
    step = await repo.get_project_step(step_id)
    if not step:
        await cb.answer("Askelia ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    project_id = step.get('project_id', 0)
    project = await repo.get_project(project_id)
    if not project:
        await cb.answer("Projektia ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    
    # Show step edit menu
    step_text = step.get('text', '')
    status = step.get('status', 'pending')
    order_index = step.get('order_index', 0)
    
    header = f"Muokkaa askelta\n\n{order_index}. {step_text}\n\nStatus: {status}"
    
    if cb.message:
        await cb.message.edit_text(
            header,
            reply_markup=step_edit_menu_kb(step, project_id)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("edit:step:text:"))
async def cb_step_edit_text(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start editing step text"""
    parts = parse_callback_data(cb.data, 4)
    step_id = parse_int_safe(parts[3]) if parts else None
    
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        return
    
    # Get step
    step = await repo.get_project_step(step_id)
    if not step:
        await cb.answer("Askelia ei löytynyt.", show_alert=True)
        return
    
    # Store step_id in state
    await state.update_data({CtxKeys.edit_task_id: step_id})  # Reuse edit_task_id key
    await state.set_state(Flow.waiting_edit_task_text)
    
    step_text = step.get('text', '')
    
    if cb.message:
        await cb.message.edit_text(
            f"Muokkaa askeltekstiä:\n\nNykyinen: {step_text}\n\nLähetä uusi teksti:"
        )
    await cb.answer()


@router.message(Flow.waiting_edit_task_text)
async def msg_edit_step_text(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle step text edit submission"""
    data = await state.get_data()
    step_id = data.get(CtxKeys.edit_task_id)
    
    if step_id is None:
        await return_to_main_menu(message, repo, state=state)
        return
    
    new_text = message.text.strip() if message.text else ""
    
    if not new_text:
        await message.answer("Teksti ei voi olla tyhjä. Yritä uudelleen:")
        return
    
    # Update step text
    success = await repo.update_project_step_text(step_id=step_id, new_text=new_text)
    
    if success:
        # Get project_id to return to project steps view
        step = await repo.get_project_step(step_id)
        if step:
            project_id = step.get('project_id', 0)
            await state.clear()
            
            # Return to project steps edit view
            project = await repo.get_project(project_id)
            if project:
                steps = await repo.get_project_steps(project_id)
                from app.ui import project_steps_edit_kb, render_project_steps_edit_header
                
                await message.answer(
                    render_project_steps_edit_header(project, steps),
                    reply_markup=project_steps_edit_kb(project, steps)
                )
                return
    
    await return_to_main_menu(message, repo, state=state)


@router.callback_query(F.data.startswith("edit:step:delete:"))
async def cb_step_delete(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Delete a project step"""
    parts = parse_callback_data(cb.data, 4)
    step_id = parse_int_safe(parts[3]) if parts else None
    
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        return
    
    # Get step info before deletion to get project_id
    step = await repo.get_project_step(step_id)
    if not step:
        await cb.answer("Askelia ei löytynyt.", show_alert=True)
        return
    
    project_id = step.get('project_id', 0)
    
    # Delete step
    success = await repo.delete_project_step(step_id=step_id)
    
    if success:
        # Get project and refresh steps view
        project = await repo.get_project(project_id)
        if project:
            steps = await repo.get_project_steps(project_id)
            
            await cb.message.edit_text(
                render_project_steps_edit_header(project, steps),
                reply_markup=project_steps_edit_kb(project, steps)
            )
            await cb.answer("Askel poistettu")
            return
    
    await cb.answer("Virhe askelta poistettaessa.", show_alert=True)


@router.callback_query(F.data.startswith("edit:step:activate:"))
async def cb_step_activate(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Activate a step (set status to active)"""
    parts = parse_callback_data(cb.data, 4)
    step_id = parse_int_safe(parts[3]) if parts else None
    
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        return
    
    # Activate step
    success = await repo.update_project_step_status(step_id=step_id, status='active')
    
    if success:
        # Refresh project steps view
        step = await repo.get_project_step(step_id)
        if step:
            project_id = step.get('project_id', 0)
            project = await repo.get_project(project_id)
            if project:
                steps = await repo.get_project_steps(project_id)
                
                await cb.message.edit_text(
                    render_project_steps_edit_header(project, steps),
                    reply_markup=project_steps_edit_kb(project, steps)
                )
                await cb.answer("Askel aktivoitu")
                return
    
    await cb.answer("Virhe askelta aktivoidessa.", show_alert=True)


@router.callback_query(F.data.startswith("edit:step:deactivate:"))
async def cb_step_deactivate(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Deactivate a step (set status to pending)"""
    parts = parse_callback_data(cb.data, 4)
    step_id = parse_int_safe(parts[3]) if parts else None
    
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        return
    
    # Deactivate step
    success = await repo.update_project_step_status(step_id=step_id, status='pending')
    
    if success:
        # Refresh project steps view
        step = await repo.get_project_step(step_id)
        if step:
            project_id = step.get('project_id', 0)
            project = await repo.get_project(project_id)
            if project:
                steps = await repo.get_project_steps(project_id)
                
                await cb.message.edit_text(
                    render_project_steps_edit_header(project, steps),
                    reply_markup=project_steps_edit_kb(project, steps)
                )
                await cb.answer("Askel palautettu odottamaan")
                return
    
    await cb.answer("Virhe askelta deaktivoidessa.", show_alert=True)


@router.callback_query(F.data.startswith("edit:step:complete:"))
async def cb_step_complete(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Mark step as completed"""
    parts = parse_callback_data(cb.data, 4)
    step_id = parse_int_safe(parts[3]) if parts else None
    
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        return
    
    # Complete step
    now = repo._now_iso()
    success = await repo.mark_project_step_completed(step_id=step_id, done_at=now)
    
    if success:
        # Refresh project steps view
        step = await repo.get_project_step(step_id)
        if step:
            project_id = step.get('project_id', 0)
            project = await repo.get_project(project_id)
            if project:
                steps = await repo.get_project_steps(project_id)
                
                await cb.message.edit_text(
                    render_project_steps_edit_header(project, steps),
                    reply_markup=project_steps_edit_kb(project, steps)
                )
                await cb.answer("Askel merkitty tehdyksi")
                return
    
    await cb.answer("Virhe askelta merkittäessä tehdyksi.", show_alert=True)


@router.callback_query(F.data.startswith("edit:step:move_up:"))
async def cb_step_move_up(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Move step up in order"""
    parts = parse_callback_data(cb.data, 4)
    step_id = parse_int_safe(parts[3]) if parts else None
    
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        return
    
    # Get step info before moving
    step = await repo.get_project_step(step_id)
    if not step:
        await cb.answer("Askelia ei löytynyt.", show_alert=True)
        return
    
    project_id = step.get('project_id', 0)
    
    # Move step up
    success = await repo.move_project_step(step_id=step_id, direction='up')
    
    if success:
        # Refresh project steps view
        project = await repo.get_project(project_id)
        if project:
            steps = await repo.get_project_steps(project_id)
            
            await cb.message.edit_text(
                render_project_steps_edit_header(project, steps),
                reply_markup=project_steps_edit_kb(project, steps)
            )
            await cb.answer("Askel siirretty ylös")
            return
    
    await cb.answer("Askelia ei voitu siirtää ylös.", show_alert=True)


@router.callback_query(F.data.startswith("edit:step:move_down:"))
async def cb_step_move_down(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Move step down in order"""
    parts = parse_callback_data(cb.data, 4)
    step_id = parse_int_safe(parts[3]) if parts else None
    
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        return
    
    # Get step info before moving
    step = await repo.get_project_step(step_id)
    if not step:
        await cb.answer("Askelia ei löytynyt.", show_alert=True)
        return
    
    project_id = step.get('project_id', 0)
    
    # Move step down
    success = await repo.move_project_step(step_id=step_id, direction='down')
    
    if success:
        # Refresh project steps view
        project = await repo.get_project(project_id)
        if project:
            steps = await repo.get_project_steps(project_id)
            
            await cb.message.edit_text(
                render_project_steps_edit_header(project, steps),
                reply_markup=project_steps_edit_kb(project, steps)
            )
            await cb.answer("Askel siirretty alas")
            return
    
    await cb.answer("Askelia ei voitu siirtää alas.", show_alert=True)


@router.callback_query(F.data.startswith("edit:step:add:"))
async def cb_step_add(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start adding a new step to project"""
    parts = parse_callback_data(cb.data, 4)
    project_id = parse_int_safe(parts[3]) if parts else None
    
    if project_id is None:
        await cb.answer("Virheellinen projektin-id.", show_alert=True)
        return
    
    # Store project_id in state (reuse edit_task_id key for step text input)
    await state.update_data({CtxKeys.edit_task_id: project_id})
    await state.set_state(Flow.waiting_project_step_text)
    
    if cb.message:
        await cb.message.edit_text(
            f"Lisää uusi askel projektiin.\n\nLähetä askelteksti:"
        )
    await cb.answer()


@router.message(Flow.waiting_project_step_text)
async def msg_add_step_text(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle new step text submission"""
    data = await state.get_data()
    project_id = data.get(CtxKeys.edit_task_id)
    
    if project_id is None:
        await return_to_main_menu(message, repo, state=state)
        return
    
    step_text = message.text.strip() if message.text else ""
    
    if not step_text:
        await message.answer("Teksti ei voi olla tyhjä. Yritä uudelleen:")
        return
    
    # Add step to project
    step_id = await repo.add_step_to_project(project_id=project_id, step_text=step_text)
    
    if step_id:
        await state.clear()
        
        # Return to project steps edit view
        project = await repo.get_project(project_id)
        if project:
            steps = await repo.get_project_steps(project_id)
            
            await message.answer(
                render_project_steps_edit_header(project, steps),
                reply_markup=project_steps_edit_kb(project, steps)
            )
            return
    
    await return_to_main_menu(message, repo, state=state)


@router.message(Flow.waiting_project_rewrite_steps)
async def msg_project_rewrite_steps(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Handle rewritten project steps input"""
    data = await state.get_data()
    project_id = data.get(CtxKeys.edit_task_id)
    
    if project_id is None:
        await return_to_main_menu(message, repo, state=state)
        return
    
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
    
    # Verify project still exists
    project = await repo.get_project(project_id)
    if not project:
        await message.answer("Virhe: projektia ei löytynyt.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    # Delete all existing steps
    await repo.delete_all_project_steps(project_id=project_id)
    
    # Add new steps
    now = repo._now_iso()
    await repo.add_project_steps(project_id=project_id, list_of_texts=steps, now=now)
    
    # Activate first step atomically (ensures consistency)
    success = await repo.activate_first_project_step(project_id=project_id, now=now)
    if not success:
        await message.answer("Virhe: ensimmäistä askelta ei voitu aktivoida.")
        await return_to_main_menu(message, repo, state=state)
        return
    
    await state.clear()
    
    # Return to project steps edit view
    project = await repo.get_project(project_id)
    if project:
        steps_list = await repo.get_project_steps(project_id)
        
        await message.answer(
            render_project_steps_edit_header(project, steps_list),
            reply_markup=project_steps_edit_kb(project, steps_list)
        )
        return
    
    await return_to_main_menu(message, repo, state=state)
