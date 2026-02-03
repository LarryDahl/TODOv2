# -*- coding: utf-8 -*-
"""
Callback data prefixes and action constants for inline keyboards.
Use these instead of hardcoded strings in handlers.
"""
from __future__ import annotations

from typing import Optional


def parse_callback(data: str, expected_parts: int = 3) -> Optional[tuple[str, ...]]:
    """Parse callback data into parts by ':'. Returns None if fewer than expected_parts."""
    parts = data.split(":", expected_parts - 1)
    return tuple(parts) if len(parts) >= expected_parts else None


# ---------------------------------------------------------------------------
# Prefixes (for F.data.startswith(...))
# ---------------------------------------------------------------------------
PREFIX_TASK = "task:"
PREFIX_TASK_DONE = "task:done:"
PREFIX_TASK_DEL = "task:del:"
PREFIX_TASK_MENU = "task:menu:"
PREFIX_TASK_EDIT_MENU = "task:edit_menu:"
PREFIX_TASK_EDIT_TEXT = "task:edit_text:"
PREFIX_TASK_PRIORITY_UP = "task:priority_up:"
PREFIX_TASK_PRIORITY_DOWN = "task:priority_down:"
PREFIX_TASK_DL_PLUS1H = "task:dl_plus1h:"
PREFIX_TASK_DL_PLUS24H = "task:dl_plus24h:"
PREFIX_TASK_DL_REMOVE = "task:dl_remove:"

PREFIX_T = "t:"  # mark task done (short form)
PREFIX_SUG_ACTIVE = "sug:active:"
PREFIX_SUG_DEFER = "sug:defer:"

PREFIX_VIEW_PROJECT = "view:project:"
PREFIX_PROJ_STEP_TOGGLE = "proj:step:toggle:"
PREFIX_DONE_PAGE = "done:page:"
PREFIX_DONE_RESTORE = "done:restore:"
PREFIX_DELETED_PAGE = "deleted:page:"
PREFIX_DELETED_RESTORE = "deleted:restore:"
PREFIX_STATS_AI = "stats:ai:"
PREFIX_SETTINGS_TZ = "settings:tz:"
PREFIX_ROUTINE_EDIT_LIST = "routine:edit_list:"
PREFIX_ROUTINE_EDIT_TASK = "routine:edit_task:"
PREFIX_ROUTINE_DEL = "routine:del:"
PREFIX_ROUTINE_ADD = "routine:add:"
PREFIX_ROUTINE_TOGGLE = "routine:toggle:"
PREFIX_ROUTINE_QUITTED = "routine:quitted:"

# Legacy prefixes (kept for backward compatibility; prefer newer names where applicable)
PREFIX_COMPLETED_RESTORE = "completed:restore:"  # legacy; prefer done:restore:
PREFIX_PS = "ps:"  # legacy project step toggle (ps:<step_id>)
PREFIX_PS_DEL = "ps:del:"
PREFIX_P = "p:"  # legacy project detail (p:<project_id>)
PREFIX_P_DEL = "p:del:"  # legacy cancel project
PREFIX_EDIT_PROJECT = "edit:project:"


# ---------------------------------------------------------------------------
# Exact / single action (for F.data == X or F.data.in_([...]))
# ---------------------------------------------------------------------------
HOME_HOME = "home:home"
HOME_REFRESH = "home:refresh"
HOME_EDIT = "home:edit"
HOME_PLUS = "home:plus"

VIEW_HOME = "view:home"
VIEW_REFRESH = "view:refresh"
VIEW_SETTINGS = "view:settings"
VIEW_EDIT = "view:edit"
VIEW_PROJECTS = "view:projects"
VIEW_DONE = "view:done"
VIEW_DELETED = "view:deleted"
VIEW_STATS = "view:stats"

NOOP = "noop"

SETTINGS_TIMEZONE = "settings:timezone"
SETTINGS_TOGGLE_MORNING_ROUTINES = "settings:toggle_morning_routines"
SETTINGS_TOGGLE_EVENING_ROUTINES = "settings:toggle_evening_routines"
SETTINGS_ROUTINE_EDIT_MENU = "settings:routine_edit_menu"
SETTINGS_ROUTINES_EDIT_MENU = "settings:routines:edit_menu"
SETTINGS_ROUTINES_EDIT_MORNING_TIME = "settings:routines:edit_morning_time"
SETTINGS_ROUTINES_EDIT_EVENING_TIME = "settings:routines:edit_evening_time"
SETTINGS_ROUTINES_MORNING_BACK = "settings:routines:morning_back"
SETTINGS_ROUTINES_EVENING_BACK = "settings:routines:evening_back"
SETTINGS_ROUTINES_PERUUTA = "settings:routines:peruuta"
SETTINGS_EXPORT_DB = "settings:export_db"
SETTINGS_RESET = "settings:reset"

STATS_ALL_TIME = "stats:all_time"
STATS_AI = "stats:ai"
STATS_RESET = "stats:reset"
STATS_RESET_CONFIRM = "stats:reset_confirm"

# Legacy exact (e.g. for .in_() or skip lists)
VIEW_HOME_LEGACY = VIEW_HOME
VIEW_REFRESH_LEGACY = VIEW_REFRESH

# Lists for F.data.in_()
NAV_HOME = [VIEW_HOME, HOME_HOME]
NAV_REFRESH = [VIEW_REFRESH, HOME_REFRESH]
NAV_EDIT = [VIEW_EDIT, HOME_EDIT]
ROUTINE_EDIT_MENU_ANY = [SETTINGS_ROUTINE_EDIT_MENU, SETTINGS_ROUTINES_EDIT_MENU]
STATS_MENU_ACTIONS = [STATS_ALL_TIME, STATS_AI, STATS_RESET, STATS_RESET_CONFIRM]
