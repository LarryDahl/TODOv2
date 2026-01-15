from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.domain.oppari.service import OppariService
from app.domain.oppari.models import StartWorklogRequest, EndWorklogRequest
from app.domain.common.errors import ConflictError, NotFoundError, ValidationError
from app.ui.telegram.states.oppari import OppariFlow
from app.ui.telegram.keyboards.oppari import now_or_manual_kb, yes_no_kb, cancel_kb
from app.ui.telegram import texts

router = Router()


def _parse_user_time(text: str, tz_name: str) -> datetime:
    """
    Accepts:
      - HHMM   (e.g. 0730)
      - HH:MM  (e.g. 07:30)
    Returns datetime for *today* in user's timezone.
    """
    raw = (text or "").strip()
    tz = ZoneInfo(tz_name)

    # HH:MM
    if len(raw) == 5 and raw[2] == ":" and raw[:2].isdigit() and raw[3:].isdigit():
        hh = int(raw[:2]); mm = int(raw[3:])
        now = datetime.now(tz)
        return now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # HHMM
    if len(raw) == 4 and raw.isdigit():
        hh = int(raw[:2]); mm = int(raw[2:])
        now = datetime.now(tz)
        return now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    raise ValueError("Invalid time format")



@router.message(Command("opp_status"))
async def opp_status(message: Message, opp_service: OppariService):
    st = await opp_service.status(message.from_user.id)
    if not st.has_open_entry:
        await message.answer("No active Oppari session.")
        return
    await message.answer(f"Oppari running since: {st.open_entry.start_at.isoformat()}")


@router.message(Command("opp_start"))
async def opp_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(OppariFlow.start_choose_time)
    await message.answer(texts.oppari.START_PROMPT, reply_markup=now_or_manual_kb("opp:start_time"))


@router.callback_query(lambda c: (c.data or "").startswith("opp:start_time:"))
async def opp_start_time_choice(cb: CallbackQuery, state: FSMContext, timezone: str):
    await cb.answer()
    choice = (cb.data or "").split(":")[-1]

    if choice == "now":
        tz = ZoneInfo(timezone)
        await state.update_data(start_at=datetime.now(tz))
        await state.set_state(OppariFlow.start_planned_task)
        await cb.message.answer(texts.oppari.ASK_PLANNED_TASK, reply_markup=cancel_kb())
        return

    if choice == "manual":
        await state.set_state(OppariFlow.start_enter_time)
        await cb.message.answer(texts.oppari.ENTER_TIME_HINT, reply_markup=cancel_kb())
        return


@router.message(OppariFlow.start_enter_time)
async def opp_start_enter_time(message: Message, state: FSMContext, timezone: str):
    if (message.text or "").strip().lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(texts.oppari.CANCELLED)
        return

    try:
        start_at = _parse_user_time(message.text, timezone)
    except Exception:
        await message.answer("Invalid time format.\n" + texts.oppari.ENTER_TIME_HINT)
        return

    await state.update_data(start_at=start_at)
    await state.set_state(OppariFlow.start_planned_task)
    await message.answer(texts.oppari.ASK_PLANNED_TASK, reply_markup=cancel_kb())


@router.message(OppariFlow.start_planned_task)
async def opp_start_planned_task(message: Message, state: FSMContext, opp_service: OppariService):
    txt = (message.text or "").strip()
    if txt.lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(texts.oppari.CANCELLED)
        return

    data = await state.get_data()
    start_at: datetime = data["start_at"]

    req = StartWorklogRequest(
        user_id=message.from_user.id,
        start_at=start_at,
        planned_task=txt if txt != "-" else None,
        project=None,
        category=None,
    )

    try:
        entry = await opp_service.start_worklog(req)
    except ConflictError as e:
        await state.clear()
        await message.answer(str(e))
        return

    await state.clear()
    await message.answer(f"Oppari started: {entry.start_at.isoformat()}")


@router.message(Command("opp_end"))
async def opp_end(message: Message, state: FSMContext, opp_service: OppariService):
    await state.clear()

    # if no active session, keep old behavior: tell user
    st = await opp_service.status(message.from_user.id)
    if not st.has_open_entry:
        await message.answer("No active Oppari session to end. Use /opp_start first.")
        return

    await state.set_state(OppariFlow.end_choose_time)
    await message.answer(texts.oppari.END_PROMPT, reply_markup=now_or_manual_kb("opp:end_time"))


@router.callback_query(lambda c: (c.data or "").startswith("opp:end_time:"))
async def opp_end_time_choice(cb: CallbackQuery, state: FSMContext, timezone: str):
    await cb.answer()
    choice = (cb.data or "").split(":")[-1]

    if choice == "now":
        tz = ZoneInfo(timezone)
        await state.update_data(end_at=datetime.now(tz))
        await state.set_state(OppariFlow.end_description)
        await cb.message.answer(texts.oppari.ASK_DESCRIPTION, reply_markup=cancel_kb())
        return

    if choice == "manual":
        await state.set_state(OppariFlow.end_enter_time)
        await cb.message.answer(texts.oppari.ENTER_TIME_HINT, reply_markup=cancel_kb())
        return



