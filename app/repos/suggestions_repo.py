# -*- coding: utf-8 -*-
"""Suggestion slots and suggestion log (accept/snooze/ignore)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from app.repos.base import BaseRepo


class SuggestionsRepo(BaseRepo):
    """user_suggestion_slots and suggestion_log."""

    async def init_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS suggestion_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                at TEXT NOT NULL
            );
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_suggestion_log_user_event ON suggestion_log(user_id, event_id);"
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_suggestion_slots (
                user_id INTEGER NOT NULL,
                slot_index INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, slot_index),
                CHECK (slot_index >= 0 AND slot_index <= 8)
            );
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_suggestion_slots_user ON user_suggestion_slots(user_id);"
        )
        cur = await db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_suggestion_slots';"
        )
        row = await cur.fetchone()
        if row and row[0] and "slot_index <= 8" not in row[0]:
            await db.execute("DROP TABLE user_suggestion_slots;")
            await db.execute(
                """
                CREATE TABLE user_suggestion_slots (
                    user_id INTEGER NOT NULL,
                    slot_index INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, slot_index),
                    CHECK (slot_index >= 0 AND slot_index <= 8)
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_suggestion_slots_user ON user_suggestion_slots(user_id);"
            )

    async def get_suggestion_slots(self, user_id: int) -> list[Optional[int]]:
        """Return 9 task_ids (or None for empty slot). Order: slot 0..8."""
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT slot_index, task_id FROM user_suggestion_slots WHERE user_id = ? ORDER BY slot_index;",
                (user_id,),
            )
            rows = await cur.fetchall()
        slot_map = {r["slot_index"]: r["task_id"] for r in rows}
        return [slot_map.get(i) for i in range(9)]

    async def set_suggestion_slot(
        self, user_id: int, slot_index: int, task_id: Optional[int], now: str
    ) -> None:
        """Set one slot. task_id=None to clear."""
        async with aiosqlite.connect(self._db_path) as conn:
            if task_id is None:
                await conn.execute(
                    "DELETE FROM user_suggestion_slots WHERE user_id = ? AND slot_index = ?;",
                    (user_id, slot_index),
                )
            else:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO user_suggestion_slots (user_id, slot_index, task_id, updated_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (user_id, slot_index, task_id, now),
                )
            await conn.commit()

    async def log_suggestion_action(self, user_id: int, event_id: int, action: str) -> None:
        """Log suggestion action: 'accepted' | 'snoozed' | 'ignored'."""
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT INTO suggestion_log (user_id, event_id, action, at)
                VALUES (?, ?, ?, ?);
                """,
                (user_id, event_id, action, self._now_iso()),
            )
            await conn.commit()

    async def get_snoozed_event_ids(self, user_id: int, days: int = 7) -> set[int]:
        """Event IDs snoozed within the last N days."""
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                SELECT DISTINCT event_id
                FROM suggestion_log
                WHERE user_id = ? AND action = 'snoozed' AND at > ?;
                """,
                (user_id, cutoff),
            )
            return {row[0] for row in await cur.fetchall()}

    async def clear_suggestion_log(self, user_id: int) -> None:
        """Delete all suggestion_log rows for user (for reset_stats)."""
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute("DELETE FROM suggestion_log WHERE user_id = ?;", (user_id,))
            await conn.commit()

    async def clear_user_slots(self, user_id: int) -> None:
        """Delete all user_suggestion_slots for user (for reset_all_data)."""
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                "DELETE FROM user_suggestion_slots WHERE user_id = ?;", (user_id,)
            )
            await conn.commit()
