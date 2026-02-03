# -*- coding: utf-8 -*-
"""Shared data models (Task)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Task:
    id: int
    user_id: int
    text: str
    task_type: str
    difficulty: int
    category: str
    deadline: Optional[str]
    scheduled_time: Optional[str]
    priority: int
    priority_source: str
    schedule_kind: Optional[str]
    schedule_json: Optional[str]
    deadline_time: Optional[str]
    scheduled_time_new: Optional[str]
    status: str
    cooldown_until: Optional[str]
    tags: str
    created_at: str
    updated_at: str
