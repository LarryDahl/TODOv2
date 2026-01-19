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
    created_at: str
    updated_at: str


class TasksRepo:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
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
                SELECT id, user_id, text, created_at, updated_at
                FROM tasks
                WHERE user_id = ?
                ORDER BY id ASC
                LIMIT ?;
                """,
                (user_id, limit),
            )
            rows = await cur.fetchall()
            return [Task(**dict(r)) for r in rows]

    async def add_task(self, user_id: int, text: str) -> int:
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO tasks (user_id, text, created_at, updated_at)
                VALUES (?, ?, ?, ?);
                """,
                (user_id, text, now, now),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_task(self, user_id: int, task_id: int) -> Optional[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, user_id, text, created_at, updated_at
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
