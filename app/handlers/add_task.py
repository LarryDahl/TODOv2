"""
Add task flow handlers.
"""
from __future__ import annotations

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


@router.callback_query(F.data == "view:add")
async def cb_add_task(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.set_state(Flow.waiting_task_type)
    if cb.message:
        await cb.message.edit_text(render_add_type_header(), reply_markup=add_task_type_kb())
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
    text = (message.text or "").strip()
    if not text:
        await message.answer("Tyhjä tehtävä ei kelpaa. Kirjoita tehtävä viestinä.")
        return

    data = await state.get_data()
    
    # Check if we're in the add task flow
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


@router.message()
async def msg_default_add_task(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Default: any text message = new task (by default)"""
    if message.text and message.text.startswith("/"):
        await return_to_main_menu(message, repo, state=state)
        return

    text = (message.text or "").strip()
    if not text:
        await return_to_main_menu(message, repo, state=state)
        return

    # Add as regular task with defaults (priority parsed in add_task)
    await repo.add_task(
        user_id=message.from_user.id,
        text=text,
        task_type='regular',
        difficulty=5,
        category=''
    )
    await return_to_main_menu(message, repo, state=state)
