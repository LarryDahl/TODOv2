from __future__ import annotations

from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.domain.oppari.service import OppariService
from app.infra.clock.system_clock import SystemClock
from app.infra.db.connection import Database
from app.infra.db.repo.scheduled_jobs_sqlite import ScheduledJobsRepo


class DIMiddleware(BaseMiddleware):
    """
    Inject dependencies to handlers via `data` dict.

    Handlers can request args by name, e.g.
      async def handler(message: Message, opp_service: OppariService, jobs_repo: ScheduledJobsRepo, clock: SystemClock): ...
    """

    def __init__(
        self,
        oppari_service: OppariService,
        db: Database,
        clock: SystemClock,
        timezone: str,
        jobs_repo: ScheduledJobsRepo,
    ) -> None:
        self._opp = oppari_service
        self._db = db
        self._clock = clock
        self._tz = timezone
        self._jobs_repo = jobs_repo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # keep names stable across the project
        data["opp_service"] = self._opp
        data["db"] = self._db
        data["clock"] = self._clock
        data["timezone"] = self._tz
        data["jobs_repo"] = self._jobs_repo

        return await handler(event, data)
