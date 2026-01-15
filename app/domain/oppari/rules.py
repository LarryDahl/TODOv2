from __future__ import annotations

from datetime import datetime

from app.domain.common.errors import ValidationError
from app.domain.common.time import ensure_aware


def validate_start_end(start_at: datetime, end_at: datetime) -> None:
    ensure_aware(start_at)
    ensure_aware(end_at)
    if end_at <= start_at:
        raise ValidationError("End time must be after start time.")


def validate_break_minutes(break_minutes: int) -> None:
    if break_minutes < 0:
        raise ValidationError("Break minutes cannot be negative.")
    if break_minutes > 24 * 60:
        raise ValidationError("Break minutes is unrealistically large.")


def validate_description(description: str) -> None:
    if not description or not description.strip():
        raise ValidationError("Description is required.")
    if len(description.strip()) > 2000:
        raise ValidationError("Description is too long (max 2000 chars).")