@router.message(OppariFlow.end_enter_time)
async def opp_end_enter_time(message: Message, state: FSMContext, timezone: str):
    if (message.text or "").strip().lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(texts.oppari.CANCELLED)
        return

    try:
        end_at = _parse_user_time(message.text, timezone)
        
    except Exception:
        await message.answer("Invalid time format.\n" + texts.oppari.ENTER_TIME_HINT)
        return

    await state.update_data(end_at=end_at)
    await state.set_state(OppariFlow.end_description)
    await message.answer(texts.oppari.ASK_DESCRIPTION, reply_markup=cancel_kb())


@router.message(OppariFlow.end_description)
async def opp_end_description(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt.lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(texts.oppari.CANCELLED)
        return
    await state.update_data(description=txt)
    await state.set_state(OppariFlow.end_learned)
    await message.answer(texts.oppari.ASK_LEARNED, reply_markup=cancel_kb())


@router.message(OppariFlow.end_learned)
async def opp_end_learned(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt.lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(texts.oppari.CANCELLED)
        return
    await state.update_data(learned=None if txt == "-" else txt)
    await state.set_state(OppariFlow.end_challenges)
    await message.answer(texts.oppari.ASK_CHALLENGES, reply_markup=cancel_kb())


@router.message(OppariFlow.end_challenges)
async def opp_end_challenges(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt.lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(texts.oppari.CANCELLED)
        return
    await state.update_data(challenges=None if txt == "-" else txt)
    await state.set_state(OppariFlow.end_next_steps)
    await message.answer(texts.oppari.ASK_NEXT_STEPS, reply_markup=cancel_kb())


@router.message(OppariFlow.end_next_steps)
async def opp_end_next_steps(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt.lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(texts.oppari.CANCELLED)
        return
    await state.update_data(next_steps=None if txt == "-" else txt)
    await state.set_state(OppariFlow.end_completed_as_planned)
    await message.answer(texts.oppari.ASK_COMPLETED_AS_PLANNED, reply_markup=yes_no_kb("opp:planned"))


@router.callback_query(lambda c: (c.data or "").startswith("opp:planned:"))
async def opp_end_completed_choice(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    choice = (cb.data or "").split(":")[-1]
    completed = True if choice == "yes" else False
    await state.update_data(completed_as_planned=completed)

    if completed:
        await state.set_state(OppariFlow.end_break_minutes)
        await cb.message.answer(texts.oppari.ASK_BREAK_MINUTES, reply_markup=cancel_kb())
    else:
        await state.set_state(OppariFlow.end_not_completed_reason)
        await cb.message.answer(texts.oppari.ASK_NOT_COMPLETED_REASON, reply_markup=cancel_kb())


@router.message(OppariFlow.end_not_completed_reason)
async def opp_end_not_completed_reason(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    if txt.lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(texts.oppari.CANCELLED)
        return
    await state.update_data(not_completed_reason=txt)
    await state.set_state(OppariFlow.end_break_minutes)
    await message.answer(texts.oppari.ASK_BREAK_MINUTES, reply_markup=cancel_kb())

# --- CALLBACKS FOR MAIN MENU BUTTONS (opp:start / opp:end / opp:status) ---

@router.callback_query(lambda c: (c.data or "") == "opp:start")
async def opp_start_cb(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await state.set_state(OppariFlow.start_choose_time)
    await cb.message.answer(texts.oppari.START_PROMPT, reply_markup=now_or_manual_kb("opp:start_time"))


@router.callback_query(lambda c: (c.data or "") == "opp:end")
async def opp_end_cb(cb: CallbackQuery, state: FSMContext, opp_service: OppariService):
    await cb.answer()
    await state.clear()

    st = await opp_service.status(cb.from_user.id)
    if not st.has_open_entry:
        await cb.message.answer("No active Oppari session to end. Use Oppari: Start first.")
        return

    await state.set_state(OppariFlow.end_choose_time)
    await cb.message.answer(texts.oppari.END_PROMPT, reply_markup=now_or_manual_kb("opp:end_time"))


@router.callback_query(lambda c: (c.data or "") == "opp:status")
async def opp_status_cb(cb: CallbackQuery, opp_service: OppariService):
    await cb.answer()
    st = await opp_service.status(cb.from_user.id)
    if not st.has_open_entry:
        await cb.message.answer("No active Oppari session.")
        return
    await cb.message.answer(f"Oppari running since: {st.open_entry.start_at.isoformat()}")


@router.message(OppariFlow.end_break_minutes)
async def opp_end_break_minutes(message: Message, state: FSMContext, opp_service: OppariService):
    txt = (message.text or "").strip()
    if txt.lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(texts.oppari.CANCELLED)
        return

    try:
        break_minutes = int(txt)
    except Exception:
        await message.answer("Please enter a number (minutes).")
        return

    data = await state.get_data()
    req = EndWorklogRequest(
        user_id=message.from_user.id,
        end_at=data["end_at"],
        description=data["description"],
        learned=data.get("learned"),
        challenges=data.get("challenges"),
        next_steps=data.get("next_steps"),
        break_minutes=break_minutes,
        completed_as_planned=data.get("completed_as_planned"),
        not_completed_reason=data.get("not_completed_reason"),
    )

    try:
        entry = await opp_service.end_worklog(req)
    except (NotFoundError, ValidationError) as e:
        await state.clear()
        await message.answer(str(e))
        return

    await state.clear()
    await message.answer(f"Oppari saved.\nStart: {entry.start_at.isoformat()}\nEnd: {entry.end_at.isoformat()}")
