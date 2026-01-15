from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.oppari.ports import Clock


class SystemClock(Clock):
    def __init__(self, tz_name: str) -> None:
        self._tz = ZoneInfo(tz_name)

    def now(self) -> datetime:
        return datetime.now(self._tz)
