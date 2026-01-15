from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any


AGENT_ID = "opp"


@dataclass(frozen=True)
class WorklogEntry:
    entry_id: str
    user_id: int
    agent_id: str
    start_at: datetime
    end_at: Optional[datetime]
    break_minutes: int
    description: str
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StartWorklogRequest:
    user_id: int
    start_at: datetime
    planned_task: Optional[str] = None
    project: Optional[str] = None
    category: Optional[str] = None


@dataclass(frozen=True)
class EndWorklogRequest:
    user_id: int
    end_at: datetime
    description: str
    learned: Optional[str] = None
    challenges: Optional[str] = None
    next_steps: Optional[str] = None
    break_minutes: int = 0
    completed_as_planned: Optional[bool] = None
    not_completed_reason: Optional[str] = None


@dataclass(frozen=True)
class OppariStatus:
    has_open_entry: bool
    open_entry: Optional[WorklogEntry]
