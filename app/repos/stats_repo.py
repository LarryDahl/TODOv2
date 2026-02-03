# -*- coding: utf-8 -*-
"""Action log, progress log, and statistics queries."""
from __future__ import annotations

import json
from typing import Optional

import aiosqlite

from app.constants import TASK_ACTION_COMPLETED, TASK_ACTION_DELETED
from app.repos.base import BaseRepo


class StatsRepo(BaseRepo):
    """action_log, progress_log; stats queries over task_events/tasks/projects."""

    async def init_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                task_id INTEGER,
                payload TEXT,
                at TEXT NOT NULL
            );
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_log_user_at ON action_log(user_id, at);"
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_action_log_action ON action_log(action);")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS progress_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                task_id INTEGER,
                amount REAL NOT NULL DEFAULT 1,
                at TEXT NOT NULL
            );
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_progress_log_user_at ON progress_log(user_id, at);"
        )

    async def log_action(
        self,
        user_id: int,
        action: str,
        task_id: Optional[int] = None,
        payload: Optional[dict] = None,
    ) -> None:
        try:
            payload_json = json.dumps(payload) if payload else None
            async with aiosqlite.connect(self._db_path) as conn:
                await conn.execute(
                    """
                    INSERT INTO action_log (user_id, action, task_id, payload, at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (user_id, action, task_id, payload_json, self._now_iso()),
                )
                await conn.commit()
        except Exception:
            pass

    async def insert_progress(
        self, user_id: int, source: str, task_id: Optional[int], amount: float = 1.0
    ) -> None:
        """Insert one progress_log row (e.g. task_completed)."""
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO progress_log (user_id, source, task_id, amount, at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (user_id, source, task_id, amount, self._now_iso()),
            )
            await conn.commit()

    async def get_statistics(self, user_id: int, days: int) -> dict:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ?
                AND datetime(at) >= datetime('now', '-' || ? || ' days');
                """,
                (user_id, TASK_ACTION_COMPLETED, days),
            )
            completed = (await cur.fetchone())["count"]
            cur = await conn.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ?
                AND datetime(at) >= datetime('now', '-' || ? || ' days');
                """,
                (user_id, TASK_ACTION_DELETED, days),
            )
            deleted = (await cur.fetchone())["count"]
            cur = await conn.execute(
                "SELECT COUNT(*) as count FROM tasks WHERE user_id = ?;",
                (user_id,),
            )
            active = (await cur.fetchone())["count"]
            return {
                "completed": completed,
                "deleted": deleted,
                "active": active,
                "days": days,
            }

    async def get_daily_progress(self, user_id: int) -> int:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ?
                AND date(at) = date('now');
                """,
                (user_id, TASK_ACTION_COMPLETED),
            )
            count = (await cur.fetchone())["count"]
            return min(count * 10, 100)

    async def get_all_time_stats(self, user_id: int) -> dict:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events WHERE user_id = ? AND action = ?;
                """,
                (user_id, TASK_ACTION_COMPLETED),
            )
            completed_count = (await cur.fetchone())["count"]
            cur = await conn.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events WHERE user_id = ? AND action = ?;
                """,
                (user_id, TASK_ACTION_DELETED),
            )
            deleted_count = (await cur.fetchone())["count"]
            cur = await conn.execute(
                "SELECT COUNT(*) as count FROM tasks WHERE user_id = ?;",
                (user_id,),
            )
            active_count = (await cur.fetchone())["count"]
            cur = await conn.execute(
                "SELECT COUNT(*) as count FROM projects WHERE status = 'cancelled';"
            )
            cancelled_count = (await cur.fetchone())["count"]
            cur = await conn.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ? AND date(at) = date('now');
                """,
                (user_id, TASK_ACTION_COMPLETED),
            )
            done_today = (await cur.fetchone())["count"]
            cur = await conn.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ?
                AND datetime(at) >= datetime('now', '-7 days');
                """,
                (user_id, TASK_ACTION_COMPLETED),
            )
            done_this_week = (await cur.fetchone())["count"]
            return {
                "completed_count": completed_count,
                "active_count": active_count,
                "deleted_count": deleted_count,
                "cancelled_count": cancelled_count,
                "done_today": done_today,
                "done_this_week": done_this_week,
            }

    async def clear_action_log(self, user_id: int) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM action_log WHERE user_id = ?;", (user_id,))
            await conn.commit()
