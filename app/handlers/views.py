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

import asyncio

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.callbacks import (
    NAV_HOME,
    NAV_REFRESH,
    NAV_EDIT,
    ROUTINE_EDIT_MENU_ANY,
    PREFIX_DELETED_PAGE,
    PREFIX_DELETED_RESTORE,
    PREFIX_DONE_PAGE,
    PREFIX_DONE_RESTORE,
    PREFIX_PROJ_STEP_TOGGLE,
    PREFIX_ROUTINE_ADD,
    PREFIX_ROUTINE_DEL,
    PREFIX_ROUTINE_EDIT_LIST,
    PREFIX_ROUTINE_EDIT_TASK,
    PREFIX_ROUTINE_QUITTED,
    PREFIX_ROUTINE_TOGGLE,
    PREFIX_SETTINGS_TZ,
    PREFIX_STATS_AI,
    PREFIX_VIEW_PROJECT,
    SETTINGS_EXPORT_DB,
    SETTINGS_RESET,
    SETTINGS_ROUTINES_EDIT_EVENING_TIME,
    SETTINGS_ROUTINES_EDIT_MORNING_TIME,
    SETTINGS_ROUTINES_EVENING_BACK,
    SETTINGS_ROUTINES_MORNING_BACK,
    SETTINGS_ROUTINES_PERUUTA,
    SETTINGS_TIMEZONE,
    SETTINGS_TOGGLE_EVENING_ROUTINES,
    SETTINGS_TOGGLE_MORNING_ROUTINES,
    STATS_ALL_TIME,
    STATS_AI,
    STATS_MENU_ACTIONS,
    STATS_RESET,
    STATS_RESET_CONFIRM,
    VIEW_DELETED,
    VIEW_DONE,
    VIEW_PROJECTS,
    VIEW_SETTINGS,
    VIEW_STATS,
    NOOP,
    parse_callback,
)
from app.db import TasksRepo
from app.handlers.common import CtxKeys, Flow, return_to_main_menu
from app.utils import parse_hhmm_strict, parse_int_safe, parse_time_string
from app.ai_analysis import FALLBACK_MESSAGE as AI_ANALYSIS_FALLBACK, run_ai_analysis
from app.ui import (
    deleted_tasks_kb,
    done_tasks_kb,
    edit_kb,
    project_detail_view_kb,
    projects_list_kb,
    render_edit_header,
    render_project_detail,
    render_projects_list_header,
    render_settings_header,
    render_stats_header,
    render_all_time_stats,
    render_ai_analysis_header,
    render_ai_analysis_disabled,
    render_ai_analysis_placeholder,
    render_ai_analysis_result,
    render_ai_analysis_error,
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


@router.callback_query(F.data.in_(NAV_HOME))
async def cb_home(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Return to home view"""
    await return_to_main_menu(cb, repo, state=state, force_refresh=True)


@router.callback_query(F.data.in_(NAV_REFRESH))
async def cb_refresh(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """
    Refresh the main menu task list to show latest changes and approaching deadlines.
    Re-renders existing message if possible. Shuffles suggestion slots (tehtäväehdotukset).
    """
    await return_to_main_menu(
        cb, repo, state=state,
        answer_text="Lista päivitetty", force_refresh=True, shuffle_suggestions=True,
    )


@router.callback_query(F.data == NOOP)
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data == VIEW_SETTINGS)
async def cb_settings(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open settings view"""
    await state.clear()
    
    settings = await repo.get_user_settings(user_id=cb.from_user.id)
    
    if cb.message:
        await cb.message.edit_text(
            render_settings_header(settings),
            reply_markup=settings_kb(
                morning_routines_enabled=settings.get("morning_routines_enabled", False),
                evening_routines_enabled=settings.get("evening_routines_enabled", False),
            )
        )
    await cb.answer()


@router.callback_query(F.data == SETTINGS_TIMEZONE)
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


@router.callback_query(F.data.startswith(PREFIX_SETTINGS_TZ))
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
                reply_markup=settings_kb(
                    morning_routines_enabled=settings.get("morning_routines_enabled", False),
                    evening_routines_enabled=settings.get("evening_routines_enabled", False),
                )
            )
            await cb.answer(render_timezone_set(timezone))
        else:
            await cb.answer("Virhe: Aikavyöhykkeen asetus epäonnistui.", show_alert=True)


@router.callback_query(F.data == SETTINGS_TOGGLE_MORNING_ROUTINES)
async def cb_settings_toggle_morning_routines(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Toggle aamurutiinit päälle/pois"""
    from app.ui import render_settings_header, settings_kb
    await state.clear()
    new_value = await repo.toggle_morning_routines_enabled(user_id=cb.from_user.id)
    if cb.message:
        settings = await repo.get_user_settings(user_id=cb.from_user.id)
        await cb.message.edit_text(
            render_settings_header(settings),
            reply_markup=settings_kb(
                morning_routines_enabled=settings.get("morning_routines_enabled", False),
                evening_routines_enabled=settings.get("evening_routines_enabled", False),
            )
        )
    status = "päällä" if new_value else "poissa käytöstä"
    await cb.answer(f"Aamurutiinit {status}")


@router.callback_query(F.data == SETTINGS_TOGGLE_EVENING_ROUTINES)
async def cb_settings_toggle_evening_routines(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Toggle iltarutiinit päälle/pois"""
    from app.ui import render_settings_header, settings_kb
    await state.clear()
    new_value = await repo.toggle_evening_routines_enabled(user_id=cb.from_user.id)
    if cb.message:
        settings = await repo.get_user_settings(user_id=cb.from_user.id)
        await cb.message.edit_text(
            render_settings_header(settings),
            reply_markup=settings_kb(
                morning_routines_enabled=settings.get("morning_routines_enabled", False),
                evening_routines_enabled=settings.get("evening_routines_enabled", False),
            )
        )
    status = "päällä" if new_value else "poissa käytöstä"
    await cb.answer(f"Iltarutiinit {status}")


@router.callback_query(F.data.in_(ROUTINE_EDIT_MENU_ANY))
async def cb_routine_edit_menu(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Muokkaa rutiineja: valinta aamu/ilta + aikaikkunat. Palaa-napista tulee settings:routines:edit_menu."""
    from app.ui import routine_edit_menu_kb, render_routine_edit_menu_header
    await state.clear()
    windows = await repo.get_routine_windows(cb.from_user.id)
    if cb.message:
        await cb.message.edit_text(
            render_routine_edit_menu_header(),
            reply_markup=routine_edit_menu_kb(windows)
        )
    await cb.answer()


@router.callback_query(F.data == SETTINGS_ROUTINES_EDIT_MORNING_TIME)
async def cb_routine_edit_morning_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Avaa aamun aikaikkunan muokkaus. Näyttää nykyisen asetuksen ja napeilla valinta."""
    from app.ui import build_routine_morning_time_kb, render_morning_start_prompt
    await state.clear()
    await state.set_state(Flow.waiting_morning_start)
    windows = await repo.get_routine_windows(cb.from_user.id)
    await state.update_data(**{CtxKeys.routine_windows: windows})
    if cb.message:
        await cb.message.edit_text(
            render_morning_start_prompt(windows),
            reply_markup=build_routine_morning_time_kb("start")
        )
    await cb.answer()


@router.callback_query(F.data == SETTINGS_ROUTINES_EDIT_EVENING_TIME)
async def cb_routine_edit_evening_time(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Avaa illan aikaikkunan muokkaus. Näyttää nykyisen asetuksen ja napeilla valinta."""
    from app.ui import build_routine_evening_time_kb, render_evening_start_prompt
    await state.clear()
    await state.set_state(Flow.waiting_evening_start)
    windows = await repo.get_routine_windows(cb.from_user.id)
    await state.update_data(**{CtxKeys.routine_windows: windows})
    if cb.message:
        await cb.message.edit_text(
            render_evening_start_prompt(windows),
            reply_markup=build_routine_evening_time_kb("start")
        )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^settings:routines:morning:start:[0-9]{2}:[0-9]{2}$"))
async def cb_routine_time_morning_start(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Aamu: käyttäjä valitsi alkuaikan (nappi) -> tallenna FSM:ään ja näytä lopetusaika-vaihe."""
    from app.ui import build_routine_morning_time_kb, render_morning_end_prompt
    parts = cb.data.split(":")
    if len(parts) < 6:
        await cb.answer()
        return
    start_str = f"{parts[4]}:{parts[5]}"
    data = await state.get_data()
    windows = data.get(CtxKeys.routine_windows) or {}
    await state.update_data(**{CtxKeys.routine_morning_start: start_str})
    await state.set_state(Flow.waiting_morning_end)
    if cb.message:
        await cb.message.edit_text(
            render_morning_end_prompt(windows, start_str),
            reply_markup=build_routine_morning_time_kb("end")
        )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^settings:routines:evening:start:[0-9]{2}:[0-9]{2}$"))
async def cb_routine_time_evening_start(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Ilta: käyttäjä valitsi alkuaikan (nappi) -> tallenna FSM:ään ja näytä lopetusaika-vaihe."""
    from app.ui import build_routine_evening_time_kb, render_evening_end_prompt
    parts = cb.data.split(":")
    if len(parts) < 6:
        await cb.answer()
        return
    start_str = f"{parts[4]}:{parts[5]}"
    data = await state.get_data()
    windows = data.get(CtxKeys.routine_windows) or {}
    await state.update_data(**{CtxKeys.routine_evening_start: start_str})
    await state.set_state(Flow.waiting_evening_end)
    if cb.message:
        await cb.message.edit_text(
            render_evening_end_prompt(windows, start_str),
            reply_markup=build_routine_evening_time_kb("end")
        )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^settings:routines:morning:end:[0-9]{2}:[0-9]{2}$"))
async def cb_routine_time_morning_end_btn(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Aamu: käyttäjä valitsi lopetusaikan (nappi) -> validoi start < end, tallenna, päivitä viesti valikoksi."""
    from app.ui import routine_edit_menu_kb, render_routine_edit_menu_header
    parts = cb.data.split(":")
    if len(parts) < 6:
        await cb.answer()
        return
    end_str = f"{parts[4]}:{parts[5]}"
    data = await state.get_data()
    start_str = data.get(CtxKeys.routine_morning_start)
    if not start_str:
        await cb.answer("Virhe: aloitusaika puuttuu. Aloita alusta.", show_alert=True)
        return
    start_t = parse_time_string(start_str)
    end_t = parse_time_string(end_str)
    if not start_t or not end_t:
        await cb.answer("Virheellinen aika.", show_alert=True)
        return
    if start_t >= end_t:
        if cb.message:
            from app.ui import build_routine_morning_time_kb, render_morning_end_prompt
            windows = data.get(CtxKeys.routine_windows) or {}
            await cb.message.edit_text(
                "Lopetusaikan tulee olla aloitusajan jälkeen. Valitse uudestaan.",
                reply_markup=build_routine_morning_time_kb("end")
            )
        await cb.answer("Lopetusaika ei voi olla ennen aloitusta.")
        return
    user_id = cb.from_user.id
    ok = await repo.set_morning_window(user_id, start_str, end_str)
    await state.clear()
    if cb.message:
        windows = await repo.get_routine_windows(user_id)
        await cb.message.edit_text(
            f"Aamurutiinin aika päivitetty: {start_str}–{end_str}\n\n"
            + render_routine_edit_menu_header(),
            reply_markup=routine_edit_menu_kb(windows)
        )
    await cb.answer("Aika tallennettu" if ok else "Virhe tallennuksessa")


@router.callback_query(F.data.regexp(r"^settings:routines:evening:end:[0-9]{2}:[0-9]{2}$"))
async def cb_routine_time_evening_end_btn(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Ilta: käyttäjä valitsi lopetusaikan (nappi) -> validoi start < end, tallenna, päivitä viesti valikoksi."""
    from app.ui import routine_edit_menu_kb, build_routine_evening_time_kb, render_routine_edit_menu_header
    parts = cb.data.split(":")
    if len(parts) < 6:
        await cb.answer()
        return
    end_str = f"{parts[4]}:{parts[5]}"
    data = await state.get_data()
    start_str = data.get(CtxKeys.routine_evening_start)
    if not start_str:
        await cb.answer("Virhe: aloitusaika puuttuu. Aloita alusta.", show_alert=True)
        return
    start_t = parse_time_string(start_str)
    end_t = parse_time_string(end_str)
    if not start_t or not end_t:
        await cb.answer("Virheellinen aika.", show_alert=True)
        return
    if start_t >= end_t:
        if cb.message:
            await cb.message.edit_text(
                "Lopetusaikan tulee olla aloitusajan jälkeen. Valitse uudestaan.",
                reply_markup=build_routine_evening_time_kb("end")
            )
        await cb.answer("Lopetusaika ei voi olla ennen aloitusta.")
        return
    user_id = cb.from_user.id
    ok = await repo.set_evening_window(user_id, start_str, end_str)
    await state.clear()
    if cb.message:
        windows = await repo.get_routine_windows(user_id)
        await cb.message.edit_text(
            f"Iltarutiinin aika päivitetty: {start_str}–{end_str}\n\n"
            + render_routine_edit_menu_header(),
            reply_markup=routine_edit_menu_kb(windows)
        )
    await cb.answer("Aika tallennettu" if ok else "Virhe tallennuksessa")


@router.callback_query(F.data == SETTINGS_ROUTINES_PERUUTA)
async def cb_routine_routines_peruuta(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Peruuta: palaa rutiinivalikkoon ilman muutoksia. Päivitetään sama viesti."""
    from app.ui import routine_edit_menu_kb, render_routine_edit_menu_header
    await state.clear()
    windows = await repo.get_routine_windows(cb.from_user.id)
    if cb.message:
        await cb.message.edit_text(
            render_routine_edit_menu_header(),
            reply_markup=routine_edit_menu_kb(windows)
        )
    await cb.answer()


@router.callback_query(F.data == SETTINGS_ROUTINES_MORNING_BACK)
async def cb_routine_morning_back_to_start(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Takaisin: yksi askel taakse (end -> start). Step 1: Palaa = valikkoon."""
    from app.ui import routine_edit_menu_kb, build_routine_morning_time_kb, render_morning_start_prompt, render_routine_edit_menu_header
    current = await state.get_state()
    if current == str(Flow.waiting_morning_end):
        await state.set_state(Flow.waiting_morning_start)
        data = await state.get_data()
        windows = data.get(CtxKeys.routine_windows) or {}
        if cb.message:
            await cb.message.edit_text(
                render_morning_start_prompt(windows),
                reply_markup=build_routine_morning_time_kb("start")
            )
        await cb.answer()
    else:
        await state.clear()
        windows = await repo.get_routine_windows(cb.from_user.id)
        if cb.message:
            await cb.message.edit_text(
                render_routine_edit_menu_header(),
                reply_markup=routine_edit_menu_kb(windows)
            )
        await cb.answer()


@router.callback_query(F.data == SETTINGS_ROUTINES_EVENING_BACK)
async def cb_routine_evening_back_to_start(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Takaisin iltaflowssa: yksi askel taakse (end -> start). Step 1: Palaa = valikkoon."""
    from app.ui import routine_edit_menu_kb, build_routine_evening_time_kb, render_evening_start_prompt, render_routine_edit_menu_header
    current = await state.get_state()
    if current == str(Flow.waiting_evening_end):
        await state.set_state(Flow.waiting_evening_start)
        data = await state.get_data()
        windows = data.get(CtxKeys.routine_windows) or {}
        if cb.message:
            await cb.message.edit_text(
                render_evening_start_prompt(windows),
                reply_markup=build_routine_evening_time_kb("start")
            )
        await cb.answer()
    else:
        await state.clear()
        windows = await repo.get_routine_windows(cb.from_user.id)
        if cb.message:
            await cb.message.edit_text(
                render_routine_edit_menu_header(),
                reply_markup=routine_edit_menu_kb(windows)
            )
        await cb.answer()


@router.message(Flow.waiting_morning_start, F.text)
async def msg_morning_start(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Aamu: käyttäjä kirjoitti alkuaikan (HH:MM) -> validoi, tallenna FSM:ään, näytä lopetusaika. Navigointi napeilla."""
    from app.ui import build_routine_morning_time_kb, render_morning_end_prompt, render_morning_start_prompt
    data = await state.get_data()
    windows = data.get(CtxKeys.routine_windows) or {}
    text = (message.text or "").strip()
    start_str = parse_hhmm_strict(text)
    if not start_str:
        await message.answer(
            "Virheellinen aika. Käytä muotoa HH:MM (esim. 06:30) tai valitse nappulasta.",
            reply_markup=build_routine_morning_time_kb("start")
        )
        return
    await state.update_data(**{CtxKeys.routine_morning_start: start_str})
    await state.set_state(Flow.waiting_morning_end)
    await message.answer(
        render_morning_end_prompt(windows, start_str),
        reply_markup=build_routine_morning_time_kb("end")
    )


@router.message(Flow.waiting_morning_end, F.text)
async def msg_morning_end(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Aamu: käyttäjä kirjoitti lopetusaikan -> validoi HH:MM ja start < end, tallenna, palaa valikkoon."""
    from app.ui import routine_edit_menu_kb, build_routine_morning_time_kb, render_routine_edit_menu_header
    data = await state.get_data()
    windows = data.get(CtxKeys.routine_windows) or {}
    text = (message.text or "").strip()
    end_str = parse_hhmm_strict(text)
    if not end_str:
        await message.answer(
            "Virheellinen aika. Käytä muotoa HH:MM (esim. 07:30) tai valitse nappulasta.",
            reply_markup=build_routine_morning_time_kb("end")
        )
        return
    start_str = data.get(CtxKeys.routine_morning_start)
    if not start_str:
        await message.answer("Virhe: aloitusaika puuttuu. Aloita alusta.", reply_markup=build_routine_morning_time_kb("end"))
        return
    start_t = parse_time_string(start_str)
    end_t = parse_time_string(end_str)
    if not start_t or not end_t:
        await message.answer("Virheellinen aika.", reply_markup=build_routine_morning_time_kb("end"))
        return
    if start_t >= end_t:
        await message.answer(
            "Lopetusaikan tulee olla aloitusajan jälkeen. Valitse nappulasta tai syötä uudestaan.",
            reply_markup=build_routine_morning_time_kb("end")
        )
        return
    user_id = message.from_user.id if message.from_user else 0
    ok = await repo.set_morning_window(user_id, start_str, end_str)
    await state.clear()
    windows = await repo.get_routine_windows(user_id)
    await message.answer(
        f"Aamurutiinin aika päivitetty: {start_str}–{end_str}\n\n" + render_routine_edit_menu_header(),
        reply_markup=routine_edit_menu_kb(windows)
    )


@router.message(Flow.waiting_evening_start, F.text)
async def msg_evening_start(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Ilta: käyttäjä kirjoitti alkuaikan (HH:MM) -> validoi, tallenna FSM:ään, näytä lopetusaika. Navigointi napeilla."""
    from app.ui import build_routine_evening_time_kb, render_evening_end_prompt
    data = await state.get_data()
    windows = data.get(CtxKeys.routine_windows) or {}
    text = (message.text or "").strip()
    start_str = parse_hhmm_strict(text)
    if not start_str:
        await message.answer(
            "Virheellinen aika. Käytä muotoa HH:MM (esim. 20:30) tai valitse nappulasta.",
            reply_markup=build_routine_evening_time_kb("start")
        )
        return
    await state.update_data(**{CtxKeys.routine_evening_start: start_str})
    await state.set_state(Flow.waiting_evening_end)
    await message.answer(
        render_evening_end_prompt(windows, start_str),
        reply_markup=build_routine_evening_time_kb("end")
    )


@router.message(Flow.waiting_evening_end, F.text)
async def msg_evening_end(message: Message, state: FSMContext, repo: TasksRepo) -> None:
    """Ilta: käyttäjä kirjoitti lopetusaikan -> validoi HH:MM ja start < end, tallenna, palaa valikkoon."""
    from app.ui import routine_edit_menu_kb, build_routine_evening_time_kb, render_routine_edit_menu_header
    data = await state.get_data()
    text = (message.text or "").strip()
    end_str = parse_hhmm_strict(text)
    if not end_str:
        await message.answer(
            "Virheellinen aika. Käytä muotoa HH:MM (esim. 22:00) tai valitse nappulasta.",
            reply_markup=build_routine_evening_time_kb("end")
        )
        return
    start_str = data.get(CtxKeys.routine_evening_start)
    if not start_str:
        await message.answer("Virhe: aloitusaika puuttuu. Aloita alusta.", reply_markup=build_routine_evening_time_kb("end"))
        return
    start_t = parse_time_string(start_str)
    end_t = parse_time_string(end_str)
    if not start_t or not end_t:
        await message.answer("Virheellinen aika.", reply_markup=build_routine_evening_time_kb("end"))
        return
    if start_t >= end_t:
        await message.answer(
            "Lopetusaikan tulee olla aloitusajan jälkeen. Valitse nappulasta tai syötä uudestaan.",
            reply_markup=build_routine_evening_time_kb("end")
        )
        return
    user_id = message.from_user.id if message.from_user else 0
    ok = await repo.set_evening_window(user_id, start_str, end_str)
    await state.clear()
    windows = await repo.get_routine_windows(user_id)
    await message.answer(
        f"Iltarutiinin aika päivitetty: {start_str}–{end_str}\n\n" + render_routine_edit_menu_header(),
        reply_markup=routine_edit_menu_kb(windows)
    )


@router.callback_query(F.data.regexp(r"^routine:time:(morning|evening):end:[0-9]{2}:[0-9]{2}:[0-9]{2}:[0-9]{2}$"))
async def cb_routine_time_end(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Illan loppuaika (vanha flow). callback_data = routine:time:evening:end:20:00:22:00"""
    from app.ui import routine_edit_menu_kb, render_routine_edit_menu_header
    parts = cb.data.split(":")
    if len(parts) < 8:
        await cb.answer()
        return
    period = parts[2]
    start_str = f"{parts[4]}:{parts[5]}"
    end_str = f"{parts[6]}:{parts[7]}"
    user_id = cb.from_user.id
    if period == "morning":
        ok = await repo.set_morning_window(user_id, start_str, end_str)
    else:
        ok = await repo.set_evening_window(user_id, start_str, end_str)
    if cb.message:
        windows = await repo.get_routine_windows(user_id)
        await cb.message.edit_text(
            render_routine_edit_menu_header(),
            reply_markup=routine_edit_menu_kb(windows)
        )
    await cb.answer("Aika tallennettu" if ok else "Virhe tallennuksessa")


@router.callback_query(F.data.startswith(PREFIX_ROUTINE_EDIT_LIST))
async def cb_routine_edit_list(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open routine list for edit (morning/evening)"""
    from app.ui import routine_list_edit_kb, render_routine_list_edit_header
    await state.clear()
    routine_type = "evening" if "evening" in cb.data else "morning"
    await repo.ensure_default_routine_tasks(cb.from_user.id, routine_type)
    tasks = await repo.list_routine_tasks(cb.from_user.id, routine_type)
    if cb.message:
        await cb.message.edit_text(
            render_routine_list_edit_header(routine_type),
            reply_markup=routine_list_edit_kb(routine_type, tasks)
        )
    await cb.answer()


@router.callback_query(F.data.startswith(PREFIX_ROUTINE_EDIT_TASK))
async def cb_routine_edit_task(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start FSM to edit routine task text. callback_data = routine:edit_task:morning:123"""
    from app.handlers.routines import start_edit_routine_task
    parts = cb.data.split(":")
    if len(parts) < 4:
        await cb.answer()
        return
    routine_type, task_id_str = parts[2], parts[3]
    await start_edit_routine_task(cb, state, repo, routine_type, int(task_id_str))


@router.callback_query(F.data.startswith(PREFIX_ROUTINE_DEL))
async def cb_routine_del(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Delete routine task. callback_data = routine:del:morning:123"""
    from app.ui import routine_list_edit_kb, render_routine_list_edit_header
    await state.clear()
    parts = cb.data.split(":")
    if len(parts) < 4:
        await cb.answer()
        return
    routine_type, task_id_str = parts[2], parts[3]
    task_id = int(task_id_str)
    await repo.delete_routine_task(cb.from_user.id, task_id)
    tasks = await repo.list_routine_tasks(cb.from_user.id, routine_type)
    if cb.message:
        await cb.message.edit_text(
            render_routine_list_edit_header(routine_type),
            reply_markup=routine_list_edit_kb(routine_type, tasks)
        )
    await cb.answer("Poistettu")


@router.callback_query(F.data.startswith(PREFIX_ROUTINE_ADD))
async def cb_routine_add(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Start FSM to add new routine task. callback_data = routine:add:morning"""
    from app.handlers.routines import start_add_routine_task
    parts = cb.data.split(":")
    routine_type = parts[2] if len(parts) > 2 else "morning"
    await start_add_routine_task(cb, state, repo, routine_type)


@router.callback_query(F.data.startswith(PREFIX_ROUTINE_TOGGLE))
async def cb_routine_toggle(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Toggle routine task done/not done for today. callback_data = routine:toggle:morning:123"""
    from app.ui import build_main_keyboard_6_3, render_home_text, render_routine_active_header, routine_active_kb
    parts = cb.data.split(":")
    if len(parts) < 4:
        await cb.answer()
        return
    routine_type, task_id_str = parts[2], parts[3]
    task_id = int(task_id_str)
    user_id = cb.from_user.id
    today = await repo.get_today_date_user_tz(user_id)
    completed = await repo.get_routine_completions_for_date(user_id, today)
    new_done = task_id not in completed
    await repo.set_routine_completion(user_id, task_id, today, new_done)
    completed = await repo.get_routine_completions_for_date(user_id, today)
    tasks = await repo.list_routine_tasks(user_id, routine_type)
    all_done = len(tasks) > 0 and len(completed) >= len(tasks)
    if cb.message:
        await cb.message.edit_text(
            render_routine_active_header(routine_type, all_done),
            reply_markup=routine_active_kb(routine_type, tasks, completed, all_done)
        )
    await cb.answer("Tehty" if new_done else "Tekemättömäksi")


@router.callback_query(F.data.startswith(PREFIX_ROUTINE_QUITTED))
async def cb_routine_quitted(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Kuittaa aamurutiinit/iltarutiinit tehdyksi -> normaali näkymä palautuu. callback_data = routine:quitted:morning | routine:quitted:evening"""
    parts = cb.data.split(":")
    if len(parts) < 3:
        await cb.answer()
        return
    routine_type = parts[2]  # morning | evening
    user_id = cb.from_user.id
    today = await repo.get_today_date_user_tz(user_id)
    await repo.set_routine_quitted(user_id, routine_type, today)
    await state.clear()
    await return_to_main_menu(cb, repo, state=state, answer_text="Rutiinit kuitattu tehdyksi")


@router.callback_query(F.data == SETTINGS_EXPORT_DB)
async def cb_settings_export_db(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Export DB (placeholder)"""
    from app.ui import render_export_db_placeholder, settings_kb
    
    await state.clear()
    
    if cb.message:
        settings = await repo.get_user_settings(user_id=cb.from_user.id)
        await cb.message.edit_text(
            render_export_db_placeholder(),
            reply_markup=settings_kb(
                morning_routines_enabled=settings.get("morning_routines_enabled", False),
                evening_routines_enabled=settings.get("evening_routines_enabled", False),
            )
        )
    await cb.answer("Tulossa myöhemmin")


@router.callback_query(F.data == SETTINGS_RESET)
async def cb_reset(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    await state.clear()
    await repo.reset_all_data(user_id=cb.from_user.id)
    if cb.message:
        await cb.message.edit_text(
            "✅ Kaikki tiedot nollattu.",
            reply_markup=settings_kb(morning_routines_enabled=False, evening_routines_enabled=False),
        )
    await cb.answer("Tiedot nollattu")


@router.callback_query(F.data == VIEW_PROJECTS)
async def cb_projects_list(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open projects list (päänäkymä > projektit)"""
    await state.clear()
    projects = await repo.list_all_projects()
    if cb.message:
        await cb.message.edit_text(
            render_projects_list_header(),
            reply_markup=projects_list_kb(projects),
        )
    await cb.answer()


@router.callback_query(F.data.startswith(PREFIX_VIEW_PROJECT))
async def cb_project_detail(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open project detail: all steps, click toggles done/not done"""
    await state.clear()
    parts = parse_callback(cb.data, 3)
    project_id = parse_int_safe(parts[2]) if parts and len(parts) >= 3 else None
    if project_id is None:
        await cb.answer("Virheellinen projektin-id.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    project = await repo.get_project(project_id)
    if not project:
        await cb.answer("Projektia ei löytynyt.", show_alert=True)
        await return_to_main_menu(cb, repo, state=state)
        return
    steps = await repo.get_project_steps(project_id)
    if cb.message:
        await cb.message.edit_text(
            render_project_detail(project, steps),
            reply_markup=project_detail_view_kb(project, steps),
        )
    await cb.answer()


@router.callback_query(F.data.startswith(PREFIX_PROJ_STEP_TOGGLE))
async def cb_proj_step_toggle(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Toggle project step done/not done and refresh project detail view"""
    parts = parse_callback(cb.data, 4)
    step_id = parse_int_safe(parts[3]) if parts and len(parts) >= 4 else None
    if step_id is None:
        await cb.answer("Virheellinen askel-id.", show_alert=True)
        return
    try:
        now = repo._now_iso()
        result = await repo.toggle_project_step(step_id=step_id, now=now)
    except ValueError:
        await cb.answer("Askelia ei löytynyt.", show_alert=True)
        return
    project_id = result.get("project_id")
    if not project_id or not cb.message:
        await cb.answer()
        return
    project = await repo.get_project(project_id)
    if not project:
        await cb.answer("Projektia ei löytynyt.", show_alert=True)
        return
    steps = await repo.get_project_steps(project_id)
    await cb.message.edit_text(
        render_project_detail(project, steps),
        reply_markup=project_detail_view_kb(project, steps),
    )
    action = result.get("action", "completed")
    if action == "completed_project":
        await cb.answer("Projekti valmis!", show_alert=False)
    else:
        await cb.answer()


@router.callback_query(F.data.in_(NAV_EDIT))
async def cb_edit_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open edit tasks view (from home or plus menu)"""
    await state.clear()
    tasks = await repo.list_tasks(user_id=cb.from_user.id)
    if cb.message:
        await cb.message.edit_text(render_edit_header(), reply_markup=edit_kb(tasks))
    await cb.answer()


@router.callback_query(F.data == VIEW_DONE)
async def cb_done_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show done tasks view"""
    await state.clear()
    tasks = await repo.list_done_tasks(user_id=cb.from_user.id, limit=50, offset=0)
    if cb.message:
        header = f"✅ Tehdyt tehtävät\n\nYhteensä: {len(tasks)} tehtävää\n\nKlikkaa tehtävää palauttaaksesi sen aktiiviseksi."
        await cb.message.edit_text(header, reply_markup=done_tasks_kb(tasks, offset=0))
    await cb.answer()


@router.callback_query(F.data.startswith(PREFIX_DONE_PAGE))
async def cb_done_page(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show next page of done tasks"""
    await state.clear()
    parts = parse_callback(cb.data, 3)
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


@router.callback_query(F.data.startswith(PREFIX_DONE_RESTORE))
async def cb_done_restore(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Restore a completed task to active list"""
    from app.handlers.common import return_to_main_menu

    parts = parse_callback(cb.data, 3)
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


@router.callback_query(F.data == VIEW_DELETED)
async def cb_deleted_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show deleted tasks view"""
    await state.clear()
    tasks = await repo.list_deleted_tasks(user_id=cb.from_user.id, limit=50, offset=0)
    if cb.message:
        header = f"🗑 Poistetut tehtävät\n\nYhteensä: {len(tasks)} tehtävää\n\nKlikkaa 'Palauta' palauttaaksesi tehtävän."
        await cb.message.edit_text(header, reply_markup=deleted_tasks_kb(tasks, offset=0))
    await cb.answer()


@router.callback_query(F.data.startswith(PREFIX_DELETED_PAGE))
async def cb_deleted_page(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show next page of deleted tasks"""
    await state.clear()
    parts = parse_callback(cb.data, 3)
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


@router.callback_query(F.data.startswith(PREFIX_DELETED_RESTORE))
async def cb_restore_deleted(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Restore a deleted task"""
    parts = parse_callback(cb.data, 3)
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


@router.callback_query(F.data == VIEW_STATS)
async def cb_stats_view(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Open stats main menu"""
    from app.ui import stats_menu_kb, render_stats_menu_header
    
    await state.clear()
    if cb.message:
        await cb.message.edit_text(render_stats_menu_header(), reply_markup=stats_menu_kb())
    await cb.answer()


@router.callback_query(F.data == STATS_ALL_TIME)
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


@router.callback_query(F.data == STATS_AI)
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


def _stats_ai_period_to_days(period_str: str) -> int:
    """Map callback period string to days for get_statistics."""
    if period_str == "custom":
        return 30
    return max(1, parse_int_safe(period_str, default=7))


@router.callback_query(F.data.startswith(PREFIX_STATS_AI))
async def cb_stats_ai_period(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Handle AI analysis period selection: build stats_payload, run AI, show result or fallback."""
    import os

    await state.clear()

    parts = cb.data.split(":", 2)
    period_str = parts[2] if len(parts) > 2 else "7"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        if cb.message:
            await cb.message.edit_text(
                render_ai_analysis_disabled(),
                reply_markup=stats_menu_kb()
            )
        await cb.answer()
        return

    period_map = {
        "1": "1 päivä",
        "7": "1 viikko",
        "30": "1 kuukausi",
        "365": "1 vuosi",
        "custom": "Muu ajanjakso",
    }
    period_text = period_map.get(period_str, f"{period_str} päivää")
    days = _stats_ai_period_to_days(period_str)
    user_id = cb.from_user.id

    # Build stats_payload: period, completed, deleted, active, done_today, done_this_week (when available)
    stats_payload = await repo.get_statistics(user_id=user_id, days=days)
    stats_payload["period"] = period_text
    stats_1 = await repo.get_statistics(user_id=user_id, days=1)
    stats_payload["done_today"] = stats_1.get("completed", 0)
    stats_7 = await repo.get_statistics(user_id=user_id, days=7)
    stats_payload["done_this_week"] = stats_7.get("completed", 0)

    analysis_text = await asyncio.to_thread(
        run_ai_analysis, stats_payload, period_text
    )

    if cb.message:
        if analysis_text == AI_ANALYSIS_FALLBACK:
            await cb.message.edit_text(
                render_ai_analysis_error(),
                reply_markup=stats_menu_kb()
            )
        else:
            await cb.message.edit_text(
                render_ai_analysis_result(period_text, analysis_text),
                reply_markup=stats_menu_kb()
            )
    await cb.answer()


@router.callback_query(F.data == STATS_RESET)
async def cb_stats_reset(cb: CallbackQuery, state: FSMContext, repo: TasksRepo) -> None:
    """Show reset stats confirmation"""
    await state.clear()
    
    if cb.message:
        await cb.message.edit_text(
            render_reset_stats_confirm(),
            reply_markup=stats_reset_confirm_kb()
        )
    await cb.answer()


@router.callback_query(F.data == STATS_RESET_CONFIRM)
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
    if cb.data in STATS_MENU_ACTIONS:
        return
    if cb.data.startswith(PREFIX_STATS_AI):
        return
    
    await state.clear()
    parts = cb.data.split(":", 1)
    days_str = parts[1] if len(parts) > 1 else "7"
    days = parse_int_safe(days_str, default=7)
    
    stats = await repo.get_statistics(user_id=cb.from_user.id, days=days)
    if cb.message:
        await cb.message.edit_text(render_stats_header(stats), reply_markup=stats_kb())
    await cb.answer()
