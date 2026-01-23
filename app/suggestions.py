"""
Deterministic task suggestion selector.

Selects 3-7 tasks from backlog (completed/deleted tasks) based on:
- Priority '!' (higher priority first)
- Age (older tasks might be worth revisiting)
- Missing metadata (tasks without deadline/schedule)
- Avoided/old (tasks completed/deleted long ago)
- Scheduled/deadline soon (tasks with approaching deadlines)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional


def score_suggestion(
    task_text: str,
    priority: int,
    completed_at: Optional[str],
    deleted_at: Optional[str],
    has_deadline: bool,
    has_schedule: bool,
    now: datetime,
) -> float:
    """
    Score a task for suggestion priority.
    
    Higher score = more likely to be suggested.
    
    Args:
        task_text: Task text (may contain '!' priority markers)
        priority: Base priority from '!' (0-5)
        completed_at: ISO datetime when task was completed, or None
        deleted_at: ISO datetime when task was deleted, or None
        has_deadline: Whether task had a deadline
        has_schedule: Whether task had a schedule
        now: Current datetime in UTC
    
    Returns:
        Score (higher = more relevant for suggestion)
    """
    score = 0.0
    
    # Factor 1: Base priority from '!' (0-5)
    # Higher priority tasks are more important to resurface
    score += priority * 10.0
    
    # Factor 2: Age (older tasks get higher score for "revisit" value)
    event_time: Optional[datetime] = None
    if deleted_at:
        try:
            event_time = datetime.fromisoformat(deleted_at.replace('Z', '+00:00'))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            pass
    elif completed_at:
        try:
            event_time = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            pass
    
    if event_time:
        days_ago = (now - event_time).total_seconds() / 86400.0
        # Older tasks (30+ days) get bonus, but very old (365+ days) get less
        if 30 <= days_ago < 365:
            score += 5.0 * (days_ago / 30.0)  # Up to ~60 points for 1 year old
        elif days_ago >= 365:
            score += 2.0  # Very old tasks get small bonus
    
    # Factor 3: Missing metadata (tasks without deadline/schedule might benefit from adding them)
    if not has_deadline and not has_schedule:
        score += 3.0
    
    # Factor 4: Deleted tasks might be worth revisiting (user might have deleted by mistake)
    if deleted_at:
        score += 2.0
    
    return score


def select_suggestions(
    completed_tasks: list[dict],
    deleted_tasks: list[dict],
    now: Optional[datetime] = None,
    max_suggestions: int = 7,
    min_suggestions: int = 3,
) -> list[dict]:
    """
    Select 3-7 task suggestions from backlog deterministically.
    
    Args:
        completed_tasks: List of completed task events (from task_events with action='completed')
        deleted_tasks: List of deleted task events (from task_events with action='deleted')
        now: Current datetime (defaults to now if not provided)
        max_suggestions: Maximum number of suggestions (default 7)
        min_suggestions: Minimum number of suggestions (default 3)
    
    Returns:
        List of suggestion dicts with keys:
        - text: Task text
        - priority: Priority (0-5)
        - event_id: Event ID (for tracking)
        - event_type: 'completed' or 'deleted'
        - event_at: ISO datetime of event
        - score: Suggestion score
    """
    if now is None:
        now = datetime.now(timezone.utc)
    
    # Combine and score all backlog tasks
    candidates: list[dict] = []
    
    # Process completed tasks
    for task in completed_tasks:
        task_text = task.get('text', '') or task.get('title', '')
        if not task_text:
            continue
        
        # Use priority from tasks table if available, otherwise parse from text
        from app.priority import parse_priority
        clean_text, parsed_priority = parse_priority(task_text)
        priority = task.get('priority')
        if priority is None:
            priority = parsed_priority
        
        # Check if task had deadline/schedule from tasks table
        has_deadline = bool(task.get('deadline'))
        has_schedule = bool(task.get('schedule_kind') and task.get('schedule_kind') != 'none')
        
        event_at = task.get('at') or task.get('updated_at', '')
        
        score = score_suggestion(
            task_text=task_text,
            priority=priority,
            completed_at=event_at,
            deleted_at=None,
            has_deadline=has_deadline,
            has_schedule=has_schedule,
            now=now,
        )
        
        candidates.append({
            'text': clean_text,  # Store clean text (without '!')
            'priority': priority,
            'event_id': task.get('id') or task.get('job_id'),
            'event_type': 'completed',
            'event_at': event_at,
            'score': score,
        })
    
    # Process deleted tasks
    for task in deleted_tasks:
        task_text = task.get('text', '') or task.get('title', '')
        if not task_text:
            continue
        
        # Use priority from tasks table if available, otherwise parse from text
        from app.priority import parse_priority
        clean_text, parsed_priority = parse_priority(task_text)
        priority = task.get('priority')
        if priority is None:
            priority = parsed_priority
        
        # Check if task had deadline/schedule from tasks table
        has_deadline = bool(task.get('deadline'))
        has_schedule = bool(task.get('schedule_kind') and task.get('schedule_kind') != 'none')
        
        event_at = task.get('at') or task.get('updated_at', '')
        
        score = score_suggestion(
            task_text=task_text,
            priority=priority,
            completed_at=None,
            deleted_at=event_at,
            has_deadline=has_deadline,
            has_schedule=has_schedule,
            now=now,
        )
        
        candidates.append({
            'text': clean_text,
            'priority': priority,
            'event_id': task.get('id') or task.get('job_id'),
            'event_type': 'deleted',
            'event_at': event_at,
            'score': score,
        })
    
    # Sort by score (descending), then by event_at (descending for tie-breaking)
    candidates.sort(key=lambda x: (-x['score'], x.get('event_at', '')))
    
    # Select top suggestions
    selected = candidates[:max_suggestions]
    
    # If we have fewer than min_suggestions, return what we have
    if len(selected) < min_suggestions:
        return selected
    
    return selected
