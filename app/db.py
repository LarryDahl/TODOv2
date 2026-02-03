# -*- coding: utf-8 -*-
"""
Database facade: Task model, constants, and TasksRepo that delegates to domain repos.
Public API: from app.db import Task, TasksRepo, DEFAULT_MORNING_START, ...
"""
from __future__ import annotations

import random
from typing import Optional

import aiosqlite

from app.constants import (
    ACTION_TASK_COMPLETED,
    ACTION_TASK_DELETED,
    ACTION_TASK_EDITED,
    DEFAULT_MORNING_END,
    DEFAULT_MORNING_START,
    DEFAULT_EVENING_END,
    DEFAULT_EVENING_START,
    PROGRESS_SOURCE_TASK_COMPLETED,
    TASK_STATUS_ACTIVE,
    TASK_STATUS_BACKLOG,
    TASK_STATUS_DROPPED,
)
from app.models import Task
from app.priority import parse_priority
from app.repos.projects_repo import ProjectsRepo
from app.repos.stats_repo import StatsRepo
from app.repos.suggestions_repo import SuggestionsRepo
from app.repos.tasks_repo import TasksRepoImpl

# Re-export for backward compatibility
__all__ = [
    "Task",
    "TasksRepo",
    "DEFAULT_MORNING_START",
    "DEFAULT_MORNING_END",
    "DEFAULT_EVENING_START",
    "DEFAULT_EVENING_END",
    "TASK_STATUS_BACKLOG",
    "TASK_STATUS_ACTIVE",
    "TASK_STATUS_DROPPED",
]


