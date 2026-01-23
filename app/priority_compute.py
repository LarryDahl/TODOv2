"""
Deterministic priority computation for tasks.

Combines multiple factors:
- Base priority (from '!' syntax)
- Deadline proximity
- Schedule window proximity

All weights are configurable in one place.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.db import Task


def _parse_iso_datetime(iso_str: str) -> Optional[datetime]:
    """Parse ISO datetime string to UTC datetime. Returns None on error."""
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError, TypeError):
        return None


def _calculate_urgency_boost(hours_until: float, urgency_hours: float, base_boost: float, max_boost: float) -> float:
    """Calculate urgency boost factor. Returns boost value."""
    if hours_until <= 0:
        return max_boost
    if hours_until >= urgency_hours:
        return base_boost
    urgency_factor = 1.0 - (hours_until / urgency_hours)
    return base_boost + urgency_factor * (max_boost - base_boost)


# Configurable weights for priority computation
PRIORITY_WEIGHTS = {
    "base_priority": 1.0,  # Multiplier for base priority (0-5 from '!' syntax)
    "deadline_base": 1.0,  # Base boost for having a deadline
    "deadline_urgency_hours": 24.0,  # Hours before deadline when urgency kicks in
    "deadline_overdue_boost": 50.0,  # Boost for overdue tasks
    "schedule_base": 1.0,  # Base boost for having a schedule
    "schedule_urgency_hours": 2.0,  # Hours before scheduled time when urgency kicks in
    "schedule_passed_boost": 30.0,  # Boost for tasks with passed schedule window
}


def compute_deadline_priority(deadline_iso: Optional[str], now: datetime) -> float:
    """
    Compute priority boost from deadline proximity.
    
    Rules:
    - Overdue tasks get maximum boost
    - Priority increases as deadline approaches
    - No deadline = 0 boost
    
    Args:
        deadline_iso: ISO datetime string in UTC, or None
        now: Current datetime in UTC
    
    Returns:
        Priority boost value (higher = more urgent)
    """
    if not deadline_iso:
        return 0.0
    
    deadline = _parse_iso_datetime(deadline_iso)
    if not deadline:
        return 0.0
    
    # Overdue tasks get maximum boost
    if deadline < now:
        return PRIORITY_WEIGHTS["deadline_overdue_boost"]
    
    # Calculate time until deadline
    time_until = deadline - now
    hours_until = time_until.total_seconds() / 3600.0
    
    # Base boost for having a deadline
    boost = PRIORITY_WEIGHTS["deadline_base"]
    
    # Urgency boost as deadline approaches
    if hours_until <= PRIORITY_WEIGHTS["deadline_urgency_hours"]:
        boost = _calculate_urgency_boost(
            hours_until,
            PRIORITY_WEIGHTS["deadline_urgency_hours"],
            PRIORITY_WEIGHTS["deadline_base"],
            PRIORITY_WEIGHTS["deadline_overdue_boost"]
        )
    
    return boost


def compute_schedule_priority(
    schedule_kind: Optional[str],
    schedule_json: Optional[str],
    now: datetime
) -> float:
    """
    Compute priority boost from schedule window proximity.
    
    Rules:
    - If scheduled window has passed without completion, high priority
    - Priority increases as scheduled time approaches
    - No schedule = 0 boost
    
    Args:
        schedule_kind: One of 'none', 'at_time', 'time_range', 'all_day', or None
        schedule_json: JSON string with schedule details, or None
        now: Current datetime in UTC
    
    Returns:
        Priority boost value (higher = more urgent)
    """
    if not schedule_kind or schedule_kind == 'none':
        return 0.0
    
    if not schedule_json:
        return 0.0
    
    try:
        schedule_data = json.loads(schedule_json)
    except (json.JSONDecodeError, TypeError):
        return 0.0
    
    boost = PRIORITY_WEIGHTS["schedule_base"]
    
    if schedule_kind == 'at_time':
        # Single timestamp
        timestamp_str = schedule_data.get('timestamp')
        if timestamp_str:
            scheduled_time = _parse_iso_datetime(timestamp_str)
            if scheduled_time:
                if scheduled_time < now:
                    return PRIORITY_WEIGHTS["schedule_passed_boost"]
                
                hours_until = (scheduled_time - now).total_seconds() / 3600.0
                if hours_until <= PRIORITY_WEIGHTS["schedule_urgency_hours"]:
                    boost = _calculate_urgency_boost(
                        hours_until,
                        PRIORITY_WEIGHTS["schedule_urgency_hours"],
                        PRIORITY_WEIGHTS["schedule_base"],
                        PRIORITY_WEIGHTS["schedule_passed_boost"]
                    )
        return boost
    
    elif schedule_kind == 'time_range':
        # Time range: check if window has passed or is approaching
        start_str = schedule_data.get('start_time')
        end_str = schedule_data.get('end_time')
        
        if start_str and end_str:
            start_time = _parse_iso_datetime(start_str)
            end_time = _parse_iso_datetime(end_str)
            if start_time and end_time:
                if end_time < now:
                    return PRIORITY_WEIGHTS["schedule_passed_boost"]
                
                if start_time <= now <= end_time:
                    return boost + (PRIORITY_WEIGHTS["schedule_passed_boost"] - PRIORITY_WEIGHTS["schedule_base"]) * 0.5
                
                hours_until = (start_time - now).total_seconds() / 3600.0
                if 0 < hours_until <= PRIORITY_WEIGHTS["schedule_urgency_hours"]:
                    boost = _calculate_urgency_boost(
                        hours_until,
                        PRIORITY_WEIGHTS["schedule_urgency_hours"],
                        PRIORITY_WEIGHTS["schedule_base"],
                        PRIORITY_WEIGHTS["schedule_passed_boost"]
                    )
    
    elif schedule_kind == 'all_day':
        # All day: check if date has passed
        date_str = schedule_data.get('date')
        if date_str:
            try:
                # Parse date (YYYY-MM-DD)
                scheduled_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                today = now.date()
                
                # If date has passed, high priority
                if scheduled_date < today:
                    return PRIORITY_WEIGHTS["schedule_passed_boost"]
                
                # If today, medium priority
                if scheduled_date == today:
                    return boost + (PRIORITY_WEIGHTS["schedule_passed_boost"] - PRIORITY_WEIGHTS["schedule_base"]) * 0.3
            except (ValueError, AttributeError):
                pass
    
    return boost


def compute_priority(task: "Task", now: Optional[datetime] = None) -> float:
    """
    Compute overall priority for a task combining all factors.
    
    Formula:
    computed_priority = (base_priority * weight) + deadline_boost + schedule_boost
    
    Args:
        task: Task object with priority, deadline, schedule info
        now: Current datetime in UTC (defaults to now if not provided)
    
    Returns:
        Computed priority value (higher = more urgent)
        Used for sorting tasks
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    # Base priority from '!' syntax (0-5)
    base_priority = task.priority * PRIORITY_WEIGHTS["base_priority"]
    
    # Deadline boost
    deadline_boost = compute_deadline_priority(task.deadline, now)
    
    # Schedule boost
    schedule_boost = compute_schedule_priority(task.schedule_kind, task.schedule_json, now)
    
    # Combined priority
    computed = base_priority + deadline_boost + schedule_boost
    
    return computed
