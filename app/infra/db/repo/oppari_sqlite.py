from __future__ import annotations

import json
from typing import Optional, Sequence, Dict, Any

from app.domain.common.time import from_iso
from app.domain.oppari.models import WorklogEntry
from app.domain.oppari.ports import WorklogRepository
from app.infra.db.connection import Database


class OppariSqliteRepo(WorklogRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def ensure_user(self, user_id: int, now_iso: str) -> None:
        row = await self._db.fetchone("SELECT user_id FROM users WHERE user_id = ?;", (user_id,))
        if row:
            await self._db.execute("UPDATE users SET last_seen_at = ? WHERE user_id = ?;", (now_iso, user_id))
            return
        await self._db.execute(
            "INSERT INTO users(user_id, created_at, last_seen_at) VALUES (?, ?, ?);",
            (user_id, now_iso, now_iso),
        )

    async def ensure_agent_registered(self, agent_id: str, name: str, category: str, now_iso: str) -> None:
        row = await self._db.fetchone("SELECT agent_id FROM agents WHERE agent_id = ?;", (agent_id,))
        if row:
            return
        await self._db.execute(
            "INSERT INTO agents(agent_id, name, category, is_active, created_at) VALUES (?, ?, ?, 1, ?);",
            (agent_id, name, category, now_iso),
        )

    async def get_open_entry(self, user_id: int, agent_id: str) -> Optional[WorklogEntry]:
        row = await self._db.fetchone(
            """
            SELECT *
            FROM worklog_entries
            WHERE user_id = ? AND agent_id = ? AND end_at IS NULL
            ORDER BY start_at DESC
            LIMIT 1;
            """,
            (user_id, agent_id),
        )
        return self._row_to_entry(row) if row else None

    async def start_entry(
        self,
        entry_id: str,
        user_id: int,
        agent_id: str,
        start_at_iso: str,
        description: str,
        created_at_iso: str,
        project: Optional[str],
        category: Optional[str],
        metadata: Dict[str, Any],
    ) -> None:
        meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        await self._db.execute(
            """
            INSERT INTO worklog_entries(
              entry_id, user_id, agent_id, project, category,
              start_at, end_at, break_minutes, description,
              metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, ?, ?);
            """,
            (entry_id, user_id, agent_id, project, category, start_at_iso, description, meta_json, created_at_iso, created_at_iso),
        )

    async def end_entry(
        self,
        entry_id: str,
        end_at_iso: str,
        break_minutes: int,
        description: str,
        updated_at_iso: str,
        metadata: Dict[str, Any],
    ) -> None:
        meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        await self._db.execute(
            """
            UPDATE worklog_entries
            SET end_at = ?,
                break_minutes = ?,
                description = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE entry_id = ?;
            """,
            (end_at_iso, break_minutes, description, meta_json, updated_at_iso, entry_id),
        )

    async def list_recent(self, user_id: int, agent_id: str, limit: int) -> Sequence[WorklogEntry]:
        rows = await self._db.fetchall(
            """
            SELECT *
            FROM worklog_entries
            WHERE user_id = ? AND agent_id = ?
            ORDER BY start_at DESC
            LIMIT ?;
            """,
            (user_id, agent_id, limit),
        )
        return [self._row_to_entry(r) for r in rows]

    def _row_to_entry(self, row) -> WorklogEntry:
        meta_raw = row["metadata_json"]
        metadata = json.loads(meta_raw) if meta_raw else {}
        return WorklogEntry(
            entry_id=row["entry_id"],
            user_id=row["user_id"],
            agent_id=row["agent_id"],
            start_at=from_iso(row["start_at"]),
            end_at=from_iso(row["end_at"]) if row["end_at"] else None,
            break_minutes=int(row["break_minutes"] or 0),
            description=row["description"],
            metadata=metadata,
            created_at=from_iso(row["created_at"]),
            updated_at=from_iso(row["updated_at"]),
        )
