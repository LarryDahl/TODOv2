from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AgentCategory = Literal["process", "service", "reflective"]


@dataclass(frozen=True)
class AgentInfo:
    agent_id: str
    name: str
    category: AgentCategory
    is_active: bool
