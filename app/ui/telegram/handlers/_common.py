from __future__ import annotations

from aiogram.types import Message

from app.infra.db.repo.scheduled_jobs_sqlite import ScheduledJobsRepo
from app.ui.telegram.keyboards.mainmenu import main_menu_kb
from app.ui.telegram.keyboards.tasks import tasks_list_kb


async def nav_to_menu(message: Message, jobs_repo: ScheduledJobsRepo) -> None:
    await message.answer("Valitse toiminto.", reply_markup=main_menu_kb())
    items = await jobs_repo.list_pending_todos(message.from_user.id)
    if items:
        await message.answer("Tekemättömät tehtävät:", reply_markup=tasks_list_kb(items))
