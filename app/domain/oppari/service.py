from __future__ import annotations

from typing import Dict, Any

from app.domain.common.errors import ConflictError, NotFoundError
from app.domain.common.time import to_iso
from app.domain.oppari.models import (
    AGENT_ID,
    StartWorklogRequest,
    EndWorklogRequest,
    OppariStatus,
    WorklogEntry,
)
from app.domain.oppari.ports import WorklogRepository, Clock, IdGenerator
from app.domain.oppari.rules import (
    validate_start_end,
    validate_break_minutes,
    validate_description,
)


class OppariService:
    """
    Oppari business logic. No aiogram. No sqlite.
    """

    def __init__(self, repo: WorklogRepository, clock: Clock, ids: IdGenerator) -> None:
        self._repo = repo
        self._clock = clock
        self._ids = ids

    async def bootstrap(self) -> None:
        now = self._clock.now()
        await self._repo.ensure_agent_registered(
            agent_id=AGENT_ID,
            name="Oppari",
            category="process",
            now_iso=to_iso(now),
        )

    async def status(self, user_id: int) -> OppariStatus:
        open_entry = await self._repo.get_open_entry(user_id=user_id, agent_id=AGENT_ID)
        return OppariStatus(has_open_entry=open_entry is not None, open_entry=open_entry)

    async def start_worklog(self, req: StartWorklogRequest) -> WorklogEntry:
        now = self._clock.now()
        await self._repo.ensure_user(req.user_id, to_iso(now))

        existing = await self._repo.get_open_entry(req.user_id, AGENT_ID)
        if existing:
            raise ConflictError("An Oppari session is already running.")

        entry_id = self._ids.new_id()

        metadata: Dict[str, Any] = {}
        if req.planned_task:
            metadata["planned_task"] = req.planned_task

        start_desc = req.planned_task or "Oppari work started"

        await self._repo.start_entry(
            entry_id=entry_id,
            user_id=req.user_id,
            agent_id=AGENT_ID,
            start_at_iso=to_iso(req.start_at),
            description=start_desc,
            created_at_iso=to_iso(now),
            project=req.project,
            category=req.category,
            metadata=metadata,
        )

        return WorklogEntry(
            entry_id=entry_id,
            user_id=req.user_id,
            agent_id=AGENT_ID,
            start_at=req.start_at,
            end_at=None,
            break_minutes=0,
            description=start_desc,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

    async def end_worklog(self, req: EndWorklogRequest) -> WorklogEntry:
        validate_description(req.description)
        validate_break_minutes(req.break_minutes)

        open_entry = await self._repo.get_open_entry(req.user_id, AGENT_ID)
        if not open_entry:
            raise NotFoundError("No running Oppari session found.")

        validate_start_end(open_entry.start_at, req.end_at)

        now = self._clock.now()
        metadata = dict(open_entry.metadata or {})

        if req.learned is not None:
            metadata["learned"] = req.learned
        if req.challenges is not None:
            metadata["challenges"] = req.challenges
        if req.next_steps is not None:
            metadata["next_steps"] = req.next_steps
        if req.completed_as_planned is not None:
            metadata["completed_as_planned"] = req.completed_as_planned
        if req.not_completed_reason is not None:
            metadata["not_completed_reason"] = req.not_completed_reason

        await self._repo.end_entry(
            entry_id=open_entry.entry_id,
            end_at_iso=to_iso(req.end_at),
            break_minutes=req.break_minutes,
            description=req.description,
            updated_at_iso=to_iso(now),
            metadata=metadata,
        )

        return WorklogEntry(
            entry_id=open_entry.entry_id,
            user_id=open_entry.user_id,
            agent_id=open_entry.agent_id,
            start_at=open_entry.start_at,
            end_at=req.end_at,
            break_minutes=req.break_minutes,
            description=req.description,
            metadata=metadata,
            created_at=open_entry.created_at,
            updated_at=now,
        )

    async def recent(self, user_id: int, limit: int = 10):
        return await self._repo.list_recent(user_id=user_id, agent_id=AGENT_ID, limit=limit)