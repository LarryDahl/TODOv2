from __future__ import annotations

from datetime import datetime
from typing import Optional, Awaitable, Callable, TypeVar

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from app.domain.oppari.service import OppariService


router = Router()

CB_STEP_DONE = "opp_step_done"
CB_STEP_DEL = "opp_step_del"
CB_STEP_EDIT = "opp_step_edit"
CB_STEP_EDIT_CANCEL = "opp_step_edit_cancel"
CB_STEP_LIST = "opp_step_list"


class OppStepEdit(StatesGroup):
    waiting_text = State()


def _now() -> datetime:
    return datetime.now()


def _parse_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except Exception:
        return None


def _btn_label(step_id: int, text: str | None) -> str:
    base = " ".join((text or "").split()).strip()
    if not base:
        base = f"Tehtävä {step_id}"
    max_len = 22
    if len(base) > max_len:
        base = base[: max_len - 1] + "…"
    return base


def build_steps_keyboard(steps: list[tuple[int, str, bool]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    active = [(sid, txt) for (sid, txt, done) in steps if not done]

    for step_id, text in active:
        kb.row(
            InlineKeyboardButton(
                text=f"✅ {_btn_label(step_id, text)}",
                callback_data=f"{CB_STEP_DONE}:{step_id}",
            )
        )
        kb.row(
            InlineKeyboardButton(text="✏️", callback_data=f"{CB_STEP_EDIT}:{step_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"{CB_STEP_DEL}:{step_id}"),
        )
    return kb.as_markup()


def build_open_steps_button() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📋 Näytä tehtävälista", callback_data=CB_STEP_LIST))
    return kb.as_markup()


async def _agent(db) -> OppariAgent:
    agent = OppariAgent(db)
    await agent.ensure_schema()
    return agent


def _is_owner(obj, config) -> bool:
    # obj can be Message or CallbackQuery
    u = getattr(obj, "from_user", None)
    return bool(u and u.id == config.owner_telegram_id)


async def _render_steps_for_chat(chat_id: int, agent: OppariAgent) -> tuple[bool, InlineKeyboardMarkup | None]:
    steps = await agent.list_steps(chat_id)
    active = [(i, t, d) for (i, t, d) in steps if not d]
    if not active:
        return False, build_open_steps_button()
    return True, build_steps_keyboard(active)


async def _edit_or_answer_steps_view(
    *,
    query: CallbackQuery | None,
    message: Message | None,
    agent: OppariAgent,
    chat_id: int,
    title: str,
) -> None:
    has_active, kb = await _render_steps_for_chat(chat_id, agent)
    text = title if has_active else f"{title}\n\nEi aktiivisia tehtäviä."

    if query is not None:
        await query.message.edit_text(text, reply_markup=kb)
        await query.answer()
    elif message is not None:
        await message.answer(text, reply_markup=kb)


# -------------------------
# /opp command entry
# -------------------------

@router.message(Command("opp"))
async def opp_entry(message: Message, db, config) -> None:
    if not _is_owner(message, config):
        return
    await handle_opp(message, db)


async def handle_opp(message: Message, db) -> None:
    agent = await _agent(db)

    chat_id = message.chat.id
    text = (message.text or "").strip()
    tokens = text.split(maxsplit=2)
    if not tokens:
        return

    if len(tokens) == 1:
        await message.answer(
            "Oppari-komennot:\n"
            "/opp start [aihe]\n"
            "/opp stop\n"
            "/opp status\n"
            "/opp goal set <min> | /opp goal\n"
            "/opp step add <teksti> | /opp step list | /opp step done <id>\n"
            "/opp weekly\n"
            "/opp streak\n"
            "/opp why <1-5> [tarkennus]\n"
            "/opp check   (simuloi 18/19 -tarkistusta)"
        )
        return

    sub = tokens[1].lower()
    arg = tokens[2] if len(tokens) >= 3 else ""
    now = _now()

    if sub == "start":
        topic = arg.strip() or None
        await message.answer(await agent.start_session(chat_id, now, topic=topic))
        return

    if sub == "stop":
        await message.answer(await agent.stop_session(chat_id, now))
        return

    if sub == "status":
        st = await agent.get_status(chat_id, now)
        steps_txt = "ei asetettu"
        if st.next_steps:
            lines = []
            for _id, t, done in st.next_steps:
                mark = "✅" if done else "⬜"
                lines.append(f"{mark} {t} (id={_id})")
            steps_txt = "\n".join(lines)

        goal_txt = f"{st.goal_minutes} min" if st.goal_minutes else "ei asetettu"
        started_txt = st.today_start_ts if st.today_started else "ei aloitusta"
        open_txt = st.open_session_started_ts if st.open_session else "ei käynnissä"

        await message.answer(
            "Oppari status:\n"
            f"- Tänään aloitettu: {started_txt}\n"
            f"- Tänään minuutteja: {st.today_minutes}\n"
            f"- Käynnissä oleva sessio: {open_txt}\n"
            f"- Päivätavoite: {goal_txt}\n"
            f"- Streak (≥15 min): {st.streak_days_15min}\n"
            f"- Seuraavat askeleet:\n{steps_txt}"
        )
        return

    if sub == "goal":
        if arg.strip() == "":
            g = await agent.get_goal(chat_id)
            await message.answer("Päivätavoite: " + (f"{g} min" if g else "ei asetettu"))
            return

        p = arg.split()
        if len(p) >= 2 and p[0].lower() == "set":
            m = _parse_int(p[1])
            if not m:
                await message.answer("Anna minuutit numerona. Esim: /opp goal set 60")
                return
            await message.answer(await agent.set_goal(chat_id, now, m))
            return

        await message.answer("Käyttö: /opp goal tai /opp goal set <min>")
        return

    if sub == "step":
        if not arg.strip():
            await message.answer("Käyttö: /opp step add <teksti> | list | done <id>")
            return

        p = arg.split(maxsplit=1)
        action = p[0].lower()
        rest = p[1] if len(p) > 1 else ""

        if action == "add":
            await message.answer(await agent.add_step(chat_id, now, rest))
            return

        if action == "list":
            await _edit_or_answer_steps_view(
                query=None, message=message, agent=agent, chat_id=chat_id, title="Valitse tehtävä:"
            )
            return

        if action == "done":
            sid = _parse_int(rest.strip())
            if not sid:
                await message.answer("Anna id numerona. Esim: /opp step done 12")
                return
            await message.answer(await agent.done_step(chat_id, now, sid))
            return

        await message.answer("Käyttö: /opp step add <teksti> | list | done <id>")
        return

    if sub == "weekly":
        await message.answer(await agent.weekly_summary(chat_id, now.date()))
        return

    if sub == "streak":
        s = await agent.streak_15min(chat_id, now.date())
        await message.answer(f"Streak (≥15 min): {s} päivää")
        return

    if sub == "why":
        p = arg.split(maxsplit=1)
        if not p:
            await message.answer("Käyttö: /opp why <1-5> [tarkennus]")
            return

        choice = p[0].strip()
        detail = p[1] if len(p) > 1 else ""

        mapping = {"1": "fatigue", "2": "unclear", "3": "motivation", "4": "anxiety", "5": "other"}
        cat = mapping.get(choice)
        if not cat:
            await message.answer("Valitse 1-5. Esim: /opp why 2 en tiedä mitä seuraavaksi")
            return

        if cat == "other" and not detail.strip():
            await message.answer("Muu — mikä tarkalleen?")
            return

        await message.answer(await agent.record_blocker(chat_id, now, cat, detail))
        return

    if sub == "check":
        msg = await agent.evaluate_reminders(chat_id, now)
        await message.answer(msg if msg else "Ei muistutettavaa tällä hetkellä.")
        return

    await message.answer("Tuntematon /opp-alikomento. Katso: /opp")


# -------------------------
# CALLBACKS
# -------------------------

@router.callback_query(F.data == CB_STEP_LIST)
async def cb_step_list(query: CallbackQuery, db, config):
    if not _is_owner(query, config):
        await query.answer()
        return

    agent = await _agent(db)
    await _edit_or_answer_steps_view(query=query, message=None, agent=agent, chat_id=query.message.chat.id, title="Valitse tehtävä:")


@router.callback_query(F.data.startswith(f"{CB_STEP_DONE}:"))
async def cb_step_done(query: CallbackQuery, db, config):
    if not _is_owner(query, config):
        await query.answer()
        return

    agent = await _agent(db)
    step_id = int(query.data.split(":", 1)[1])
    await agent.done_step(query.message.chat.id, _now(), step_id)

    await _edit_or_answer_steps_view(query=query, message=None, agent=agent, chat_id=query.message.chat.id, title="Valitse tehtävä:")


@router.callback_query(F.data.startswith(f"{CB_STEP_DEL}:"))
async def cb_step_del(query: CallbackQuery, db, config):
    if not _is_owner(query, config):
        await query.answer()
        return

    agent = await _agent(db)
    step_id = int(query.data.split(":", 1)[1])
    await agent.delete_step(query.message.chat.id, _now(), step_id)

    await _edit_or_answer_steps_view(query=query, message=None, agent=agent, chat_id=query.message.chat.id, title="Valitse tehtävä:")


@router.callback_query(F.data.startswith(f"{CB_STEP_EDIT}:"))
async def cb_step_edit(query: CallbackQuery, state: FSMContext, config):
    if not _is_owner(query, config):
        await query.answer()
        return

    step_id = int(query.data.split(":", 1)[1])
    await state.set_state(OppStepEdit.waiting_text)
    await state.update_data(step_id=step_id, chat_id=query.message.chat.id)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Peru", callback_data=CB_STEP_EDIT_CANCEL))

    await query.message.edit_text("Kirjoita uusi tehtävän nimi (lähetä viestinä):", reply_markup=kb.as_markup())
    await query.answer("Muokkaa")


@router.callback_query(F.data == CB_STEP_EDIT_CANCEL)
async def cb_step_edit_cancel(query: CallbackQuery, state: FSMContext, db, config):
    if not _is_owner(query, config):
        await query.answer()
        return

    await state.clear()
    await query.message.edit_text("Peruttu.", reply_markup=build_open_steps_button())
    await query.answer("Peruttu")


@router.message(OppStepEdit.waiting_text)
async def step_edit_text(message: Message, state: FSMContext, db, config):
    if not _is_owner(message, config):
        return

    data = await state.get_data()
    step_id = int(data["step_id"])
    chat_id = int(data["chat_id"])

    new_text = (message.text or "").strip()
    agent = await _agent(db)
    resp = await agent.update_step_text(chat_id, _now(), step_id, new_text)
    await state.clear()

    await message.answer(f"✅ {resp}", reply_markup=build_open_steps_button())