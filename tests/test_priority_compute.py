"""
Unit tests for priority computation with time-based boosts.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app.priority_compute import compute_time_boost, compute_priority


def test_deadline_overdue_always_highest():
    """Test that overdue deadline tasks always have higher priority than non-overdue."""
    now = datetime.now(timezone.utc)
    
    # Overdue deadline (1 hour ago)
    overdue_deadline = (now - timedelta(hours=1)).isoformat()
    
    # Non-overdue deadline (1 hour from now)
    future_deadline = (now + timedelta(hours=1)).isoformat()
    
    # Overdue should have maximum boost (1000)
    overdue_boost = compute_time_boost(now, base_priority=0, scheduled_time=None, deadline_time=overdue_deadline)
    assert overdue_boost == 1000, f"Overdue deadline should have boost 1000, got {overdue_boost}"
    
    # Future deadline should have lower boost
    future_boost = compute_time_boost(now, base_priority=0, scheduled_time=None, deadline_time=future_deadline)
    assert future_boost < 1000, f"Future deadline should have boost < 1000, got {future_boost}"
    
    # Overdue should always be higher than any non-overdue
    assert overdue_boost > future_boost, "Overdue deadline should have higher boost than future deadline"


def test_scheduled_30min_higher_than_10h():
    """Test that scheduled task 30min away has higher boost than 10h away."""
    now = datetime.now(timezone.utc)
    
    # Scheduled 30 minutes from now
    scheduled_30min = (now + timedelta(minutes=30)).isoformat()
    
    # Scheduled 10 hours from now
    scheduled_10h = (now + timedelta(hours=10)).isoformat()
    
    boost_30min = compute_time_boost(now, base_priority=0, scheduled_time=scheduled_30min, deadline_time=None)
    boost_10h = compute_time_boost(now, base_priority=0, scheduled_time=scheduled_10h, deadline_time=None)
    
    assert boost_30min > boost_10h, f"Scheduled 30min away ({boost_30min}) should have higher boost than 10h away ({boost_10h})"


def test_no_times_zero_boost():
    """Test that tasks with no deadline or scheduled time have 0 boost."""
    now = datetime.now(timezone.utc)
    
    boost = compute_time_boost(now, base_priority=0, scheduled_time=None, deadline_time=None)
    
    assert boost == 0, f"Tasks with no times should have boost 0, got {boost}"


def test_deadline_step_boost():
    """Test that deadline boost increases as deadline approaches (step-based)."""
    now = datetime.now(timezone.utc)
    
    # Test different time thresholds
    test_cases = [
        (timedelta(hours=100), 10),   # 72h+ -> +10
        (timedelta(hours=50), 50),    # 24-72h -> +50
        (timedelta(hours=10), 200),   # 6-24h -> +200
        (timedelta(hours=3), 500),    # 1-6h -> +500
        (timedelta(minutes=30), 800), # 15min-1h -> +800
        (timedelta(minutes=5), 1000), # 0-15min -> +1000
    ]
    
    for time_delta, expected_boost in test_cases:
        deadline = (now + time_delta).isoformat()
        boost = compute_time_boost(now, base_priority=0, scheduled_time=None, deadline_time=deadline)
        assert boost == expected_boost, f"Deadline {time_delta} away should have boost {expected_boost}, got {boost}"


def test_scheduled_step_boost():
    """Test that scheduled boost increases as scheduled time approaches (step-based)."""
    now = datetime.now(timezone.utc)
    
    # Test different time thresholds
    test_cases = [
        (timedelta(hours=100), 5),    # 72h+ -> +5
        (timedelta(hours=50), 20),    # 24-72h -> +20
        (timedelta(hours=10), 100),   # 6-24h -> +100
        (timedelta(hours=3), 300),    # 1-6h -> +300
        (timedelta(minutes=30), 500), # 15min-1h -> +500
        (timedelta(minutes=5), 500),  # 0-15min -> +500
    ]
    
    for time_delta, expected_boost in test_cases:
        scheduled = (now + time_delta).isoformat()
        boost = compute_time_boost(now, base_priority=0, scheduled_time=scheduled, deadline_time=None)
        assert boost == expected_boost, f"Scheduled {time_delta} away should have boost {expected_boost}, got {boost}"


def test_scheduled_passed_boost():
    """Test that scheduled tasks after scheduled time have fixed boost."""
    now = datetime.now(timezone.utc)
    
    # Scheduled 1 hour ago
    scheduled_past = (now - timedelta(hours=1)).isoformat()
    
    boost = compute_time_boost(now, base_priority=0, scheduled_time=scheduled_past, deadline_time=None)
    
    assert boost == 500, f"Scheduled task after scheduled time should have boost 500, got {boost}"


def test_deadline_overrides_scheduled():
    """Test that deadline boost overrides scheduled boost when both are set."""
    now = datetime.now(timezone.utc)
    
    # Deadline 1 hour from now (should give +500 boost)
    deadline = (now + timedelta(hours=3)).isoformat()
    
    # Scheduled 30 minutes from now (should give +500 boost)
    scheduled = (now + timedelta(minutes=30)).isoformat()
    
    # When both are set, deadline should take precedence (higher boost)
    boost = compute_time_boost(now, base_priority=0, scheduled_time=scheduled, deadline_time=deadline)
    
    # Deadline boost should be used (500 for 3h deadline)
    assert boost == 500, f"Deadline boost should override scheduled, got {boost}"


def test_compute_priority_with_base():
    """Test that compute_priority combines base priority and time boost."""
    now = datetime.now(timezone.utc)
    
    # Base priority 3
    base_priority = 3
    
    # Deadline 1 hour from now (should give +500 boost)
    deadline = (now + timedelta(hours=3)).isoformat()
    
    # Total priority should be base + boost
    total_priority = compute_priority(base_priority, scheduled_time=None, deadline_time=deadline, now=now)
    
    assert total_priority == 503, f"Total priority should be 3 + 500 = 503, got {total_priority}"


def test_overdue_deadline_highest_priority():
    """Test that overdue deadline tasks have highest priority regardless of base priority."""
    now = datetime.now(timezone.utc)
    
    # Overdue deadline
    overdue_deadline = (now - timedelta(hours=1)).isoformat()
    
    # High base priority task with future deadline
    future_deadline = (now + timedelta(hours=10)).isoformat()
    
    # Overdue with low base priority
    overdue_priority = compute_priority(base_priority=0, scheduled_time=None, deadline_time=overdue_deadline, now=now)
    
    # Future with high base priority
    future_priority = compute_priority(base_priority=5, scheduled_time=None, deadline_time=future_deadline, now=now)
    
    # Overdue should always be higher
    assert overdue_priority > future_priority, f"Overdue deadline (priority {overdue_priority}) should be higher than future deadline with high base (priority {future_priority})"
