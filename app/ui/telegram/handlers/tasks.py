from __future__ import annotations

from datetime import timezone
from uuid import uuid4

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.domain.common.time import to_iso
from app.infra.clock.system_clock import SystemClock
from app.infra.db.connection import Database
from app.infra.db.repo.scheduled_jobs_sqlite import ScheduledJobsRepo
from app.ui.telegram.keyboards.mainmenu import main_menu_kb
from app.ui.telegram.keyboards.tasks import tasks_list_kb
from app.ui.telegram.states.tasks import TasksFlow

router = Router()

SYSTEM_AGENT_ID = "system"
TODO_DUE_FAR_FUTURE_UTC_ISO = "2099-12-31T23:59:59Z"


def _now_utc_iso(clock: SystemClock) -> str:
    return to_iso(clock.now().astimezone(timezone.utc))


def _command_args(message: Message) -> str:
    text = (message.text or "").strip()
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _render_tasks_text(items) -> str:
    # items: ScheduledJobsRepo.list_pending_todos(user_id) palauttaa listan (sisältö riippuu toteutuksesta)
    # Me pidetään teksti yksinkertaisena ja annetaan nappien hoitaa edit/del/done.
    return "Tekemättömät tehtävät:"


async def _ensure_user_and_system_agent(db: Database, user_id: int, now_iso_utc: str) -> None:
    row = await db.fetchone("SELECT user_id FROM users WHERE user_id = ?;", (user_id,))
    if row:
        await db.execute("UPDATE users SET last_seen_at = ? WHERE user_id = ?;", (now_iso_utc, user_id))
    else:
        await db.execute(
            "INSERT INTO users(user_id, created_at, last_seen_at) VALUES (?, ?, ?);",
            (user_id, now_iso_utc, now_iso_utc),
        )

    arow = await db.fetchone("SELECT agent_id FROM agents WHERE agent_id = ?;", (SYSTEM_AGENT_ID,))
    if not arow:
        await db.execute(
            "INSERT INTO agents(agent_id, name, category, is_active, created_at) VALUES (?, ?, ?, 1, ?);",
            (SYSTEM_AGENT_ID, "System", "core", now_iso_utc),
        )


async def _send_or_edit_list_message(
    *,
    target_message: Message,
    jobs_repo: ScheduledJobsRepo,
    user_id: int,
    prefer_edit: bool,
) -> bool:
    """
    prefer_edit=True: yritetään editata target_messagea (callback-UX).
    prefer_edit=False: lähetetään uusi listaviesti (komento / lisäys-UX).

    Palauttaa True jos listalla on itemeitä, False jos tyhjä.
    """
    items = await jobs_repo.list_pending_todos(user_id)
    if not items:
        # Tyhjä: ei inline-listaa, vaan erillinen "tyhjä" + mainmenu
        await target_message.answer("Ei tekemättömiä tehtäviä.", reply_markup=main_menu_kb())
        return False

    text = _render_tasks_text(items)
    markup = tasks_list_kb(items)

    if prefer_edit:
        # Päivitetään sama viesti (siistimpi UX)
        try:
            await target_message.edit_text(text, reply_markup=markup)
        except Exception:
            # Jos edit ei onnistu (vanha viesti, sama content, tms), fallback: uusi viesti
            await target_message.answer(text, reply_markup=markup)
    else:
        await target_message.answer(text, reply_markup=markup)

    return True


async def _create_todo(
    *,
    message: Message,
    db: Database,
    jobs_repo: ScheduledJobsRepo,
    clock: SystemClock,
    title: str,
) -> None:
    now_utc_iso = _now_utc_iso(clock)
    await _ensure_user_and_system_agent(db, message.from_user.id, now_utc_iso)

    await jobs_repo.create_todo(
        agent_id=SYSTEM_AGENT_ID,
        due_at_iso_utc=TODO_DUE_FAR_FUTURE_UTC_ISO,
        job_id=uuid4().hex,
        user_id=message.from_user.id,
        title=title,
        chat_id=message.chat.id,
        now_iso=now_utc_iso,
    )


@router.message(Command(commands=["td", "todo"]))
async def td_list(message: Message, jobs_repo: ScheduledJobsRepo):
    # Komennolla lähetetään uusi listaviesti (ei editata jotain satunnaista viestiä)
    await _send_or_edit_list_message(
        target_message=message,
        jobs_repo=jobs_repo,
        user_id=message.from_user.id,
        prefer_edit=False,
    )


