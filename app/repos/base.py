# -*- coding: utf-8 -*-
"""Base repository with shared db path and helpers."""
from __future__ import annotations

from datetime import datetime, timezone


class BaseRepo:
    """Base for domain repos: shared db path and _now_iso()."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
