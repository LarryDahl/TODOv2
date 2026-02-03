# -*- coding: utf-8 -*-
"""Tasks, task_events, user_settings, and routines (morning/evening)."""
from __future__ import annotations

import json
from typing import Optional

import aiosqlite

from app.constants import (
    TASK_ACTION_COMPLETED,
    TASK_ACTION_DELETED,
    ACTION_TASK_DELETED,
    TASK_STATUS_ACTIVE,
    TASK_STATUS_BACKLOG,
    DEFAULT_MORNING_START,
    DEFAULT_MORNING_END,
    DEFAULT_EVENING_START,
    DEFAULT_EVENING_END,
)
from app.models import Task
from app.priority import parse_priority
from app.repos.base import BaseRepo
from app.utils import parse_time_string, time_in_window


class TasksRepoImpl(BaseRepo):
    """tasks, task_events, user_settings, user_routine_* tables. No action_log/progress_log."""

    ROUTINE_TYPE_MORNING = "morning"
    ROUTINE_TYPE_EVENING = "evening"
    DEFAULT_MORNING_TASKS = ["Aamupala", "Aamujumppa", "Aamusuihku"]
    DEFAULT_EVENING_TASKS = ["Iltapala", "Iltasuihku", "Iltasatu"]

    async def init_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                task_type TEXT NOT NULL DEFAULT 'regular',
                difficulty INTEGER NOT NULL DEFAULT 5,
                category TEXT NOT NULL DEFAULT '',
                deadline TEXT,
                scheduled_time TEXT,
                priority INTEGER NOT NULL DEFAULT 0,
                priority_source TEXT NOT NULL DEFAULT 'bang_suffix',
                schedule_kind TEXT,
                schedule_json TEXT,
                deadline_time TEXT,
                scheduled_time_new TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        cursor = await db.execute("PRAGMA table_info(tasks)")
        columns = [row[1] for row in await cursor.fetchall()]
        for col, sql in [
            ("task_type", "ALTER TABLE tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'regular';"),
            ("difficulty", "ALTER TABLE tasks ADD COLUMN difficulty INTEGER NOT NULL DEFAULT 5;"),
            ("category", "ALTER TABLE tasks ADD COLUMN category TEXT NOT NULL DEFAULT '';"),
            ("deadline", "ALTER TABLE tasks ADD COLUMN deadline TEXT;"),
            ("scheduled_time", "ALTER TABLE tasks ADD COLUMN scheduled_time TEXT;"),
            ("priority", "ALTER TABLE tasks ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;"),
            ("priority_source", "ALTER TABLE tasks ADD COLUMN priority_source TEXT NOT NULL DEFAULT 'bang_suffix';"),
            ("schedule_kind", "ALTER TABLE tasks ADD COLUMN schedule_kind TEXT;"),
            ("schedule_json", "ALTER TABLE tasks ADD COLUMN schedule_json TEXT;"),
            ("deadline_time", "ALTER TABLE tasks ADD COLUMN deadline_time TEXT;"),
            ("scheduled_time_new", "ALTER TABLE tasks ADD COLUMN scheduled_time_new TEXT;"),
            ("status", "ALTER TABLE tasks ADD COLUMN status TEXT NOT NULL DEFAULT 'backlog';"),
            ("cooldown_until", "ALTER TABLE tasks ADD COLUMN cooldown_until TEXT;"),
            ("tags", "ALTER TABLE tasks ADD COLUMN tags TEXT NOT NULL DEFAULT '[]';"),
        ]:
            if col not in columns:
                await db.execute(sql)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id INTEGER,
                action TEXT NOT NULL,
                text TEXT NOT NULL,
                at TEXT NOT NULL
            );
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_task_events_user_id ON task_events(user_id);")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                timezone TEXT NOT NULL DEFAULT 'Europe/Helsinki',
                show_done_in_home BOOLEAN NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );
            """
        )
        us_cursor = await db.execute("PRAGMA table_info(user_settings)")
        us_columns = [row[1] for row in await us_cursor.fetchall()]
        if "active_card_message_id" not in us_columns:
            await db.execute("ALTER TABLE user_settings ADD COLUMN active_card_message_id INTEGER;")
        if "day_start_time" not in us_columns:
            await db.execute("ALTER TABLE user_settings ADD COLUMN day_start_time TEXT;")
        if "day_end_time" not in us_columns:
            await db.execute("ALTER TABLE user_settings ADD COLUMN day_end_time TEXT;")
        if "morning_routines_enabled" not in us_columns:
            await db.execute("ALTER TABLE user_settings ADD COLUMN morning_routines_enabled BOOLEAN NOT NULL DEFAULT 0;")
        if "evening_routines_enabled" not in us_columns:
            await db.execute("ALTER TABLE user_settings ADD COLUMN evening_routines_enabled BOOLEAN NOT NULL DEFAULT 0;")
        if "morning_start_time" not in us_columns:
            await db.execute("ALTER TABLE user_settings ADD COLUMN morning_start_time TEXT;")
        if "morning_end_time" not in us_columns:
            await db.execute("ALTER TABLE user_settings ADD COLUMN morning_end_time TEXT;")
        if "evening_start_time" not in us_columns:
            await db.execute("ALTER TABLE user_settings ADD COLUMN evening_start_time TEXT;")
        if "evening_end_time" not in us_columns:
            await db.execute("ALTER TABLE user_settings ADD COLUMN evening_end_time TEXT;")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_routine_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                routine_type TEXT NOT NULL,
                order_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                CHECK (routine_type IN ('morning', 'evening'))
            );
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_routine_tasks_user_type ON user_routine_tasks(user_id, routine_type);")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_routine_completions (
                user_id INTEGER NOT NULL,
                routine_task_id INTEGER NOT NULL,
                completion_date TEXT NOT NULL,
                done_at TEXT NOT NULL,
                PRIMARY KEY (user_id, routine_task_id, completion_date),
                FOREIGN KEY (routine_task_id) REFERENCES user_routine_tasks(id)
            );
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_routine_completions_user_date ON user_routine_completions(user_id, completion_date);")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_routine_quitted (
                user_id INTEGER NOT NULL,
                routine_type TEXT NOT NULL,
                completion_date TEXT NOT NULL,
                at TEXT NOT NULL,
                PRIMARY KEY (user_id, routine_type, completion_date)
            );
            """
        )

    async def list_tasks(self, user_id: int, limit: int = 50) -> list[Task]:
        from app.priority_compute import compute_priority
        from datetime import datetime as dt, timezone as tz
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, status, cooldown_until, tags, created_at, updated_at
                FROM tasks WHERE user_id = ?;
                """,
                (user_id,),
            )
            tasks = [Task(**dict(r)) for r in await cur.fetchall()]
        now = dt.now(tz.utc)
        def sort_key(task: Task) -> tuple:
            effective_priority = compute_priority(
                base_priority=task.priority,
                scheduled_time=task.scheduled_time_new,
                deadline_time=task.deadline_time,
                now=now,
            )
            return (effective_priority, task.created_at)
        tasks.sort(key=sort_key)
        return tasks[:limit]

    async def list_completed_tasks(self, user_id: int, limit: int = 3) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, task_id, text, at
                FROM task_events
                WHERE user_id = ? AND action = ? ORDER BY at DESC LIMIT ?;
                """,
                (user_id, TASK_ACTION_COMPLETED, limit),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def count_completed_tasks_today(self, user_id: int) -> int:
        from app.clock import SystemClock
        from datetime import timedelta, timezone
        settings = await self.get_user_settings(user_id)
        user_tz_str = settings.get("timezone", "Europe/Helsinki")
        now_user_tz = SystemClock.now_user_tz(user_tz_str)
        start_of_today = now_user_tz.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_today = start_of_today + timedelta(days=1) - timedelta(microseconds=1)
        start_of_today_utc = start_of_today.astimezone(timezone.utc)
        end_of_today_utc = end_of_today.astimezone(timezone.utc)
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT COUNT(*) as count FROM task_events
                WHERE user_id = ? AND action = ? AND at >= ? AND at <= ?;
                """,
                (user_id, TASK_ACTION_COMPLETED, start_of_today_utc.isoformat(), end_of_today_utc.isoformat()),
            )
            row = await cur.fetchone()
            return row["count"] if row else 0

    async def _list_event_tasks(self, user_id: int, action: str, limit: int, offset: int) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT e.id as job_id, e.task_id, e.text as title, NULL as due_at, NULL as schedule_kind, NULL as schedule_json, ? as status, e.at as updated_at
                FROM task_events e
                WHERE e.user_id = ? AND e.action = ? ORDER BY e.at DESC LIMIT ? OFFSET ?;
                """,
                (action, user_id, action, limit, offset),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def list_done_tasks(self, user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
        return await self._list_event_tasks(user_id, TASK_ACTION_COMPLETED, limit, offset)

    async def list_deleted_tasks(self, user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
        return await self._list_event_tasks(user_id, TASK_ACTION_DELETED, limit, offset)

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
        clean_title, priority = parse_priority(text)
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, status, cooldown_until, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (user_id, clean_title, task_type, difficulty, category, deadline, scheduled_time, priority, "bang_suffix", None, None, deadline, scheduled_time, TASK_STATUS_BACKLOG, None, "[]", now, now),
            )
            await conn.commit()
            return int(cur.lastrowid)

    async def get_task(self, user_id: int, task_id: int) -> Optional[Task]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, status, cooldown_until, tags, created_at, updated_at
                FROM tasks WHERE user_id = ? AND id = ?;
                """,
                (user_id, task_id),
            )
            row = await cur.fetchone()
            return Task(**dict(row)) if row else None

    async def get_tasks_by_ids(self, user_id: int, ids: list[int]) -> dict[int, Task]:
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, status, cooldown_until, tags, created_at, updated_at
                FROM tasks WHERE user_id = ? AND id IN (""" + placeholders + """);
                """,
                (user_id, *ids),
            )
            rows = await cur.fetchall()
            return {r["id"]: Task(**dict(r)) for r in rows}

    async def get_active_task(self, user_id: int) -> Optional[Task]:
        tasks = await self.get_active_tasks(user_id, limit=1)
        return tasks[0] if tasks else None

    async def get_active_tasks(self, user_id: int, limit: int = 7) -> list[Task]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, status, cooldown_until, tags, created_at, updated_at
                FROM tasks WHERE user_id = ? AND status = ? ORDER BY updated_at DESC LIMIT ?;
                """,
                (user_id, TASK_STATUS_ACTIVE, limit),
            )
            rows = await cur.fetchall()
            return [Task(**dict(r)) for r in rows]

    async def set_task_active(self, user_id: int, task_id: int) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE user_id = ? AND id = ?;",
                (TASK_STATUS_ACTIVE, now, user_id, task_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def get_backlog_tasks_for_fill(
        self, user_id: int, exclude_ids: Optional[set[int]] = None, limit: int = 6
    ) -> list[Task]:
        exclude_ids = exclude_ids or set()
        now_iso = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, status, cooldown_until, tags, created_at, updated_at
                FROM tasks
                WHERE user_id = ? AND status = ? AND (cooldown_until IS NULL OR cooldown_until <= ?);
                """,
                (user_id, TASK_STATUS_BACKLOG, now_iso),
            )
            tasks = [Task(**dict(r)) for r in await cur.fetchall()]
        tasks = [t for t in tasks if t.id not in exclude_ids]
        tasks.sort(key=lambda t: (-t.priority, t.created_at))
        return tasks[:limit]

    async def defer_task(self, user_id: int, task_id: int, hours: int = 18) -> bool:
        from datetime import datetime, timedelta
        now = self._now_iso()
        try:
            dt = __import__("datetime").datetime.fromisoformat(now.replace("Z", "+00:00"))
        except Exception:
            from datetime import timezone
            dt = __import__("datetime").datetime.now(timezone.utc)
        end = (dt + timedelta(hours=hours)).isoformat()
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "UPDATE tasks SET status = ?, cooldown_until = ?, updated_at = ? WHERE user_id = ? AND id = ?;",
                (TASK_STATUS_BACKLOG, end, now, user_id, task_id),
            )
            await conn.commit()
            if cur.rowcount == 0:
                return False
        return True

    async def get_active_card_message_id(self, user_id: int) -> Optional[int]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT active_card_message_id FROM user_settings WHERE user_id = ?;",
                (user_id,),
            )
            row = await cur.fetchone()
            if row and row["active_card_message_id"] is not None:
                return int(row["active_card_message_id"])
        return None

    async def set_active_card_message_id(self, user_id: int, message_id: Optional[int]) -> None:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO user_settings (user_id, timezone, show_done_in_home, updated_at, active_card_message_id)
                VALUES (?, 'Europe/Helsinki', 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET updated_at = ?, active_card_message_id = ?;
                """,
                (user_id, now, message_id, now, message_id),
            )
            await conn.commit()

    async def update_task(self, user_id: int, task_id: int, new_text: str) -> bool:
        clean_title, priority = parse_priority(new_text)
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                UPDATE tasks SET text = ?, priority = ?, priority_source = ?, updated_at = ?
                WHERE user_id = ? AND id = ?;
                """,
                (clean_title, priority, "bang_suffix", now, user_id, task_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def update_task_meta(
        self, user_id: int, task_id: int, patch: dict
    ) -> bool:
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if not task:
            return False
        now = self._now_iso()
        updates = []
        params = []
        if "text" in patch:
            clean_title, priority = parse_priority(patch["text"])
            updates.extend(["text = ?", "priority = ?", "priority_source = ?"])
            params.extend([clean_title, priority, "bang_suffix"])
        elif "priority" in patch:
            priority = max(0, min(5, int(patch["priority"])))
            updates.append("priority = ?")
            params.append(priority)
        elif "increment_priority" in patch:
            new_priority = min(5, task.priority + 1)
            updates.append("priority = ?")
            params.append(new_priority)
        elif "decrement_priority" in patch:
            new_priority = max(0, task.priority - 1)
            updates.append("priority = ?")
            params.append(new_priority)
        if "deadline" in patch:
            updates.append("deadline = ?")
            params.append(patch["deadline"])
        updates.append("updated_at = ?")
        params.append(now)
        params.extend([user_id, task_id])
        if not updates:
            return False
        async with aiosqlite.connect(self._db_path) as conn:
            sql = "UPDATE tasks SET " + ", ".join(updates) + " WHERE user_id = ? AND id = ?;"
            cur = await conn.execute(sql, params)
            await conn.commit()
            return cur.rowcount > 0

    async def _log_event(self, user_id: int, task_id: Optional[int], action: str, text: str) -> None:
        at = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO task_events (user_id, task_id, action, text, at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (user_id, task_id, action, text, at),
            )
            await conn.commit()

    async def _delete_task_row(self, user_id: int, task_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "DELETE FROM tasks WHERE user_id = ? AND id = ?;",
                (user_id, task_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def complete_task(self, user_id: int, task_id: int) -> Optional[Task]:
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if not task:
            return None
        await self._log_event(user_id=user_id, task_id=task_id, action=TASK_ACTION_COMPLETED, text=task.text)
        ok = await self._delete_task_row(user_id, task_id)
        return task if ok else None

    async def restore_completed_task(self, user_id: int, event_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, task_id, text, at FROM task_events
                WHERE user_id = ? AND action = ? AND id = ?;
                """,
                (user_id, TASK_ACTION_COMPLETED, event_id),
            )
            row = await cur.fetchone()
            if not row:
                return False
            if row["task_id"]:
                existing = await self.get_task(user_id=user_id, task_id=row["task_id"])
                if existing:
                    return False
                cur = await conn.execute(
                    """
                    SELECT id FROM task_events
                    WHERE user_id = ? AND task_id = ? AND action = ?;
                    """,
                    (user_id, row["task_id"], TASK_ACTION_DELETED),
                )
                if await cur.fetchone():
                    return False
            original_task = await self.get_task(user_id=user_id, task_id=row["task_id"]) if row["task_id"] else None
            restore_text = row["text"]
            clean_title, priority = parse_priority(restore_text)
            now = self._now_iso()
            await conn.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, status, cooldown_until, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id, clean_title,
                    original_task.task_type if original_task else "regular",
                    original_task.difficulty if original_task else 5,
                    original_task.category if original_task else "",
                    original_task.deadline if original_task else None,
                    original_task.scheduled_time if original_task else None,
                    priority, "bang_suffix",
                    original_task.schedule_kind if original_task else None,
                    original_task.schedule_json if original_task else None,
                    getattr(original_task, "deadline_time", None) if original_task else None,
                    getattr(original_task, "scheduled_time_new", None) if original_task else None,
                    TASK_STATUS_BACKLOG, None,
                    getattr(original_task, "tags", "[]") if original_task else "[]",
                    now, now,
                ),
            )
            await conn.execute("DELETE FROM task_events WHERE id = ?;", (event_id,))
            await conn.commit()
            return True

    async def get_completed_task_by_index(self, user_id: int, index: int) -> Optional[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, task_id, text, at FROM task_events
                WHERE user_id = ? AND action = ? ORDER BY at DESC LIMIT 1 OFFSET ?;
                """,
                (user_id, TASK_ACTION_COMPLETED, index),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def restore_deleted_task(self, user_id: int, event_id: int) -> bool:
        payload = {}
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, task_id, text, at FROM task_events
                WHERE user_id = ? AND action = ? AND id = ?;
                """,
                (user_id, TASK_ACTION_DELETED, event_id),
            )
            row = await cur.fetchone()
            if not row:
                return False
            priority = 0
            priority_source = "bang_suffix"
            task_type, difficulty, category = "regular", 5, ""
            deadline = scheduled_time = schedule_kind = schedule_json = None
            if row["task_id"]:
                cur = await conn.execute(
                    """
                    SELECT payload FROM action_log
                    WHERE user_id = ? AND task_id = ? AND action = ?
                    ORDER BY at DESC LIMIT 1;
                    """,
                    (user_id, row["task_id"], ACTION_TASK_DELETED),
                )
                log_row = await cur.fetchone()
                if log_row and log_row["payload"]:
                    try:
                        payload = json.loads(log_row["payload"])
                        if "priority" in payload:
                            priority = payload["priority"]
                        task_type = payload.get("task_type", "regular")
                        difficulty = payload.get("difficulty", 5)
                        category = payload.get("category", "")
                        deadline = payload.get("deadline")
                        scheduled_time = payload.get("scheduled_time")
                        schedule_kind = payload.get("schedule_kind")
                        schedule_json = payload.get("schedule_json")
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
            if priority == 0:
                restore_text = row["text"]
                if " | Syy: " in restore_text:
                    restore_text = restore_text.split(" | Syy: ")[0]
                clean_title, priority = parse_priority(restore_text)
            else:
                restore_text = row["text"]
                if " | Syy: " in restore_text:
                    restore_text = restore_text.split(" | Syy: ")[0]
                clean_title, _ = parse_priority(restore_text)
            now = self._now_iso()
            tags_val = payload.get("tags", "[]") if isinstance(payload.get("tags"), str) else "[]"
            await conn.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, status, cooldown_until, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (user_id, clean_title, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline, scheduled_time, TASK_STATUS_BACKLOG, None, tags_val, now, now),
            )
            await conn.execute("DELETE FROM task_events WHERE id = ?;", (event_id,))
            await conn.commit()
            return True

    async def get_backlog_tasks(self, user_id: int, limit: int = 100) -> tuple[list[dict], list[dict]]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT e.id, e.task_id, e.text, e.at, t.deadline, t.schedule_kind, t.schedule_json, t.priority
                FROM task_events e
                LEFT JOIN tasks t ON e.task_id = t.id AND e.user_id = t.user_id
                WHERE e.user_id = ? AND e.action = ? ORDER BY e.at DESC LIMIT ?;
                """,
                (user_id, TASK_ACTION_COMPLETED, limit),
            )
            completed = [dict(r) for r in await cur.fetchall()]
            cur = await conn.execute(
                """
                SELECT e.id, e.task_id, e.text, e.at, t.deadline, t.schedule_kind, t.schedule_json, t.priority
                FROM task_events e
                LEFT JOIN tasks t ON e.task_id = t.id AND e.user_id = t.user_id
                WHERE e.user_id = ? AND e.action = ? ORDER BY e.at DESC LIMIT ?;
                """,
                (user_id, TASK_ACTION_DELETED, limit),
            )
            deleted = [dict(r) for r in await cur.fetchall()]
            return (completed, deleted)

    async def delete_task_with_log(self, user_id: int, task_id: int, reason: str = "") -> Optional[Task]:
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if not task:
            return None
        event_text = task.text
        if reason:
            event_text = f"{task.text} | Syy: {reason}"
        await self._log_event(user_id=user_id, task_id=task_id, action=TASK_ACTION_DELETED, text=event_text)
        ok = await self._delete_task_row(user_id, task_id)
        return task if ok else None

    async def set_deadline(self, task_id: int, user_id: int, deadline_utc: str) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                UPDATE tasks SET deadline = ?, deadline_time = ?, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (deadline_utc, deadline_utc, now, task_id, user_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def clear_deadline(self, task_id: int, user_id: int) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                UPDATE tasks SET deadline = NULL, deadline_time = NULL, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (now, task_id, user_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def set_schedule(self, task_id: int, user_id: int, schedule_kind: str, schedule_payload: dict) -> bool:
        now = self._now_iso()
        schedule_json_str = json.dumps(schedule_payload) if schedule_payload else None
        scheduled_time_new = schedule_payload.get("timestamp") if schedule_kind == "at_time" and schedule_payload else None
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                UPDATE tasks SET schedule_kind = ?, schedule_json = ?, scheduled_time_new = ?, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (schedule_kind, schedule_json_str, scheduled_time_new, now, task_id, user_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def clear_schedule(self, task_id: int, user_id: int) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                UPDATE tasks SET schedule_kind = NULL, schedule_json = NULL, scheduled_time_new = NULL, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (now, task_id, user_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def get_user_settings(self, user_id: int) -> dict:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT timezone, show_done_in_home, day_start_time, day_end_time, morning_routines_enabled, evening_routines_enabled,
                    morning_start_time, morning_end_time, evening_start_time, evening_end_time
                FROM user_settings WHERE user_id = ?;
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            if not row:
                now = self._now_iso()
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO user_settings (user_id, timezone, show_done_in_home, day_start_time, day_end_time, morning_routines_enabled, evening_routines_enabled, morning_start_time, morning_end_time, evening_start_time, evening_end_time, updated_at)
                    VALUES (?, 'Europe/Helsinki', 1, NULL, NULL, 0, 0, NULL, NULL, NULL, NULL, ?);
                    """,
                    (user_id, now),
                )
                await conn.commit()
                cur = await conn.execute(
                    """
                    SELECT timezone, show_done_in_home, day_start_time, day_end_time, morning_routines_enabled, evening_routines_enabled,
                        morning_start_time, morning_end_time, evening_start_time, evening_end_time
                    FROM user_settings WHERE user_id = ?;
                    """,
                    (user_id,),
                )
                row = await cur.fetchone()
            if row:
                d = dict(row)
                def _bool(v):
                    if v is None:
                        return False
                    return bool(int(v)) if isinstance(v, (int, float)) else bool(v)
                return {
                    "timezone": d.get("timezone") or "Europe/Helsinki",
                    "show_done_in_home": _bool(d.get("show_done_in_home")),
                    "day_start_time": d.get("day_start_time"),
                    "day_end_time": d.get("day_end_time"),
                    "morning_routines_enabled": _bool(d.get("morning_routines_enabled")),
                    "evening_routines_enabled": _bool(d.get("evening_routines_enabled")),
                    "morning_start_time": d.get("morning_start_time"),
                    "morning_end_time": d.get("morning_end_time"),
                    "evening_start_time": d.get("evening_start_time"),
                    "evening_end_time": d.get("evening_end_time"),
                }
            return {
                "timezone": "Europe/Helsinki",
                "show_done_in_home": True,
                "day_start_time": None,
                "day_end_time": None,
                "morning_routines_enabled": False,
                "evening_routines_enabled": False,
                "morning_start_time": None,
                "morning_end_time": None,
                "evening_start_time": None,
                "evening_end_time": None,
            }

    async def set_user_timezone(self, user_id: int, timezone: str) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO user_settings (user_id, timezone, show_done_in_home, day_start_time, day_end_time, morning_routines_enabled, evening_routines_enabled, morning_start_time, morning_end_time, evening_start_time, evening_end_time, updated_at)
                VALUES (?, ?, COALESCE((SELECT show_done_in_home FROM user_settings WHERE user_id = ?), 1), (SELECT day_start_time FROM user_settings WHERE user_id = ?), (SELECT day_end_time FROM user_settings WHERE user_id = ?), COALESCE((SELECT morning_routines_enabled FROM user_settings WHERE user_id = ?), 0), COALESCE((SELECT evening_routines_enabled FROM user_settings WHERE user_id = ?), 0), (SELECT morning_start_time FROM user_settings WHERE user_id = ?), (SELECT morning_end_time FROM user_settings WHERE user_id = ?), (SELECT evening_start_time FROM user_settings WHERE user_id = ?), (SELECT evening_end_time FROM user_settings WHERE user_id = ?), ?);
                """,
                (user_id, timezone, user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id, now),
            )
            await conn.commit()
            return True

    async def toggle_show_done_in_home(self, user_id: int) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT show_done_in_home FROM user_settings WHERE user_id = ?;",
                (user_id,),
            )
            row = await cur.fetchone()
            current_value = bool(row["show_done_in_home"]) if row else True
            new_value = not current_value
            await conn.execute(
                """
                INSERT OR REPLACE INTO user_settings (user_id, timezone, show_done_in_home, day_start_time, day_end_time, morning_routines_enabled, evening_routines_enabled, morning_start_time, morning_end_time, evening_start_time, evening_end_time, updated_at)
                VALUES (?, COALESCE((SELECT timezone FROM user_settings WHERE user_id = ?), 'Europe/Helsinki'), ?, (SELECT day_start_time FROM user_settings WHERE user_id = ?), (SELECT day_end_time FROM user_settings WHERE user_id = ?), COALESCE((SELECT morning_routines_enabled FROM user_settings WHERE user_id = ?), 0), COALESCE((SELECT evening_routines_enabled FROM user_settings WHERE user_id = ?), 0), (SELECT morning_start_time FROM user_settings WHERE user_id = ?), (SELECT morning_end_time FROM user_settings WHERE user_id = ?), (SELECT evening_start_time FROM user_settings WHERE user_id = ?), (SELECT evening_end_time FROM user_settings WHERE user_id = ?), ?);
                """,
                (user_id, user_id, new_value, user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id, now),
            )
            await conn.commit()
            return new_value

    async def set_user_time_window(self, user_id: int, day_start_time: Optional[str] = None, day_end_time: Optional[str] = None) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO user_settings (user_id, timezone, show_done_in_home, day_start_time, day_end_time, updated_at)
                VALUES (?, 'Europe/Helsinki', 1, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    day_start_time = COALESCE(?, day_start_time),
                    day_end_time = COALESCE(?, day_end_time),
                    updated_at = ?;
                """,
                (user_id, day_start_time, day_end_time, now, day_start_time, day_end_time, now),
            )
            await conn.commit()
            return True

    async def toggle_morning_routines_enabled(self, user_id: int) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT morning_routines_enabled FROM user_settings WHERE user_id = ?;",
                (user_id,),
            )
            row = await cur.fetchone()
            current = bool(row["morning_routines_enabled"]) if row and row["morning_routines_enabled"] is not None else False
            new_value = not current
            await conn.execute(
                """
                INSERT INTO user_settings (user_id, timezone, show_done_in_home, day_start_time, day_end_time, morning_routines_enabled, evening_routines_enabled, morning_start_time, morning_end_time, evening_start_time, evening_end_time, updated_at)
                VALUES (?, COALESCE((SELECT timezone FROM user_settings WHERE user_id = ?), 'Europe/Helsinki'), COALESCE((SELECT show_done_in_home FROM user_settings WHERE user_id = ?), 1), (SELECT day_start_time FROM user_settings WHERE user_id = ?), (SELECT day_end_time FROM user_settings WHERE user_id = ?), ?, COALESCE((SELECT evening_routines_enabled FROM user_settings WHERE user_id = ?), 0), (SELECT morning_start_time FROM user_settings WHERE user_id = ?), (SELECT morning_end_time FROM user_settings WHERE user_id = ?), (SELECT evening_start_time FROM user_settings WHERE user_id = ?), (SELECT evening_end_time FROM user_settings WHERE user_id = ?), ?)
                ON CONFLICT(user_id) DO UPDATE SET morning_routines_enabled = ?, updated_at = ?;
                """,
                (user_id, user_id, user_id, user_id, user_id, 1 if new_value else 0, user_id, user_id, user_id, user_id, user_id, now, 1 if new_value else 0, now),
            )
            await conn.commit()
            return new_value

    async def toggle_evening_routines_enabled(self, user_id: int) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT evening_routines_enabled FROM user_settings WHERE user_id = ?;",
                (user_id,),
            )
            row = await cur.fetchone()
            current = bool(row["evening_routines_enabled"]) if row and row["evening_routines_enabled"] is not None else False
            new_value = not current
            await conn.execute(
                """
                INSERT INTO user_settings (user_id, timezone, show_done_in_home, day_start_time, day_end_time, morning_routines_enabled, evening_routines_enabled, morning_start_time, morning_end_time, evening_start_time, evening_end_time, updated_at)
                VALUES (?, COALESCE((SELECT timezone FROM user_settings WHERE user_id = ?), 'Europe/Helsinki'), COALESCE((SELECT show_done_in_home FROM user_settings WHERE user_id = ?), 1), (SELECT day_start_time FROM user_settings WHERE user_id = ?), (SELECT day_end_time FROM user_settings WHERE user_id = ?), COALESCE((SELECT morning_routines_enabled FROM user_settings WHERE user_id = ?), 0), ?, (SELECT morning_start_time FROM user_settings WHERE user_id = ?), (SELECT morning_end_time FROM user_settings WHERE user_id = ?), (SELECT evening_start_time FROM user_settings WHERE user_id = ?), (SELECT evening_end_time FROM user_settings WHERE user_id = ?), ?)
                ON CONFLICT(user_id) DO UPDATE SET evening_routines_enabled = ?, updated_at = ?;
                """,
                (user_id, user_id, user_id, user_id, user_id, user_id, 1 if new_value else 0, user_id, user_id, user_id, user_id, now, 1 if new_value else 0, now),
            )
            await conn.commit()
            return new_value

    async def list_routine_tasks(self, user_id: int, routine_type: str) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, text, order_index FROM user_routine_tasks
                WHERE user_id = ? AND routine_type = ? ORDER BY order_index, id;
                """,
                (user_id, routine_type),
            )
            rows = await cur.fetchall()
            return [{"id": r["id"], "text": r["text"], "order_index": r["order_index"]} for r in rows]

    async def add_routine_task(self, user_id: int, routine_type: str, text: str) -> int:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM user_routine_tasks WHERE user_id = ? AND routine_type = ?;",
                (user_id, routine_type),
            )
            row = await cur.fetchone()
            idx = row[0] if row else 0
            cur = await conn.execute(
                """
                INSERT INTO user_routine_tasks (user_id, routine_type, order_index, text, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (user_id, routine_type, idx, text, now),
            )
            await conn.commit()
            return int(cur.lastrowid)

    async def update_routine_task(self, user_id: int, routine_task_id: int, new_text: str) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "UPDATE user_routine_tasks SET text = ? WHERE user_id = ? AND id = ?;",
                (new_text, user_id, routine_task_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def delete_routine_task(self, user_id: int, routine_task_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "DELETE FROM user_routine_tasks WHERE user_id = ? AND id = ?;",
                (user_id, routine_task_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def get_routine_completions_for_date(self, user_id: int, completion_date: str) -> set[int]:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                SELECT routine_task_id FROM user_routine_completions
                WHERE user_id = ? AND completion_date = ?;
                """,
                (user_id, completion_date),
            )
            rows = await cur.fetchall()
            return {r[0] for r in rows}

    async def set_routine_completion(self, user_id: int, routine_task_id: int, completion_date: str, done: bool) -> None:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            if done:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO user_routine_completions (user_id, routine_task_id, completion_date, done_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (user_id, routine_task_id, completion_date, now),
                )
            else:
                await conn.execute(
                    "DELETE FROM user_routine_completions WHERE user_id = ? AND routine_task_id = ? AND completion_date = ?;",
                    (user_id, routine_task_id, completion_date),
                )
            await conn.commit()

    async def get_today_date_user_tz(self, user_id: int) -> str:
        from app.clock import SystemClock
        settings = await self.get_user_settings(user_id)
        tz = settings.get("timezone", "Europe/Helsinki")
        now = SystemClock.now_user_tz(tz)
        return now.strftime("%Y-%m-%d")

    async def get_routine_windows(self, user_id: int) -> dict:
        settings = await self.get_user_settings(user_id)
        return {
            "morning_start": settings.get("morning_start_time") or DEFAULT_MORNING_START,
            "morning_end": settings.get("morning_end_time") or DEFAULT_MORNING_END,
            "evening_start": settings.get("evening_start_time") or DEFAULT_EVENING_START,
            "evening_end": settings.get("evening_end_time") or DEFAULT_EVENING_END,
            "timezone": settings.get("timezone") or "Europe/Helsinki",
        }

    async def set_morning_window(self, user_id: int, start: str, end: str) -> bool:
        start_t = parse_time_string(start)
        end_t = parse_time_string(end)
        if start_t is None or end_t is None:
            return False
        if start_t >= end_t:
            return False
        await self._ensure_user_settings_row(user_id)
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                "UPDATE user_settings SET morning_start_time = ?, morning_end_time = ?, updated_at = ? WHERE user_id = ?;",
                (start, end, now, user_id),
            )
            await conn.commit()
            return True

    async def set_evening_window(self, user_id: int, start: str, end: str) -> bool:
        start_t = parse_time_string(start)
        end_t = parse_time_string(end)
        if start_t is None or end_t is None:
            return False
        if start_t >= end_t:
            return False
        await self._ensure_user_settings_row(user_id)
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                "UPDATE user_settings SET evening_start_time = ?, evening_end_time = ?, updated_at = ? WHERE user_id = ?;",
                (start, end, now, user_id),
            )
            await conn.commit()
            return True

    async def _ensure_user_settings_row(self, user_id: int) -> None:
        await self.get_user_settings(user_id)

    async def is_in_morning_window(self, user_id: int) -> bool:
        from app.clock import SystemClock
        windows = await self.get_routine_windows(user_id)
        tz = windows.get("timezone", "Europe/Helsinki")
        now = SystemClock.now_user_tz(tz)
        return time_in_window(now.hour, now.minute, windows["morning_start"], windows["morning_end"])

    async def is_in_evening_window(self, user_id: int) -> bool:
        from app.clock import SystemClock
        windows = await self.get_routine_windows(user_id)
        tz = windows.get("timezone", "Europe/Helsinki")
        now = SystemClock.now_user_tz(tz)
        return time_in_window(now.hour, now.minute, windows["evening_start"], windows["evening_end"])

    async def ensure_default_routine_tasks(self, user_id: int, routine_type: str) -> None:
        tasks = await self.list_routine_tasks(user_id, routine_type)
        if tasks:
            return
        defaults = self.DEFAULT_MORNING_TASKS if routine_type == self.ROUTINE_TYPE_MORNING else self.DEFAULT_EVENING_TASKS
        for i, text in enumerate(defaults):
            await self.add_routine_task(user_id, routine_type, text)

    async def set_routine_quitted(self, user_id: int, routine_type: str, completion_date: str) -> None:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO user_routine_quitted (user_id, routine_type, completion_date, at)
                VALUES (?, ?, ?, ?);
                """,
                (user_id, routine_type, completion_date, now),
            )
            await conn.commit()

    async def get_routine_quitted(self, user_id: int, routine_type: str, completion_date: str) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "SELECT 1 FROM user_routine_quitted WHERE user_id = ? AND routine_type = ? AND completion_date = ?;",
                (user_id, routine_type, completion_date),
            )
            row = await cur.fetchone()
            return row is not None

    async def clear_task_events(self, user_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM task_events WHERE user_id = ?;", (user_id,))
            await conn.commit()

    async def clear_routine_completions_quitted(self, user_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM user_routine_completions WHERE user_id = ?;", (user_id,))
            await conn.execute("DELETE FROM user_routine_quitted WHERE user_id = ?;", (user_id,))
            await conn.commit()

    async def delete_user_tasks(self, user_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM tasks WHERE user_id = ?;", (user_id,))
            await conn.commit()
