from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher

from app.config import load_settings
from app.db import TasksRepo
from app.handlers import router


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    settings = load_settings()
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)

    repo = TasksRepo(settings.db_path)
    await repo.init()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    dp["repo"] = repo
    dp.include_router(router)

    await dp.start_polling(bot, repo=repo)


if __name__ == "__main__":
    asyncio.run(main())