class TasksRepo:
    """Facade: delegates to TasksRepoImpl, SuggestionsRepo, StatsRepo, ProjectsRepo."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._tasks = TasksRepoImpl(db_path)
        self._suggestions = SuggestionsRepo(db_path)
        self._stats = StatsRepo(db_path)
        self._projects = ProjectsRepo(db_path)

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._tasks.init_tables(db)
            await self._suggestions.init_tables(db)
            await self._stats.init_tables(db)
            await self._projects.init_tables(db)
            await db.commit()

    def _now_iso(self) -> str:
        return self._tasks._now_iso()

    # ---- Tasks / events (delegate to _tasks) ----
    async def list_tasks(self, user_id: int, limit: int = 50):
        return await self._tasks.list_tasks(user_id, limit)

    async def list_completed_tasks(self, user_id: int, limit: int = 3):
        return await self._tasks.list_completed_tasks(user_id, limit)

    async def count_completed_tasks_today(self, user_id: int) -> int:
        return await self._tasks.count_completed_tasks_today(user_id)

    async def list_done_tasks(self, user_id: int, limit: int = 50, offset: int = 0):
        return await self._tasks.list_done_tasks(user_id, limit, offset)

    async def list_deleted_tasks(self, user_id: int, limit: int = 50, offset: int = 0):
        return await self._tasks.list_deleted_tasks(user_id, limit, offset)

    async def add_task(
        self,
        user_id: int,
        text: str,
        task_type: str = "regular",
        difficulty: int = 5,
        category: str = "",
        deadline: Optional[str] = None,
        scheduled_time: Optional[str] = None,
    ) -> int:
        task_id = await self._tasks.add_task(
            user_id, text, task_type, difficulty, category, deadline, scheduled_time
        )
        clean_title, priority = parse_priority(text)
        await self._stats.log_action(
            user_id=user_id,
            action="task_created",
            task_id=task_id,
            payload={"text": clean_title, "task_type": task_type, "priority": priority},
        )
        return task_id

    async def get_task(self, user_id: int, task_id: int):
        return await self._tasks.get_task(user_id, task_id)

    async def get_tasks_by_ids(self, user_id: int, ids: list[int]):
        return await self._tasks.get_tasks_by_ids(user_id, ids)

    async def get_active_task(self, user_id: int):
        return await self._tasks.get_active_task(user_id)

    async def get_active_tasks(self, user_id: int, limit: int = 7):
        return await self._tasks.get_active_tasks(user_id, limit)

    async def set_task_active(self, user_id: int, task_id: int) -> bool:
        return await self._tasks.set_task_active(user_id, task_id)

    async def get_backlog_tasks_for_fill(
        self, user_id: int, exclude_ids: Optional[set[int]] = None, limit: int = 6
    ):
        return await self._tasks.get_backlog_tasks_for_fill(user_id, exclude_ids, limit)

    async def defer_task(self, user_id: int, task_id: int, hours: int = 18) -> bool:
        return await self._tasks.defer_task(user_id, task_id, hours)

    async def get_active_card_message_id(self, user_id: int):
        return await self._tasks.get_active_card_message_id(user_id)

    async def set_active_card_message_id(
        self, user_id: int, message_id: Optional[int]
    ) -> None:
        return await self._tasks.set_active_card_message_id(user_id, message_id)

    async def update_task(self, user_id: int, task_id: int, new_text: str) -> bool:
        success = await self._tasks.update_task(user_id, task_id, new_text)
        if success:
            task = await self._tasks.get_task(user_id, task_id)
            if task:
                clean_title, priority = parse_priority(task.text)
                await self._stats.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={"new_text": clean_title, "priority": priority},
                )
        return success

    async def update_task_meta(
        self, user_id: int, task_id: int, patch: dict
    ) -> bool:
        success = await self._tasks.update_task_meta(user_id, task_id, patch)
        if success:
            await self._stats.log_action(
                user_id=user_id,
                action=ACTION_TASK_EDITED,
                task_id=task_id,
                payload=patch,
            )
        return success

    async def complete_task(self, user_id: int, task_id: int) -> bool:
        task = await self._tasks.complete_task(user_id, task_id)
        if not task:
            return False
        await self._stats.log_action(
            user_id=user_id,
            action=ACTION_TASK_COMPLETED,
            task_id=task_id,
            payload={"text": task.text},
        )
        await self._stats.insert_progress(
            user_id, PROGRESS_SOURCE_TASK_COMPLETED, task_id, 1.0
        )
        return True

    async def restore_completed_task(self, user_id: int, event_id: int) -> bool:
        return await self._tasks.restore_completed_task(user_id, event_id)

    async def get_completed_task_by_index(self, user_id: int, index: int):
        return await self._tasks.get_completed_task_by_index(user_id, index)

    async def restore_deleted_task(self, user_id: int, event_id: int) -> bool:
        return await self._tasks.restore_deleted_task(user_id, event_id)

    async def get_backlog_tasks(self, user_id: int, limit: int = 100):
        return await self._tasks.get_backlog_tasks(user_id, limit)

    async def delete_task_with_log(
        self, user_id: int, task_id: int, reason: str = ""
    ) -> bool:
        task = await self._tasks.delete_task_with_log(user_id, task_id, reason)
        if not task:
            return False
        await self._stats.log_action(
            user_id=user_id,
            action=ACTION_TASK_DELETED,
            task_id=task_id,
            payload={
                "reason": reason,
                "text": task.text,
                "priority": task.priority,
                "task_type": task.task_type,
                "difficulty": task.difficulty,
                "category": task.category,
                "deadline": task.deadline,
                "scheduled_time": task.scheduled_time,
                "schedule_kind": task.schedule_kind,
                "schedule_json": task.schedule_json,
                "tags": getattr(task, "tags", "[]"),
            },
        )
        return True

    async def set_deadline(
        self, task_id: int, user_id: int, deadline_utc: str
    ) -> bool:
        success = await self._tasks.set_deadline(task_id, user_id, deadline_utc)
        if success:
            task = await self._tasks.get_task(user_id=user_id, task_id=task_id)
            if task:
                clean_title, priority = parse_priority(task.text)
                await self._stats.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={"new_text": clean_title, "priority": priority},
                )
        return success

    async def clear_deadline(self, task_id: int, user_id: int) -> bool:
        success = await self._tasks.clear_deadline(task_id, user_id)
        if success:
            task = await self._tasks.get_task(user_id=user_id, task_id=task_id)
            if task:
                clean_title, priority = parse_priority(task.text)
                await self._stats.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={"new_text": clean_title, "priority": priority},
                )
        return success

    async def set_schedule(
        self,
        task_id: int,
        user_id: int,
        schedule_kind: str,
        schedule_payload: dict,
    ) -> bool:
        success = await self._tasks.set_schedule(
            task_id, user_id, schedule_kind, schedule_payload
        )
        if success:
            task = await self._tasks.get_task(user_id=user_id, task_id=task_id)
            if task:
                clean_title, priority = parse_priority(task.text)
                await self._stats.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={"new_text": clean_title, "priority": priority},
                )
        return success

    async def clear_schedule(self, task_id: int, user_id: int) -> bool:
        success = await self._tasks.clear_schedule(task_id, user_id)
        if success:
            task = await self._tasks.get_task(user_id=user_id, task_id=task_id)
            if task:
                clean_title, priority = parse_priority(task.text)
                await self._stats.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={"new_text": clean_title, "priority": priority},
                )
        return success

    # ---- Suggestion slots (delegate + orchestrate) ----
    async def get_suggestion_slots(self, user_id: int):
        return await self._suggestions.get_suggestion_slots(user_id)

    async def set_suggestion_slot(
        self,
        user_id: int,
        slot_index: int,
        task_id: Optional[int],
        now: str,
    ) -> None:
        return await self._suggestions.set_suggestion_slot(
            user_id, slot_index, task_id, now
        )

    async def remove_task_from_slots(
        self, user_id: int, task_id: int, now: str
    ) -> int:
        slots = await self._suggestions.get_suggestion_slots(user_id)
        idx = next((i for i, tid in enumerate(slots) if tid == task_id), -1)
        if idx < 0:
            return -1
        await self._suggestions.set_suggestion_slot(user_id, idx, None, now)
        await self._fill_one_slot(user_id, idx, now)
        return idx

    async def _fill_one_slot(
        self, user_id: int, slot_index: int, now: str
    ) -> Optional[int]:
        slots = await self._suggestions.get_suggestion_slots(user_id)
        in_slots = {tid for tid in slots if tid is not None}
        active_tasks = await self._tasks.get_active_tasks(user_id, limit=9)
        exclude_ids = in_slots | {t.id for t in active_tasks}
        candidates = await self._tasks.get_backlog_tasks_for_fill(
            user_id, exclude_ids=exclude_ids, limit=1
        )
        if not candidates:
            return None
        task_id = candidates[0].id
        await self._suggestions.set_suggestion_slot(
            user_id, slot_index, task_id, now
        )
        return task_id

    async def fill_suggestion_slots(self, user_id: int, now: str) -> None:
        active_tasks = await self._tasks.get_active_tasks(user_id, limit=9)
        need_suggestions = 9 - len(active_tasks)
        if need_suggestions <= 0:
            for i in range(9):
                await self._suggestions.set_suggestion_slot(user_id, i, None, now)
            return
        slots = await self._suggestions.get_suggestion_slots(user_id)
        in_slots = {tid for tid in slots if tid is not None}
        exclude = in_slots | {t.id for t in active_tasks}
        backlog = await self._tasks.get_backlog_tasks_for_fill(
            user_id, exclude_ids=exclude, limit=need_suggestions
        )
        used = set(in_slots)
        for i in range(need_suggestions):
            if i < len(slots) and slots[i] is not None:
                continue
            for t in backlog:
                if t.id not in used:
                    await self._suggestions.set_suggestion_slot(
                        user_id, i, t.id, now
                    )
                    used.add(t.id)
                    break
        for i in range(need_suggestions, 9):
            await self._suggestions.set_suggestion_slot(user_id, i, None, now)

    async def shuffle_suggestion_slots(
        self, user_id: int, now: str, need_suggestions: int
    ) -> None:
        if need_suggestions <= 0:
            for i in range(9):
                await self._suggestions.set_suggestion_slot(user_id, i, None, now)
            return
        active_tasks = await self._tasks.get_active_tasks(user_id, limit=9)
        active_ids = {t.id for t in active_tasks}
        backlog = await self._tasks.get_backlog_tasks_for_fill(
            user_id, exclude_ids=active_ids, limit=max(need_suggestions, 50)
        )
        if len(backlog) > need_suggestions:
            chosen = random.sample(backlog, need_suggestions)
            for i in range(need_suggestions):
                await self._suggestions.set_suggestion_slot(
                    user_id, i, chosen[i].id, now
                )
        else:
            for i in range(len(backlog)):
                await self._suggestions.set_suggestion_slot(
                    user_id, i, backlog[i].id, now
                )
        for i in range(need_suggestions, 9):
            await self._suggestions.set_suggestion_slot(user_id, i, None, now)

    async def log_suggestion_action(
        self, user_id: int, event_id: int, action: str
    ) -> None:
        return await self._suggestions.log_suggestion_action(
            user_id, event_id, action
        )

    async def get_snoozed_event_ids(self, user_id: int, days: int = 7):
        return await self._suggestions.get_snoozed_event_ids(user_id, days)

    # ---- Stats (delegate to _stats) ----
    async def log_action(
        self,
        user_id: int,
        action: str,
        task_id: Optional[int] = None,
        payload: Optional[dict] = None,
    ) -> None:
        return await self._stats.log_action(
            user_id, action, task_id, payload
        )

    async def get_statistics(self, user_id: int, days: int):
        return await self._stats.get_statistics(user_id, days)

    async def get_daily_progress(self, user_id: int) -> int:
        return await self._stats.get_daily_progress(user_id)

    async def get_all_time_stats(self, user_id: int):
        return await self._stats.get_all_time_stats(user_id)

    async def reset_all_data(self, user_id: int) -> None:
        await self._tasks.delete_user_tasks(user_id)
        await self._tasks.clear_task_events(user_id)
        await self._suggestions.clear_suggestion_log(user_id)
        await self._suggestions.clear_user_slots(user_id)
        await self._stats.clear_action_log(user_id)
        await self._tasks.clear_routine_completions_quitted(user_id)

    async def reset_stats(self, user_id: int) -> bool:
        await self._tasks.clear_task_events(user_id)
        await self._stats.clear_action_log(user_id)
        await self._suggestions.clear_suggestion_log(user_id)
        await self._tasks.clear_routine_completions_quitted(user_id)
        return True

    # ---- User settings / routines (delegate to _tasks) ----
    async def get_user_settings(self, user_id: int):
        return await self._tasks.get_user_settings(user_id)

    async def set_user_timezone(self, user_id: int, timezone: str) -> bool:
        return await self._tasks.set_user_timezone(user_id, timezone)

    async def toggle_show_done_in_home(self, user_id: int) -> bool:
        return await self._tasks.toggle_show_done_in_home(user_id)

    async def set_user_time_window(
        self,
        user_id: int,
        day_start_time: Optional[str] = None,
        day_end_time: Optional[str] = None,
    ) -> bool:
        return await self._tasks.set_user_time_window(
            user_id, day_start_time, day_end_time
        )

    async def toggle_morning_routines_enabled(self, user_id: int) -> bool:
        return await self._tasks.toggle_morning_routines_enabled(user_id)

    async def toggle_evening_routines_enabled(self, user_id: int) -> bool:
        return await self._tasks.toggle_evening_routines_enabled(user_id)

    async def list_routine_tasks(self, user_id: int, routine_type: str):
        return await self._tasks.list_routine_tasks(user_id, routine_type)

    async def add_routine_task(
        self, user_id: int, routine_type: str, text: str
    ) -> int:
        return await self._tasks.add_routine_task(user_id, routine_type, text)

    async def update_routine_task(
        self, user_id: int, routine_task_id: int, new_text: str
    ) -> bool:
        return await self._tasks.update_routine_task(
            user_id, routine_task_id, new_text
        )

    async def delete_routine_task(
        self, user_id: int, routine_task_id: int
    ) -> bool:
        return await self._tasks.delete_routine_task(
            user_id, routine_task_id
        )

    async def get_routine_completions_for_date(
        self, user_id: int, completion_date: str
    ):
        return await self._tasks.get_routine_completions_for_date(
            user_id, completion_date
        )

    async def set_routine_completion(
        self,
        user_id: int,
        routine_task_id: int,
        completion_date: str,
        done: bool,
    ) -> None:
        return await self._tasks.set_routine_completion(
            user_id, routine_task_id, completion_date, done
        )

    async def get_today_date_user_tz(self, user_id: int) -> str:
        return await self._tasks.get_today_date_user_tz(user_id)

    async def get_routine_windows(self, user_id: int):
        return await self._tasks.get_routine_windows(user_id)

    async def set_morning_window(
        self, user_id: int, start: str, end: str
    ) -> bool:
        return await self._tasks.set_morning_window(user_id, start, end)

    async def set_evening_window(
        self, user_id: int, start: str, end: str
    ) -> bool:
        return await self._tasks.set_evening_window(user_id, start, end)

    async def is_in_morning_window(self, user_id: int) -> bool:
        return await self._tasks.is_in_morning_window(user_id)

    async def is_in_evening_window(self, user_id: int) -> bool:
        return await self._tasks.is_in_evening_window(user_id)

    async def ensure_default_routine_tasks(
        self, user_id: int, routine_type: str
    ) -> None:
        return await self._tasks.ensure_default_routine_tasks(
            user_id, routine_type
        )

    async def set_routine_quitted(
        self, user_id: int, routine_type: str, completion_date: str
    ) -> None:
        return await self._tasks.set_routine_quitted(
            user_id, routine_type, completion_date
        )

    async def get_routine_quitted(
        self, user_id: int, routine_type: str, completion_date: str
    ) -> bool:
        return await self._tasks.get_routine_quitted(
            user_id, routine_type, completion_date
        )

    # ---- Projects (delegate to _projects) ----
    async def create_project(self, title: str, now: str) -> int:
        return await self._projects.create_project(title, now)

    async def add_project_steps(
        self, project_id: int, list_of_texts: list[str], now: str
    ) -> None:
        return await self._projects.add_project_steps(
            project_id, list_of_texts, now
        )

    async def get_active_project_steps(self):
        return await self._projects.get_active_project_steps()

    async def get_project_step(self, step_id: int):
        return await self._projects.get_project_step(step_id)

    async def mark_project_step_completed(
        self, step_id: int, done_at: str
    ) -> bool:
        return await self._projects.mark_project_step_completed(
            step_id, done_at
        )

    async def get_next_pending_step(
        self, project_id: int, after_order_index: int
    ):
        return await self._projects.get_next_pending_step(
            project_id, after_order_index
        )

    async def set_project_step_active(self, step_id: int) -> bool:
        return await self._projects.set_project_step_active(step_id)

    async def update_project_current_step(
        self,
        project_id: int,
        current_step_order: Optional[int],
        now: str,
    ) -> bool:
        return await self._projects.update_project_current_step(
            project_id, current_step_order, now
        )

    async def activate_first_project_step(
        self, project_id: int, now: str
    ) -> bool:
        return await self._projects.activate_first_project_step(
            project_id, now
        )

    async def mark_project_completed(self, project_id: int, now: str) -> bool:
        return await self._projects.mark_project_completed(project_id, now)

    async def advance_project_step(self, step_id: int, now: str):
        return await self._projects.advance_project_step(step_id, now)

    async def get_project(self, project_id: int):
        return await self._projects.get_project(project_id)

    async def list_all_projects(self):
        return await self._projects.list_all_projects()

    async def get_project_steps(self, project_id: int):
        return await self._projects.get_project_steps(project_id)

    async def update_project_step_text(
        self, step_id: int, new_text: str
    ) -> bool:
        return await self._projects.update_project_step_text(
            step_id, new_text
        )

    async def update_project_step_status(
        self, step_id: int, status: str
    ) -> bool:
        return await self._projects.update_project_step_status(
            step_id, status
        )

    async def move_project_step(self, step_id: int, direction: str) -> bool:
        return await self._projects.move_project_step(step_id, direction)

    async def add_step_to_project(
        self, project_id: int, step_text: str
    ) -> int:
        return await self._projects.add_step_to_project(
            project_id, step_text
        )

    async def delete_project_step(self, step_id: int) -> bool:
        return await self._projects.delete_project_step(step_id)

    async def delete_all_project_steps(self, project_id: int) -> bool:
        return await self._projects.delete_all_project_steps(project_id)

    async def cancel_project(self, project_id: int, now: str) -> bool:
        return await self._projects.cancel_project(project_id, now)

    async def toggle_project_step(self, step_id: int, now: str):
        return await self._projects.toggle_project_step(step_id, now)

    async def delete_project(self, project_id: int) -> bool:
        return await self._projects.delete_project(project_id)
