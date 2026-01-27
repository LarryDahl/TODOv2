"""
Deterministic priority computation for tasks.

Combines multiple factors:
- Base priority (from '!' syntax)
- Deadline proximity (simplified step-based boost)
- Schedule proximity (simplified step-based boost)

All weights are configurable in one place.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _parse_iso_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string to UTC datetime. Returns None on error."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError, TypeError):
        return None


def _hours_until(target: datetime, now: datetime) -> float:
    """Calculate hours until target datetime. Negative if target is in the past."""
    delta = target - now
    return delta.total_seconds() / 3600.0


# Step-based boost configuration
# Each step defines: (hours_threshold, boost_value)
# Boost increases as deadline/scheduled_time approaches
DEADLINE_BOOST_STEPS = [
    (72.0, 10),   # 72h+ until deadline: +10 boost
    (24.0, 50),   # 24-72h: +50 boost
    (6.0, 200),   # 6-24h: +200 boost
    (1.0, 500),   # 1-6h: +500 boost
    (0.25, 800),  # 15min-1h: +800 boost
    (0.0, 1000),  # 0-15min: +1000 boost
]

DEADLINE_OVERDUE_BOOST = 1000  # Overdue deadline: always highest priority

SCHEDULED_BOOST_STEPS = [
    (72.0, 5),    # 72h+ until scheduled: +5 boost
    (24.0, 20),   # 24-72h: +20 boost
    (6.0, 100),   # 6-24h: +100 boost
    (1.0, 300),   # 1-6h: +300 boost
    (0.25, 500),  # 15min-1h: +500 boost
    (0.0, 500),   # 0-15min: +500 boost (stays high after scheduled time)
]

SCHEDULED_PASSED_BOOST = 500  # After scheduled time: +500 boost


def compute_time_boost(
    now: datetime,
    base_priority: int,
    scheduled_time: Optional[str],
    deadline_time: Optional[str]
) -> int:
    """
    Compute time-based priority boost using step-based logic.
    
    Priority boost rules:
    - Deadline overdue: MAX_BOOST (1000) - always highest priority
    - Deadline approaching: step-based boost (10-1000) based on time until deadline
    - Scheduled time passed: +500 boost
    - Scheduled time approaching: step-based boost (5-500) based on time until scheduled
    - No times: 0 boost
    
    Args:
        now: Current datetime in UTC
        base_priority: Base priority from '!' syntax (0-5)
        scheduled_time: ISO datetime string for scheduled time, or None
        deadline_time: ISO datetime string for deadline time, or None
    
    Returns:
        Integer boost value (higher = more urgent)
    """
    boost = 0
    
    # Deadline boost (highest priority)
    if deadline_time:
        deadline_dt = _parse_iso_datetime(deadline_time)
        if deadline_dt:
            hours_until = _hours_until(deadline_dt, now)
            
            # Overdue: maximum boost
            if hours_until < 0:
                return DEADLINE_OVERDUE_BOOST
            
            # Step-based boost as deadline approaches
            for threshold, step_boost in DEADLINE_BOOST_STEPS:
                if hours_until >= threshold:
                    boost = max(boost, step_boost)
                    break
    
    # Scheduled boost (lower priority than deadline)
    if scheduled_time:
        scheduled_dt = _parse_iso_datetime(scheduled_time)
        if scheduled_dt:
            hours_until = _hours_until(scheduled_dt, now)
            
            # After scheduled time: fixed boost
            if hours_until < 0:
                boost = max(boost, SCHEDULED_PASSED_BOOST)
            else:
                # Step-based boost as scheduled time approaches
                for threshold, step_boost in SCHEDULED_BOOST_STEPS:
                    if hours_until >= threshold:
                        boost = max(boost, step_boost)
                        break
    
    return boost


def compute_priority(
    base_priority: int,
    scheduled_time: Optional[str],
    deadline_time: Optional[str],
    now: Optional[datetime] = None
) -> int:
    """
    Compute overall priority for a task combining base priority and time boost.
    
    Formula:
    priority_effective = base_priority + time_boost
    
    Args:
        base_priority: Base priority from '!' syntax (0-5)
        scheduled_time: ISO datetime string for scheduled time, or None
        deadline_time: ISO datetime string for deadline time, or None
        now: Current datetime in UTC (defaults to now if not provided)
    
    Returns:
        Computed priority value (higher = more urgent)
        Used for sorting tasks
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    time_boost = compute_time_boost(now, base_priority, scheduled_time, deadline_time)
    
    # Combined priority
    return base_priority + time_boost
