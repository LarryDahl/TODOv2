"""
Constants for task status and actions.
"""
from __future__ import annotations

# Task event actions (stored in task_events.action)
TASK_ACTION_COMPLETED = "completed"
TASK_ACTION_DELETED = "deleted"

# Action log actions (stored in action_log.action)
ACTION_TASK_CREATED = "task_created"
ACTION_TASK_COMPLETED = "task_completed"
ACTION_TASK_EDITED = "task_edited"
ACTION_TASK_DELETED = "task_deleted"
ACTION_SUGGESTION_SHOWN = "suggestion_shown"
ACTION_SUGGESTION_ACCEPTED = "suggestion_accepted"
ACTION_SUGGESTION_IGNORED = "suggestion_ignored"

# Progress log source (for XP/progress hooks)
PROGRESS_SOURCE_TASK_COMPLETED = "task_completed"

# Task status (pool/queued/active/done)
TASK_STATUS_BACKLOG = "backlog"
TASK_STATUS_ACTIVE = "active"
TASK_STATUS_DROPPED = "dropped"

# Routine window defaults (HH:MM)
DEFAULT_MORNING_START = "05:30"
DEFAULT_MORNING_END = "07:30"
DEFAULT_EVENING_START = "20:00"
DEFAULT_EVENING_END = "22:00"
