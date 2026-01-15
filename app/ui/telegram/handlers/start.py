from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.infra.clock.system_clock import SystemClock
from app.infra.db.repo.scheduled_jobs_sqlite import ScheduledJobsRepo
from app.ui.telegram.handlers.mainmenu import send_mainmenu

router = Router()


@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext, jobs_repo: ScheduledJobsRepo, clock: SystemClock):
    await state.clear()
    await send_mainmenu(message, jobs_repo=jobs_repo)


@router.message(Command("menu"))
async def menu_cmd(message: Message, state: FSMContext, jobs_repo: ScheduledJobsRepo):
    await state.clear()
    await send_mainmenu(message, jobs_repo=jobs_repo)
