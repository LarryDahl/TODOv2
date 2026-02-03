# -*- coding: utf-8 -*-
"""Projects and project steps (backlog projects with ordered steps)."""
from __future__ import annotations

from typing import Optional

import aiosqlite

from app.repos.base import BaseRepo


class ProjectsRepo(BaseRepo):
    """projects and project_steps tables."""

    async def init_tables(self, db: aiosqlite.Connection) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                current_step_order INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            """
        )
        cursor = await db.execute("PRAGMA table_info(projects)")
        project_columns = [row[1] for row in await cursor.fetchall()]
        if "completed_at" not in project_columns:
            await db.execute("ALTER TABLE projects ADD COLUMN completed_at TEXT;")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS project_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                order_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                done_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_steps_project_id ON project_steps(project_id);"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_steps_project_status ON project_steps(project_id, status);"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_steps_project_order ON project_steps(project_id, order_index);"
        )

    async def create_project(self, title: str, now: str) -> int:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                INSERT INTO projects (title, status, current_step_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (title, "active", None, now, now),
            )
            await conn.commit()
            return int(cur.lastrowid)

    async def add_project_steps(
        self, project_id: int, list_of_texts: list[str], now: str
    ) -> None:
        async with aiosqlite.connect(self._db_path) as conn:
            for idx, text in enumerate(list_of_texts, start=1):
                await conn.execute(
                    """
                    INSERT INTO project_steps (project_id, order_index, text, status, created_at, done_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (project_id, idx, text, "pending", now, None),
                )
            await conn.commit()

    async def get_active_project_steps(self) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT
                    ps.id, ps.project_id, ps.order_index, ps.text, ps.status,
                    ps.created_at, ps.done_at,
                    p.title as project_title,
                    (SELECT COUNT(*) FROM project_steps ps2 WHERE ps2.project_id = ps.project_id) as total_steps
                FROM project_steps ps
                JOIN projects p ON ps.project_id = p.id
                WHERE ps.status = ? AND p.status != 'cancelled';
                """,
                ("active",),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def get_project_step(self, step_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, project_id, order_index, text, status, created_at, done_at
                FROM project_steps WHERE id = ?;
                """,
                (step_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def mark_project_step_completed(self, step_id: int, done_at: str) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                UPDATE project_steps SET status = ?, done_at = ? WHERE id = ?;
                """,
                ("completed", done_at, step_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def get_next_pending_step(
        self, project_id: int, after_order_index: int
    ) -> Optional[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, project_id, order_index, text, status, created_at, done_at
                FROM project_steps
                WHERE project_id = ? AND status = ? AND order_index > ?
                ORDER BY order_index ASC LIMIT 1;
                """,
                (project_id, "pending", after_order_index),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def set_project_step_active(self, step_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "UPDATE project_steps SET status = ? WHERE id = ?;",
                ("active", step_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def update_project_current_step(
        self, project_id: int, current_step_order: Optional[int], now: str
    ) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                UPDATE projects SET current_step_order = ?, updated_at = ? WHERE id = ?;
                """,
                (current_step_order, now, project_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def activate_first_project_step(self, project_id: int, now: str) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id FROM project_steps WHERE project_id = ? AND order_index = 1;
                """,
                (project_id,),
            )
            row = await cur.fetchone()
            if not row:
                return False
            first_step_id = row["id"]
            cur = await conn.execute(
                "UPDATE project_steps SET status = ? WHERE id = ?;",
                ("active", first_step_id),
            )
            if cur.rowcount == 0:
                return False
            cur = await conn.execute(
                """
                UPDATE projects SET current_step_order = ?, updated_at = ? WHERE id = ?;
                """,
                (1, now, project_id),
            )
            if cur.rowcount == 0:
                return False
            await conn.commit()
            return True

    async def mark_project_completed(self, project_id: int, now: str) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                UPDATE projects SET status = ?, current_step_order = NULL, updated_at = ?
                WHERE id = ?;
                """,
                ("completed", now, project_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def advance_project_step(self, step_id: int, now: str) -> dict:
        step = await self.get_project_step(step_id)
        if not step:
            raise ValueError(f"Step {step_id} not found")
        if step["status"] != "active":
            return {
                "action": "noop",
                "project_id": step["project_id"],
                "completed_step_id": step_id,
                "new_active_step_id": None,
            }
        project_id = step["project_id"]
        current_order_index = step["order_index"]
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                UPDATE project_steps SET status = ?, done_at = ? WHERE id = ?;
                """,
                ("completed", now, step_id),
            )
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, project_id, order_index, text, status, created_at, done_at
                FROM project_steps
                WHERE project_id = ? AND status = ? AND order_index > ?
                ORDER BY order_index ASC LIMIT 1;
                """,
                (project_id, "pending", current_order_index),
            )
            next_step_row = await cur.fetchone()
            if next_step_row:
                next_step = dict(next_step_row)
                next_step_id = next_step["id"]
                next_order_index = next_step["order_index"]
                await conn.execute(
                    "UPDATE project_steps SET status = ? WHERE id = ?;",
                    ("active", next_step_id),
                )
                await conn.execute(
                    """
                    UPDATE projects SET current_step_order = ?, updated_at = ? WHERE id = ?;
                    """,
                    (next_order_index, now, project_id),
                )
                await conn.commit()
                return {
                    "action": "advanced",
                    "project_id": project_id,
                    "completed_step_id": step_id,
                    "new_active_step_id": next_step_id,
                }
            else:
                await conn.execute(
                    """
                    UPDATE projects SET status = ?, current_step_order = NULL, updated_at = ?, completed_at = ?
                    WHERE id = ?;
                    """,
                    ("completed", now, now, project_id),
                )
                await conn.commit()
                return {
                    "action": "completed_project",
                    "project_id": project_id,
                    "completed_step_id": step_id,
                    "new_active_step_id": None,
                }

    async def get_project(self, project_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, title, status, current_step_order, created_at, updated_at, completed_at
                FROM projects WHERE id = ?;
                """,
                (project_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_all_projects(self) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, title, status, current_step_order, created_at, updated_at, completed_at
                FROM projects ORDER BY created_at DESC;
                """
            )
            return [dict(r) for r in await cur.fetchall()]

    async def get_project_steps(self, project_id: int) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, project_id, order_index, text, status, created_at, done_at
                FROM project_steps WHERE project_id = ? ORDER BY order_index ASC;
                """,
                (project_id,),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def update_project_step_text(self, step_id: int, new_text: str) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "UPDATE project_steps SET text = ? WHERE id = ?;",
                (new_text, step_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def update_project_step_status(self, step_id: int, status: str) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "UPDATE project_steps SET status = ? WHERE id = ?;",
                (status, step_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def move_project_step(self, step_id: int, direction: str) -> bool:
        step = await self.get_project_step(step_id)
        if not step:
            return False
        project_id = step["project_id"]
        current_order = step["order_index"]
        if direction == "up":
            new_order = current_order - 1
            if new_order < 1:
                return False
        elif direction == "down":
            new_order = current_order + 1
        else:
            return False
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id FROM project_steps WHERE project_id = ? AND order_index = ?;
                """,
                (project_id, new_order),
            )
            other_step = await cur.fetchone()
            if not other_step and direction == "down":
                cur = await conn.execute(
                    """
                    SELECT MAX(order_index) as max_order FROM project_steps WHERE project_id = ?;
                    """,
                    (project_id,),
                )
                max_row = await cur.fetchone()
                max_order = max_row["max_order"] if max_row else 0
                if new_order > max_order:
                    return False
            await conn.execute("BEGIN TRANSACTION")
            try:
                await conn.execute(
                    "UPDATE project_steps SET order_index = ? WHERE id = ?;",
                    (-step_id, step_id),
                )
                if other_step:
                    await conn.execute(
                        "UPDATE project_steps SET order_index = ? WHERE id = ?;",
                        (current_order, other_step["id"]),
                    )
                await conn.execute(
                    "UPDATE project_steps SET order_index = ? WHERE id = ?;",
                    (new_order, step_id),
                )
                await conn.commit()
                return True
            except Exception:
                await conn.rollback()
                return False

    async def add_step_to_project(self, project_id: int, step_text: str) -> int:
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT MAX(order_index) as max_order FROM project_steps WHERE project_id = ?;
                """,
                (project_id,),
            )
            row = await cur.fetchone()
            max_order = row["max_order"] if row and row["max_order"] else 0
            new_order = max_order + 1
            now = self._now_iso()
            cur = await conn.execute(
                """
                INSERT INTO project_steps (project_id, order_index, text, status, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (project_id, new_order, step_text, "pending", now),
            )
            await conn.commit()
            return int(cur.lastrowid) if cur.lastrowid else 0

    async def delete_project_step(self, step_id: int) -> bool:
        step = await self.get_project_step(step_id)
        if not step:
            return False
        if step["status"] == "active":
            now = self._now_iso()
            try:
                await self.advance_project_step(step_id=step_id, now=now)
            except ValueError:
                pass
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "DELETE FROM project_steps WHERE id = ?;",
                (step_id,),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def delete_all_project_steps(self, project_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                "DELETE FROM project_steps WHERE project_id = ?;",
                (project_id,),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def cancel_project(self, project_id: int, now: str) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            cur = await conn.execute(
                """
                UPDATE projects SET status = ?, updated_at = ? WHERE id = ?;
                """,
                ("cancelled", now, project_id),
            )
            await conn.commit()
            return cur.rowcount > 0

    async def toggle_project_step(self, step_id: int, now: str) -> dict:
        step = await self.get_project_step(step_id)
        if not step:
            raise ValueError(f"Step {step_id} not found")
        project_id = step["project_id"]
        order_index = step["order_index"]
        status = step["status"]
        if status == "completed":
            async with aiosqlite.connect(self._db_path) as conn:
                await conn.execute(
                    """
                    UPDATE project_steps SET status = ?, done_at = ? WHERE id = ?;
                    """,
                    ("active", None, step_id),
                )
                await conn.execute(
                    """
                    UPDATE projects SET status = ?, current_step_order = ?, updated_at = ?, completed_at = ?
                    WHERE id = ? AND status = ?;
                    """,
                    ("active", order_index, now, None, project_id, "completed"),
                )
                await conn.commit()
            return {"action": "uncompleted", "project_id": project_id, "step_id": step_id}
        if status == "active":
            return await self.advance_project_step(step_id=step_id, now=now)
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                UPDATE project_steps SET status = ?, done_at = ? WHERE id = ?;
                """,
                ("completed", now, step_id),
            )
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """
                SELECT id, order_index FROM project_steps
                WHERE project_id = ? AND status = ? AND order_index > ?
                ORDER BY order_index ASC LIMIT 1;
                """,
                (project_id, "pending", order_index),
            )
            next_row = await cur.fetchone()
            if next_row:
                await conn.execute(
                    "UPDATE project_steps SET status = ? WHERE id = ?;",
                    ("active", next_row["id"]),
                )
                await conn.execute(
                    """
                    UPDATE projects SET current_step_order = ?, updated_at = ? WHERE id = ?;
                    """,
                    (next_row["order_index"], now, project_id),
                )
            else:
                await conn.execute(
                    """
                    UPDATE project_steps SET status = ?, done_at = ? WHERE project_id = ? AND status = ?;
                    """,
                    ("completed", now, project_id, "active"),
                )
                await conn.execute(
                    """
                    UPDATE projects SET status = ?, current_step_order = NULL, updated_at = ?, completed_at = ?
                    WHERE id = ?;
                    """,
                    ("completed", now, now, project_id),
                )
            await conn.commit()
        return {"action": "completed", "project_id": project_id, "step_id": step_id}

    async def delete_project(self, project_id: int) -> bool:
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                "DELETE FROM project_steps WHERE project_id = ?;",
                (project_id,),
            )
            cur = await conn.execute(
                "DELETE FROM projects WHERE id = ?;",
                (project_id,),
            )
            await conn.commit()
            return cur.rowcount > 0
