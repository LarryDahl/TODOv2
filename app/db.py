from __future__ import annotations

import json
import aiosqlite
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.priority import parse_priority


@dataclass(frozen=True)
class Task:
    id: int
    user_id: int
    text: str
    task_type: str  # 'deadline', 'scheduled', 'regular'
    difficulty: int  # percentage (1, 5, 10, or custom)
    category: str  # 'liikunta', 'arki', 'opiskelu', 'suhteet', 'muu', ''
    deadline: Optional[str]  # ISO datetime for deadline (latest-by), UTC
    scheduled_time: Optional[str]  # ISO datetime for scheduled tasks (deprecated, use schedule_kind/schedule_json)
    priority: int  # 0 to 5, derived from trailing '!' in title
    priority_source: str  # 'bang_suffix' or future AI-based sources
    schedule_kind: Optional[str]  # 'none' | 'at_time' | 'time_range' | 'all_day' | None
    schedule_json: Optional[str]  # JSON string with schedule details
    created_at: str
    updated_at: str


class TasksRepo:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            # Check if new columns exist, if not add them
            cursor = await db.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in await cursor.fetchall()]
            
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            
            # Add new columns if they don't exist (migration)
            if 'task_type' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'regular';")
            if 'difficulty' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN difficulty INTEGER NOT NULL DEFAULT 5;")
            if 'category' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN category TEXT NOT NULL DEFAULT '';")
            if 'deadline' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN deadline TEXT;")
            if 'scheduled_time' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN scheduled_time TEXT;")
            if 'priority' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;")
            if 'priority_source' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN priority_source TEXT NOT NULL DEFAULT 'bang_suffix';")
            if 'schedule_kind' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN schedule_kind TEXT;")
            if 'schedule_json' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN schedule_json TEXT;")
            
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);")

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id INTEGER,
                    action TEXT NOT NULL,         -- 'completed' | 'deleted'
                    text TEXT NOT NULL,
                    at TEXT NOT NULL
                );
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_task_events_user_id ON task_events(user_id);")
            await db.commit()

    async def list_tasks(self, user_id: int, limit: int = 50) -> list[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, created_at, updated_at
                FROM tasks
                WHERE user_id = ?
                ORDER BY priority DESC, 
                         CASE WHEN deadline IS NULL THEN 1 ELSE 0 END,
                         deadline ASC,
                         created_at ASC
                LIMIT ?;
                """,
                (user_id, limit),
            )
            rows = await cur.fetchall()
            return [Task(**dict(r)) for r in rows]
    
    async def list_completed_tasks(self, user_id: int, limit: int = 3) -> list[dict]:
        """Get most recently completed tasks"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, task_id, text, at
                FROM task_events
                WHERE user_id = ? AND action = 'completed'
                ORDER BY at DESC
                LIMIT ?;
                """,
                (user_id, limit),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
    
    async def list_done_tasks(self, user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
        """
        List completed tasks with deadline and schedule metadata.
        
        Note: Since tasks are deleted on completion, deadline/schedule info is not preserved.
        Returns list of dicts with keys: job_id, title, due_at, schedule_kind, schedule_json, status, updated_at
        
        Args:
            user_id: User ID
            limit: Maximum number of tasks to return (default 50)
            offset: Number of tasks to skip (default 0)
        
        Returns:
            List of dicts with task information
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Tasks are deleted on completion, so we can only get data from events
            # deadline/schedule info is lost unless stored in events (future enhancement)
            cur = await db.execute(
                """
                SELECT 
                    e.id as job_id,
                    e.task_id,
                    e.text as title,
                    NULL as due_at,
                    NULL as schedule_kind,
                    NULL as schedule_json,
                    'done' as status,
                    e.at as updated_at
                FROM task_events e
                WHERE e.user_id = ? AND e.action = 'completed'
                ORDER BY e.at DESC
                LIMIT ? OFFSET ?;
                """,
                (user_id, limit, offset),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
    
    async def list_deleted_tasks(self, user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
        """
        List deleted (cancelled) tasks with deadline and schedule metadata.
        
        Note: Since tasks are deleted, deadline/schedule info is not preserved.
        Returns list of dicts with keys: job_id, title, due_at, schedule_kind, schedule_json, status, updated_at
        
        Args:
            user_id: User ID
            limit: Maximum number of tasks to return (default 50)
            offset: Number of tasks to skip (default 0)
        
        Returns:
            List of dicts with task information
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT 
                    e.id as job_id,
                    e.task_id,
                    e.text as title,
                    NULL as due_at,
                    NULL as schedule_kind,
                    NULL as schedule_json,
                    'cancelled' as status,
                    e.at as updated_at
                FROM task_events e
                WHERE e.user_id = ? AND e.action = 'deleted'
                ORDER BY e.at DESC
                LIMIT ? OFFSET ?;
                """,
                (user_id, limit, offset),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def add_task(
        self, 
        user_id: int, 
        text: str, 
        task_type: str = 'regular',
        difficulty: int = 5,
        category: str = '',
        deadline: Optional[str] = None,
        scheduled_time: Optional[str] = None
    ) -> int:
        # Parse priority from trailing exclamation marks
        clean_title, priority = parse_priority(text)
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (user_id, clean_title, task_type, difficulty, category, deadline, scheduled_time, priority, 'bang_suffix', None, None, now, now),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_task(self, user_id: int, task_id: int) -> Optional[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, created_at, updated_at
                FROM tasks
                WHERE user_id = ? AND id = ?;
                """,
                (user_id, task_id),
            )
            row = await cur.fetchone()
            return Task(**dict(row)) if row else None

    async def update_task(self, user_id: int, task_id: int, new_text: str) -> bool:
        # Re-parse priority from text (always recompute, never reuse old priority)
        clean_title, priority = parse_priority(new_text)
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE tasks
                SET text = ?, priority = ?, priority_source = ?, updated_at = ?
                WHERE user_id = ? AND id = ?;
                """,
                (clean_title, priority, 'bang_suffix', now, user_id, task_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def _log_event(self, user_id: int, task_id: Optional[int], action: str, text: str) -> None:
        at = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO task_events (user_id, task_id, action, text, at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (user_id, task_id, action, text, at),
            )
            await db.commit()

    async def complete_task(self, user_id: int, task_id: int) -> bool:
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if not task:
            return False

        await self._log_event(user_id=user_id, task_id=task_id, action="completed", text=task.text)

        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                "DELETE FROM tasks WHERE user_id = ? AND id = ?;",
                (user_id, task_id),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def restore_completed_task(self, user_id: int, event_id: int) -> bool:
        """Restore a completed task back to the task list using event id"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Get the completed task event
            cur = await db.execute(
                """
                SELECT id, task_id, text, at
                FROM task_events
                WHERE user_id = ? AND action = 'completed' AND id = ?;
                """,
                (user_id, event_id),
            )
            row = await cur.fetchone()
            if not row:
                return False
            
            # Try to get original task data if task_id exists (might be None if task was already deleted)
            original_task = None
            if row['task_id']:
                original_task = await self.get_task(user_id=user_id, task_id=row['task_id'])
            
            # Add task back with original data or defaults
            # Re-parse priority from text when restoring
            restore_text = row['text']
            clean_title, priority = parse_priority(restore_text)
            now = self._now_iso()
            cur = await db.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id,
                    clean_title,
                    original_task.task_type if original_task else 'regular',
                    original_task.difficulty if original_task else 5,
                    original_task.category if original_task else '',
                    original_task.deadline if original_task else None,
                    original_task.scheduled_time if original_task else None,
                    priority,
                    'bang_suffix',
                    original_task.schedule_kind if original_task else None,
                    original_task.schedule_json if original_task else None,
                    now,
                    now
                ),
            )
            
            # Remove the completed event so it disappears from completed tasks list
            await db.execute(
                "DELETE FROM task_events WHERE id = ?;",
                (event_id,),
            )
            
            await db.commit()
            return True
    
    async def get_completed_task_by_index(self, user_id: int, index: int) -> Optional[dict]:
        """Get completed task by index (0 = most recent)"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, task_id, text, at
                FROM task_events
                WHERE user_id = ? AND action = 'completed'
                ORDER BY at DESC
                LIMIT 1 OFFSET ?;
                """,
                (user_id, index),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def restore_deleted_task(self, user_id: int, event_id: int) -> bool:
        """Restore a deleted task back to the task list using event id"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Get the deleted task event
            cur = await db.execute(
                """
                SELECT id, task_id, text, at
                FROM task_events
                WHERE user_id = ? AND action = 'deleted' AND id = ?;
                """,
                (user_id, event_id),
            )
            row = await cur.fetchone()
            if not row:
                return False
            
            # Try to get original task data if task_id exists (might be None if task was already deleted)
            original_task = None
            if row['task_id']:
                # Task is already deleted, so we can't get it from tasks table
                # We'll restore with defaults and user can edit if needed
                pass
            
            # Add task back with original data or defaults
            # Re-parse priority from text when restoring
            restore_text = row['text']
            clean_title, priority = parse_priority(restore_text)
            now = self._now_iso()
            cur = await db.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id,
                    clean_title,
                    original_task.task_type if original_task else 'regular',
                    original_task.difficulty if original_task else 5,
                    original_task.category if original_task else '',
                    original_task.deadline if original_task else None,
                    original_task.scheduled_time if original_task else None,
                    priority,
                    'bang_suffix',
                    original_task.schedule_kind if original_task else None,
                    original_task.schedule_json if original_task else None,
                    now,
                    now
                ),
            )
            
            # Remove the deleted event so it disappears from deleted tasks list
            await db.execute(
                "DELETE FROM task_events WHERE id = ?;",
                (event_id,),
            )
            
            await db.commit()
            return True
    
    async def get_statistics(self, user_id: int, days: int) -> dict:
        """Get statistics for the last N days"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Get completed tasks count
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = 'completed' 
                AND datetime(at) >= datetime('now', '-' || ? || ' days');
                """,
                (user_id, days),
            )
            completed = (await cur.fetchone())['count']
            
            # Get deleted tasks count
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = 'deleted'
                AND datetime(at) >= datetime('now', '-' || ? || ' days');
                """,
                (user_id, days),
            )
            deleted = (await cur.fetchone())['count']
            
            # Get current active tasks
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM tasks
                WHERE user_id = ?;
                """,
                (user_id,),
            )
            active = (await cur.fetchone())['count']
            
            return {
                'completed': completed,
                'deleted': deleted,
                'active': active,
                'days': days
            }
    
    async def get_daily_progress(self, user_id: int) -> int:
        """Get today's progress: 1 task = 10%, max 100% (10 tasks)"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Count completed tasks today (since midnight UTC)
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = 'completed'
                AND date(at) = date('now');
                """,
                (user_id,),
            )
            count = (await cur.fetchone())['count']
            # 1 task = 10%, max 100% (10 tasks)
            progress = min(count * 10, 100)
            return progress
    
    async def reset_all_data(self, user_id: int) -> None:
        """Reset all data for a user"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM tasks WHERE user_id = ?;", (user_id,))
            await db.execute("DELETE FROM task_events WHERE user_id = ?;", (user_id,))
            await db.commit()

    async def delete_task_with_log(self, user_id: int, task_id: int) -> bool:
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if not task:
            return False

        await self._log_event(user_id=user_id, task_id=task_id, action="deleted", text=task.text)

        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                "DELETE FROM tasks WHERE user_id = ? AND id = ?;",
                (user_id, task_id),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def set_deadline(self, task_id: int, user_id: int, deadline_utc: str) -> bool:
        """
        Set deadline for a task.
        
        Args:
            task_id: Task ID
            user_id: User ID (for security check)
            deadline_utc: ISO 8601 datetime string in UTC
        
        Returns:
            True if task was updated, False if not found or unauthorized
        """
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE tasks
                SET deadline = ?, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (deadline_utc, now, task_id, user_id),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def clear_deadline(self, task_id: int, user_id: int) -> bool:
        """
        Clear deadline for a task.
        
        Args:
            task_id: Task ID
            user_id: User ID (for security check)
        
        Returns:
            True if task was updated, False if not found or unauthorized
        """
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE tasks
                SET deadline = NULL, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (now, task_id, user_id),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def set_schedule(self, task_id: int, user_id: int, schedule_kind: str, schedule_payload: dict) -> bool:
        """
        Set schedule window for a task.
        
        Args:
            task_id: Task ID
            user_id: User ID (for security check)
            schedule_kind: One of 'none', 'at_time', 'time_range', 'all_day'
            schedule_payload: Dict with schedule details:
                - 'at_time': {'timestamp': 'ISO datetime'}
                - 'time_range': {'start_time': 'ISO datetime', 'end_time': 'ISO datetime'}
                - 'all_day': {'date': 'YYYY-MM-DD'}
                - 'none': {}
        
        Returns:
            True if task was updated, False if not found or unauthorized
        """
        now = self._now_iso()
        schedule_json_str = json.dumps(schedule_payload) if schedule_payload else None
        
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE tasks
                SET schedule_kind = ?, schedule_json = ?, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (schedule_kind, schedule_json_str, now, task_id, user_id),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def clear_schedule(self, task_id: int, user_id: int) -> bool:
        """
        Clear schedule window for a task.
        
        Args:
            task_id: Task ID
            user_id: User ID (for security check)
        
        Returns:
            True if task was updated, False if not found or unauthorized
        """
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE tasks
                SET schedule_kind = NULL, schedule_json = NULL, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (now, task_id, user_id),
            )
            await db.commit()
            return cur.rowcount > 0
