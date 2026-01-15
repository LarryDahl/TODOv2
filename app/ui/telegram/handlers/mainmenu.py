from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.infra.db.repo.scheduled_jobs_sqlite import ScheduledJobsRepo
from app.ui.telegram.keyboards.mainmenu import main_menu_kb
from app.ui.telegram.keyboards.tasks import tasks_list_kb
from app.ui.telegram.states.tasks import TasksFlow

router = Router()


async def send_mainmenu(message: Message, jobs_repo: ScheduledJobsRepo) -> None:
    """
    Show main menu and immediately show pending todos if there are any.
    """
    await message.answer("Valitse toiminto.", reply_markup=main_menu_kb())

    items = await jobs_repo.list_pending_todos(message.from_user.id)
    if items:
        await message.answer("Tekemättömät tehtävät:", reply_markup=tasks_list_kb(items))


@router.message(F.text == "Agentit")
async def mm_agents(message: Message, state: FSMContext, jobs_repo: ScheduledJobsRepo):
    await state.clear()
    await message.answer("Agentit: suunnitteilla.", reply_markup=main_menu_kb())
    await send_mainmenu(message, jobs_repo=jobs_repo)


@router.message(F.text == "Asetukset")
async def mm_settings(message: Message, state: FSMContext, jobs_repo: ScheduledJobsRepo):
    await state.clear()
    await message.answer(
        "Asetukset: suunnitteilla.\n"
        "- aikavyöhyke\n"
        "- muistutukset\n"
        "- raportointi\n"
        "- agenttien on/off",
        reply_markup=main_menu_kb(),
    )
    await send_mainmenu(message, jobs_repo=jobs_repo)


@router.message(F.text == "Tilastot")
async def mm_stats(message: Message, state: FSMContext, jobs_repo: ScheduledJobsRepo):
    await state.clear()
    await message.answer(
        "Tilastot: suunnitteilla.\n"
        "- Oppari tunnit\n"
        "- Todo: tehty/päivä, streak\n"
        "- agenttikohtaiset yhteenvedot",
        reply_markup=main_menu_kb(),
    )
    await send_mainmenu(message, jobs_repo=jobs_repo)


@router.message(F.text == "Lisää tehtävä")
async def mm_add_task(message: Message, state: FSMContext):
    await state.set_state(TasksFlow.add_title)
    await message.answer("Kirjoita tehtävän kuvaus (yksi viesti).", reply_markup=main_menu_kb())
