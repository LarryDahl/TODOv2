"""
Utility functions for date/time parsing and formatting.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def parse_time_input(text: str) -> Optional[str]:
    """Parse time input in formats: HHMM, HH:MM, HH MM. Returns HH:MM or None."""
    text = text.strip().replace(" ", "").replace(":", "")
    
    if len(text) == 4 and text.isdigit():
        hours, minutes = int(text[:2]), int(text[2:])
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return f"{hours:02d}:{minutes:02d}"
    return None


def parse_time_string(time_str: str) -> Optional[tuple[int, int]]:
    """Parse HH:MM time string. Returns (hour, minute) or None."""
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            hour, minute = int(parts[0]), int(parts[1])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return (hour, minute)
    except (ValueError, AttributeError):
        pass
    return None


def get_date_offset_days(offset: int) -> datetime:
    """Get datetime for today + offset days at midnight UTC."""
    now = datetime.now(timezone.utc)
    target_date = now.date()
    if offset != 0:
        from datetime import timedelta
        target_date = target_date + timedelta(days=offset)
    return datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)


def combine_date_time(date: datetime, time_str: str) -> datetime:
    """Combine a date with a time string (HH:MM format)."""
    time_parts = parse_time_string(time_str)
    if not time_parts:
        raise ValueError(f"Invalid time string: {time_str}")
    hour, minute = time_parts
    return datetime.combine(
        date.date(),
        datetime.min.time().replace(hour=hour, minute=minute),
        tzinfo=timezone.utc
    )


def format_datetime_iso(dt: datetime) -> str:
    """Format datetime as ISO 8601 string in UTC."""
    return dt.isoformat()


def parse_callback_data(data: str, expected_parts: int = 3) -> Optional[tuple[str, ...]]:
    """Parse callback data into parts. Returns None if invalid."""
    parts = data.split(":", expected_parts - 1)
    return tuple(parts) if len(parts) >= expected_parts else None


def parse_int_safe(value: str, default: Optional[int] = None) -> Optional[int]:
    """Safely parse integer, returns default on error."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
