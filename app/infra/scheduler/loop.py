# app/infra/scheduler/loop.py
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Awaitable, Callable, Dict, Optional

from app.infra.db.repo.scheduled_jobs_sqlite import ScheduledJobsRepo, ScheduledJob

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


RunnerFn = Callable[[ScheduledJob], Awaitable[None]]


@dataclass
class SchedulerConfig:
    poll_seconds: int = 10
    batch_limit: int = 25


class JobRunner:
    """
    job_type -> coroutine(job)
    Keep it generic; agents register their job_types here in composition root.
    """
    def __init__(self) -> None:
        self._handlers: Dict[str, RunnerFn] = {}

    def register(self, job_type: str, fn: RunnerFn) -> None:
        self._handlers[job_type] = fn

    async def run(self, job: ScheduledJob) -> None:
        fn = self._handlers.get(job.job_type)
        if not fn:
            raise RuntimeError(f"No runner registered for job_type={job.job_type}")
        await fn(job)


class SchedulerLoop:
    def __init__(self, repo: ScheduledJobsRepo, runner: JobRunner, cfg: SchedulerConfig = SchedulerConfig()) -> None:
        self._repo = repo
        self._runner = runner
        self._cfg = cfg
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as e:
                # never crash the bot because of scheduler, but log errors
                logger.error(f"Scheduler tick error: {e}", exc_info=True)
            await asyncio.sleep(self._cfg.poll_seconds)

    async def _tick(self) -> None:
        now_utc = utc_now_iso()
        due = await self._repo.list_due(now_utc, limit=self._cfg.batch_limit)
        for job in due:
            await self._execute_one(job)

    async def _execute_one(self, job: ScheduledJob) -> None:
        now_iso = utc_now_iso()
        try:
            await self._runner.run(job)
            next_due = self._compute_next_due(job)
            await self._repo.mark_run_ok(job.job_id, next_due, now_iso)
        except Exception as e:
            logger.error(f"Job execution failed: job_id={job.job_id}, job_type={job.job_type}, error={e}", exc_info=True)
            await self._repo.mark_run_failed(job.job_id, str(e), now_iso)

    def _compute_next_due(self, job: ScheduledJob) -> Optional[str]:
        """
        Start simple:
        - schedule_kind == "once"     => None (complete)
        - schedule_kind == "interval" => now + interval_minutes (from schedule_json)
        """
        kind = job.schedule_kind
        if kind == "once":
            return None

        if kind == "interval":
            mins = int(job.schedule.get("minutes", 0) or 0)
            if mins <= 0:
                return None
            nxt = datetime.now(timezone.utc) + timedelta(minutes=mins)
            return nxt.isoformat()

        # cron/rrule coming next
        return None