@router.message(Command("td_add"))
async def td_add_cmd(
    message: Message,
    state: FSMContext,
    db: Database,
    jobs_repo: ScheduledJobsRepo,
    clock: SystemClock,
):
    args = _command_args(message)

    # /td_add <teksti> -> lisää suoraan
    if args:
        title = args.strip()
        if not title:
            await message.answer("Tyhjä tehtävä ei kelpaa.", reply_markup=main_menu_kb())
            return

        await _create_todo(message=message, db=db, jobs_repo=jobs_repo, clock=clock, title=title)

        # Siististi: toastia ei ole message-puolella, joten yksi kuittaus + lista
        await message.answer("Tehtävä lisätty.", reply_markup=main_menu_kb())
        await _send_or_edit_list_message(
            target_message=message,
            jobs_repo=jobs_repo,
            user_id=message.from_user.id,
            prefer_edit=False,
        )
        return

    # /td_add -> FSM
    await state.set_state(TasksFlow.add_title)
    await message.answer("Kirjoita tehtävän kuvaus (yksi viesti).", reply_markup=main_menu_kb())


@router.message(TasksFlow.add_title)
async def td_add_title(
    message: Message,
    state: FSMContext,
    db: Database,
    jobs_repo: ScheduledJobsRepo,
    clock: SystemClock,
):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Tyhjä tehtävä ei kelpaa. Kirjoita kuvaus.")
        return

    await _create_todo(message=message, db=db, jobs_repo=jobs_repo, clock=clock, title=title)

    await state.clear()
    await message.answer("Tehtävä lisätty.", reply_markup=main_menu_kb())
    await _send_or_edit_list_message(
        target_message=message,
        jobs_repo=jobs_repo,
        user_id=message.from_user.id,
        prefer_edit=False,
    )


@router.callback_query(F.data.startswith("td:done:"))
async def td_done(
    cb: CallbackQuery,
    db: Database,
    jobs_repo: ScheduledJobsRepo,
    clock: SystemClock,
):
    job_id = cb.data.split(":")[-1]
    now_utc_iso = _now_utc_iso(clock)

    await _ensure_user_and_system_agent(db, cb.from_user.id, now_utc_iso)
    await jobs_repo.mark_todo_done(job_id, cb.from_user.id, now_utc_iso)

    # Siisti UX: toast + editataan sama listaviesti
    await cb.answer("Merkitty tehdyksi ✅")
    await _send_or_edit_list_message(
        target_message=cb.message,
        jobs_repo=jobs_repo,
        user_id=cb.from_user.id,
        prefer_edit=True,
    )


@router.callback_query(F.data.startswith("td:del:"))
async def td_delete(
    cb: CallbackQuery,
    db: Database,
    jobs_repo: ScheduledJobsRepo,
    clock: SystemClock,
):
    job_id = cb.data.split(":")[-1]
    now_utc_iso = _now_utc_iso(clock)

    await _ensure_user_and_system_agent(db, cb.from_user.id, now_utc_iso)
    await jobs_repo.delete_todo(job_id, cb.from_user.id, now_utc_iso)

    await cb.answer("Poistettu 🗑️")
    await _send_or_edit_list_message(
        target_message=cb.message,
        jobs_repo=jobs_repo,
        user_id=cb.from_user.id,
        prefer_edit=True,
    )


@router.callback_query(F.data.startswith("td:edit:"))
async def td_edit(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    job_id = cb.data.split(":")[-1]
    await state.update_data(edit_job_id=job_id)
    await state.set_state(TasksFlow.edit_title)
    await cb.message.answer("Kirjoita uusi kuvaus (yksi viesti).", reply_markup=main_menu_kb())


@router.message(TasksFlow.edit_title)
async def td_edit_title(
    message: Message,
    state: FSMContext,
    db: Database,
    jobs_repo: ScheduledJobsRepo,
    clock: SystemClock,
):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Tyhjä kuvaus ei kelpaa. Kirjoita uusi kuvaus.")
        return

    data = await state.get_data()
    job_id = data.get("edit_job_id")
    if not job_id:
        await state.clear()
        await message.answer("Muokkaus keskeytyi.", reply_markup=main_menu_kb())
        return

    now_utc_iso = _now_utc_iso(clock)
    await _ensure_user_and_system_agent(db, message.from_user.id, now_utc_iso)

    await jobs_repo.update_todo_title(job_id, message.from_user.id, title, now_utc_iso)
    await state.clear()

    await message.answer("Päivitetty.", reply_markup=main_menu_kb())
    await _send_or_edit_list_message(
        target_message=message,
        jobs_repo=jobs_repo,
        user_id=message.from_user.id,
        prefer_edit=False,
    )
