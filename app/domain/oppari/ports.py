from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Sequence, Dict, Any

from app.domain.oppari.models import WorklogEntry


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...


class IdGenerator(ABC):
    @abstractmethod
    def new_id(self) -> str: ...


class WorklogRepository(ABC):
    @abstractmethod
    async def ensure_user(self, user_id: int, now_iso: str) -> None: ...

    @abstractmethod
    async def ensure_agent_registered(self, agent_id: str, name: str, category: str, now_iso: str) -> None: ...

    @abstractmethod
    async def get_open_entry(self, user_id: int, agent_id: str) -> Optional[WorklogEntry]: ...

    @abstractmethod
    async def start_entry(
        self,
        entry_id: str,
        user_id: int,
        agent_id: str,
        start_at_iso: str,
        description: str,
        created_at_iso: str,
        project: Optional[str],
        category: Optional[str],
        metadata: Dict[str, Any],
    ) -> None: ...

    @abstractmethod
    async def end_entry(
        self,
        entry_id: str,
        end_at_iso: str,
        break_minutes: int,
        description: str,
        updated_at_iso: str,
        metadata: Dict[str, Any],
    ) -> None: ...

    @abstractmethod
    async def list_recent(self, user_id: int, agent_id: str, limit: int) -> Sequence[WorklogEntry]: ...
