from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from app.config import load_settings
from app.db import TasksRepo
from app.handlers import router


async def main() -> None:
    """
    Main entry point for the Telegram bot.
    
    IMPORTANT: Only run ONE instance of this bot at a time.
    Running multiple instances will cause TelegramConflictError:
    "terminated by other getUpdates request"
    
    If you see this error:
    1. Check that only one process is running (ps aux | grep python)
    2. Make sure you're not running both polling and webhook
    3. Kill any duplicate processes before restarting
    """
    # Get current process ID for logging
    pid = os.getpid()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - [PID:%(process)d] - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Log startup with PID
    logger.info("=" * 60)
    logger.info(f"Bot starting - PID: {pid}")
    logger.info("=" * 60)
    logger.warning("IMPORTANT: Only run ONE instance of this bot at a time!")
    logger.warning("Multiple instances will cause TelegramConflictError")
    
    try:
        settings = load_settings()
        os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)

        repo = TasksRepo(settings.db_path)
        await repo.init()

        bot = Bot(token=settings.bot_token)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        dp["repo"] = repo
        dp.include_router(router)

        @dp.error(ExceptionTypeFilter(TelegramBadRequest))
        async def handle_old_callback_query(event: ErrorEvent) -> None:
            """Ignore TelegramBadRequest for old/invalid callback queries (e.g. after bot restart)."""
            msg = str(event.exception).lower()
            if "query is too old" in msg or "query id is invalid" in msg or "response timeout expired" in msg:
                logger.debug("Ignoring old/invalid callback query: %s", event.exception)
                return
            raise event.exception

        logger.info(f"Starting polling - PID: {pid}")
        logger.info("Bot is ready to receive updates")
        logger.info("=" * 60)
        
        await dp.start_polling(bot, repo=repo)
        
    except KeyboardInterrupt:
        logger.info(f"Bot stopped by user - PID: {pid}")
    except Exception as e:
        logger.error(f"Bot crashed - PID: {pid}", exc_info=True)
        raise
    finally:
        logger.info(f"Bot shutdown complete - PID: {pid}")


if __name__ == "__main__":
    asyncio.run(main())
