# app/infra/db/repo/scheduled_jobs_sqlite.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from app.infra.db.connection import Database


@dataclass(frozen=True)
class ScheduledJob:
    job_id: str
    user_id: int
    agent_id: str
    job_type: str
    schedule_kind: str
    schedule: dict[str, Any]
    payload: dict[str, Any]
    status: str
    due_at: str
    created_at: str
    updated_at: str
    run_count: int
    last_run_at: Optional[str]
    last_error: Optional[str]
    completed_at: Optional[str]


class ScheduledJobsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        job_id: str,
        user_id: int,
        agent_id: str,
        job_type: str,
        schedule_kind: str,
        schedule: dict[str, Any],
        payload: dict[str, Any],
        due_at_iso_utc: str,
        now_iso: str,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO scheduled_jobs(
              job_id, user_id, agent_id,
              job_type, schedule_kind, schedule_json, payload_json,
              status, due_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?);
            """,
            (
                job_id,
                user_id,
                agent_id,
                job_type,
                schedule_kind,
                json.dumps(schedule, ensure_ascii=False) if schedule else None,
                json.dumps(payload, ensure_ascii=False) if payload else None,
                due_at_iso_utc,
                now_iso,
                now_iso,
            ),
        )

    async def create_todo(
        self,
        job_id: str,
        user_id: int,
        agent_id: str,
        title: str,
        chat_id: int,
        due_at_iso_utc: str,
        now_iso: str,
    ) -> None:
        payload = {"title": title, "chat_id": chat_id}
        await self.create(
            job_id=job_id,
            user_id=user_id,
            agent_id=agent_id,
            job_type="todo",
            schedule_kind="once",
            schedule={},
            payload=payload,
            due_at_iso_utc=due_at_iso_utc,
            now_iso=now_iso,
        )

    async def list_pending_todos(self, user_id: int) -> list[dict[str, Any]]:
        rows = await self._db.fetchall(
            """
            SELECT job_id, payload_json
            FROM scheduled_jobs
            WHERE user_id = ? AND job_type = 'todo' AND status = 'pending'
            ORDER BY created_at ASC;
            """,
            (user_id,),
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            payload = json.loads(r["payload_json"] or "{}")
            out.append({"job_id": r["job_id"], "title": payload.get("title", "")})
        return out

    async def mark_todo_done(self, job_id: str, user_id: int, now_iso: str) -> None:
        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET status='done', completed_at=?, updated_at=?
            WHERE job_id=? AND user_id=? AND job_type='todo';
            """,
            (now_iso, now_iso, job_id, user_id),
        )

    async def delete_todo(self, job_id: str, user_id: int, now_iso: str) -> None:
        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET status='deleted', updated_at=?
            WHERE job_id=? AND user_id=? AND job_type='todo';
            """,
            (now_iso, job_id, user_id),
        )

    async def update_todo_title(self, job_id: str, user_id: int, title: str, now_iso: str) -> None:
        row = await self._db.fetchone(
            """
            SELECT payload_json
            FROM scheduled_jobs
            WHERE job_id=? AND user_id=? AND job_type='todo';
            """,
            (job_id, user_id),
        )
        payload = json.loads((row["payload_json"] if row else None) or "{}")
        payload["title"] = title

        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET payload_json=?, updated_at=?
            WHERE job_id=? AND user_id=? AND job_type='todo';
            """,
            (json.dumps(payload, ensure_ascii=False), now_iso, job_id, user_id),
        )

    async def get_todo_chat_id(self, job_id: str, user_id: int) -> Optional[int]:
        row = await self._db.fetchone(
            """
            SELECT payload_json
            FROM scheduled_jobs
            WHERE job_id=? AND user_id=? AND job_type='todo';
            """,
            (job_id, user_id),
        )
        if not row:
            return None
        payload = json.loads(row["payload_json"] or "{}")
        v = payload.get("chat_id")
        return int(v) if v is not None else None

    async def list_pending_todos_for_user(self, user_id: int, limit: int = 5000):
        rows = await self._db.fetchall(
            """
            SELECT *
            FROM scheduled_jobs
            WHERE user_id=? AND status='pending' AND job_type='todo'
            ORDER BY due_at ASC, created_at ASC
            LIMIT ?;
            """,
            (user_id, limit),
        )
        return [self._row_to_job(r) for r in rows]

    async def cancel_top_todo_for_user(self, user_id: int, now_iso: str) -> bool:
        row = await self._db.fetchone(
            """
            SELECT job_id
            FROM scheduled_jobs
            WHERE user_id=? AND status='pending' AND job_type='todo'
            ORDER BY due_at ASC, created_at ASC
            LIMIT 1;
            """,
            (user_id,),
        )
        if not row:
            return False

        job_id = row["job_id"]
        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET status='cancelled',
                updated_at=?
            WHERE job_id=? AND user_id=?;
            """,
            (now_iso, job_id, user_id),
        )
        return True

    async def cancel_all_todos_for_user(self, user_id: int, now_iso: str) -> int:
        row = await self._db.fetchone(
            """
            SELECT COUNT(*) AS cnt
            FROM scheduled_jobs
            WHERE user_id=? AND status='pending' AND job_type='todo';
            """,
            (user_id,),
        )
        cnt = int(row["cnt"]) if row else 0

        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET status='cancelled',
                updated_at=?
            WHERE user_id=? AND status='pending' AND job_type='todo';
            """,
            (now_iso, user_id),
        )
        return cnt

    async def mark_done_for_user(self, job_id: str, user_id: int, now_iso: str) -> bool:
        row = await self._db.fetchone(
            """
            SELECT job_id
            FROM scheduled_jobs
            WHERE job_id=? AND user_id=? AND status='pending';
            """,
            (job_id, user_id),
        )
        if not row:
            return False

        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET status='done',
                completed_at=?,
                updated_at=?
            WHERE job_id=? AND user_id=?;
            """,
            (now_iso, now_iso, job_id, user_id),
        )
        return True

    async def cancel_for_user(self, job_id: str, user_id: int, now_iso: str) -> bool:
        row = await self._db.fetchone(
            """
            SELECT job_id
            FROM scheduled_jobs
            WHERE job_id=? AND user_id=? AND status='pending';
            """,
            (job_id, user_id),
        )
        if not row:
            return False

        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET status='cancelled',
                updated_at=?
            WHERE job_id=? AND user_id=?;
            """,
            (now_iso, job_id, user_id),
        )
        return True



    async def get(self, job_id: str) -> Optional[ScheduledJob]:
        row = await self._db.fetchone("SELECT * FROM scheduled_jobs WHERE job_id = ?;", (job_id,))
        return self._row_to_job(row) if row else None

    async def list_due(self, now_iso_utc: str, limit: int = 25) -> Sequence[ScheduledJob]:
        rows = await self._db.fetchall(
            """
            SELECT *
            FROM scheduled_jobs
            WHERE status = 'pending' AND due_at <= ?
            ORDER BY due_at ASC
            LIMIT ?;
            """,
            (now_iso_utc, limit),
        )
        return [self._row_to_job(r) for r in rows]

    async def mark_run_ok(self, job_id: str, next_due_at_iso_utc: Optional[str], now_iso: str) -> None:
        # if next_due_at is None => complete job
        if next_due_at_iso_utc is None:
            await self._db.execute(
                """
                UPDATE scheduled_jobs
                SET status='done',
                    completed_at=?,
                    last_run_at=?,
                    run_count=run_count+1,
                    last_error=NULL,
                    updated_at=?
                WHERE job_id=?;
                """,
                (now_iso, now_iso, now_iso, job_id),
            )
            return

        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET due_at=?,
                last_run_at=?,
                run_count=run_count+1,
                last_error=NULL,
                updated_at=?
            WHERE job_id=?;
            """,
            (next_due_at_iso_utc, now_iso, now_iso, job_id),
        )

    async def mark_run_failed(self, job_id: str, error: str, now_iso: str) -> None:
        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET status='failed',
                last_run_at=?,
                run_count=run_count+1,
                last_error=?,
                updated_at=?
            WHERE job_id=?;
            """,
            (now_iso, error[:2000], now_iso, job_id),
        )

    async def cancel(self, job_id: str, now_iso: str) -> None:
        await self._db.execute(
            """
            UPDATE scheduled_jobs
            SET status='cancelled',
                updated_at=?
            WHERE job_id=?;
            """,
            (now_iso, job_id),
        )

    async def list_pending_for_user(self, user_id: int, limit: int = 50) -> Sequence[ScheduledJob]:
        rows = await self._db.fetchall(
            """
            SELECT *
            FROM scheduled_jobs
            WHERE user_id=? AND status='pending'
            ORDER BY due_at ASC
            LIMIT ?;
            """,
            (user_id, limit),
        )
        return [self._row_to_job(r) for r in rows]

    def _row_to_job(self, row) -> ScheduledJob:
        schedule = json.loads(row["schedule_json"]) if row["schedule_json"] else {}
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        return ScheduledJob(
            job_id=row["job_id"],
            user_id=int(row["user_id"]),
            agent_id=row["agent_id"],
            job_type=row["job_type"],
            schedule_kind=row["schedule_kind"],
            schedule=schedule,
            payload=payload,
            status=row["status"],
            due_at=row["due_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            run_count=int(row["run_count"] or 0),
            last_run_at=row["last_run_at"],
            last_error=row["last_error"],
            completed_at=row["completed_at"],
        )
