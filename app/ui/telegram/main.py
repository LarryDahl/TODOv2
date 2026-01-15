from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# optional dotenv support (safe if you have python-dotenv installed)
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from app.config import load_settings
from app.domain.common.time import to_iso
from app.domain.oppari.service import OppariService
from app.infra.clock.system_clock import SystemClock
from app.infra.db.connection import Database
from app.infra.db.schema_version import apply_migrations
from app.infra.db.repo.oppari_sqlite import OppariSqliteRepo
from app.infra.ids.uuid_gen import UuidGenerator

from app.ui.telegram.handlers.cancel import router as cancel_router
from app.ui.telegram.middlewares.auth import OwnerOnlyMiddleware
from app.ui.telegram.middlewares.di import DIMiddleware
from app.ui.telegram.handlers.admin import router as admin_router
from app.ui.telegram.handlers.oppari import router as oppari_router
from app.ui.telegram.handlers.schedule import router as schedule_router
from app.ui.telegram.handlers.start import router as start_router
from app.ui.telegram.handlers.mainmenu import router as mainmenu_router
from app.ui.telegram.handlers.tasks import router as tasks_router

from app.infra.db.repo.scheduled_jobs_sqlite import ScheduledJobsRepo
from app.infra.scheduler.loop import SchedulerLoop, JobRunner


async def main() -> None:
    if load_dotenv is not None:
        load_dotenv()

    settings = load_settings()

    repo_root = Path(__file__).resolve().parents[3]  # .../app/ui/telegram/main.py -> repo root

    # --- DB path: one place, always absolute, ensure dir exists ---
    db_path = settings.db_path
    if not db_path.is_absolute():
        db_path = repo_root / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    print("DB_PATH:", str(db_path))

    db = Database(str(db_path))
    clock = SystemClock(settings.timezone)
    ids = UuidGenerator()

    # --- migrations ---
    migrations_dir = repo_root / "app" / "infra" / "db" / "migrations"
    print("MIGRATIONS:", str(migrations_dir))

    await apply_migrations(
        db=db,
        migrations_dir=str(migrations_dir),
        now_iso=to_iso(clock.now()),
    )

    # --- bot/dispatcher ---
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # --- services ---
    opp_repo = OppariSqliteRepo(db)
    opp_service = OppariService(repo=opp_repo, clock=clock, ids=ids)
    await opp_service.bootstrap()

    # --- middlewares ---
    jobs_repo = ScheduledJobsRepo(db)

    dp.message.middleware(OwnerOnlyMiddleware(settings.owner_telegram_id))
    dp.callback_query.middleware(OwnerOnlyMiddleware(settings.owner_telegram_id))

    dp.message.middleware(DIMiddleware(opp_service, db, clock, settings.timezone, jobs_repo))
    dp.callback_query.middleware(DIMiddleware(opp_service, db, clock, settings.timezone, jobs_repo))

    # --- routers ---
    dp.include_router(start_router)
    dp.include_router(cancel_router)
    dp.include_router(mainmenu_router)
    dp.include_router(tasks_router)
    dp.include_router(oppari_router)
    dp.include_router(admin_router)
    dp.include_router(schedule_router)

    # --- scheduler (background) ---


    runner = JobRunner()

    async def run_ping(job):
        await bot.send_message(
            chat_id=job.payload.get("chat_id", job.user_id),
            text="🏓 Ping job executed!",
        )

    runner.register("ping", run_ping)

    scheduler = SchedulerLoop(repo=jobs_repo, runner=runner)
    scheduler_task = asyncio.create_task(scheduler.run_forever())

    print("✅ Starting polling...")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.stop()
        scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
