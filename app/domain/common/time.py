from __future__ import annotations

from datetime import datetime


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return dt


def to_iso(dt: datetime) -> str:
    ensure_aware(dt)
    # store as ISO 8601 with offset
    return dt.isoformat()


def from_iso(s: str) -> datetime:
    # Python can parse ISO with offset via fromisoformat
    return datetime.fromisoformat(s)
