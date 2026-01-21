from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class Task:
    id: int
    user_id: int
    text: str
    task_type: str  # 'deadline', 'scheduled', 'regular'
    difficulty: int  # percentage (1, 5, 10, or custom)
    category: str  # 'liikunta', 'arki', 'opiskelu', 'suhteet', 'muu', ''
    deadline: Optional[str]  # ISO datetime for deadline tasks
    scheduled_time: Optional[str]  # ISO datetime for scheduled tasks
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
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, created_at, updated_at
                FROM tasks
                WHERE user_id = ?
                ORDER BY id ASC
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
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (user_id, text, task_type, difficulty, category, deadline, scheduled_time, now, now),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_task(self, user_id: int, task_id: int) -> Optional[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, created_at, updated_at
                FROM tasks
                WHERE user_id = ? AND id = ?;
                """,
                (user_id, task_id),
            )
            row = await cur.fetchone()
            return Task(**dict(row)) if row else None

    async def update_task(self, user_id: int, task_id: int, new_text: str) -> bool:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE tasks
                SET text = ?, updated_at = ?
                WHERE user_id = ? AND id = ?;
                """,
                (new_text, now, user_id, task_id),
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
            now = self._now_iso()
            cur = await db.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id,
                    row['text'],
                    original_task.task_type if original_task else 'regular',
                    original_task.difficulty if original_task else 5,
                    original_task.category if original_task else '',
                    original_task.deadline if original_task else None,
                    original_task.scheduled_time if original_task else None,
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
