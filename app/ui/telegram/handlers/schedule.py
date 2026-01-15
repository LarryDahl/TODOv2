from __future__ import annotations

import re
import uuid
from datetime import timedelta, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.infra.db.connection import Database
from app.infra.clock.system_clock import SystemClock
from app.domain.common.time import to_iso
from app.infra.db.repo.scheduled_jobs_sqlite import ScheduledJobsRepo

router = Router()

SYSTEM_AGENT_ID = "system"


def _parse_delay(token: str) -> timedelta:
    m = re.fullmatch(r"(\d+)([mh]?)", token.strip())
    if not m:
        raise ValueError
    value = int(m.group(1))
    unit = m.group(2) or "m"
    return timedelta(minutes=value) if unit == "m" else timedelta(hours=value)


async def _ensure_user_and_system_agent(db: Database, user_id: int, now_iso: str) -> None:
    # user
    row = await db.fetchone("SELECT user_id FROM users WHERE user_id = ?;", (user_id,))
    if row:
        await db.execute("UPDATE users SET last_seen_at=? WHERE user_id=?;", (now_iso, user_id))
    else:
        await db.execute(
            "INSERT INTO users(user_id, created_at, last_seen_at) VALUES (?, ?, ?);",
            (user_id, now_iso, now_iso),
        )

    # system agent
    arow = await db.fetchone("SELECT agent_id FROM agents WHERE agent_id = ?;", (SYSTEM_AGENT_ID,))
    if not arow:
        await db.execute(
            "INSERT INTO agents(agent_id, name, category, is_active, created_at) VALUES (?, ?, ?, 1, ?);",
            (SYSTEM_AGENT_ID, "System", "core", now_iso),
        )


@router.message(Command("schedule"))
async def schedule_debug(message: Message, db: Database, clock: SystemClock):
    parts = (message.text or "").strip().split()
    if len(parts) != 3:
        await message.reply("Usage: /schedule ping 1 | 10m | 2h")
        return

    _, job_type, delay_token = parts

    try:
        delta = _parse_delay(delay_token)
    except Exception:
        await message.reply("Invalid delay. Use: 1 | 10m | 2h")
        return

    now = clock.now().astimezone(timezone.utc)
    now_iso = to_iso(now)
    due_at = now + delta

    await _ensure_user_and_system_agent(db, message.from_user.id, now_iso)

    repo = ScheduledJobsRepo(db)
    job_id = str(uuid.uuid4())

    await repo.create(
        job_id=job_id,
        user_id=message.from_user.id,
        agent_id=SYSTEM_AGENT_ID,
        job_type=job_type,
        schedule_kind="once",
        schedule={},
        payload={"chat_id": message.chat.id},
        due_at_iso_utc=to_iso(due_at),
        now_iso=now_iso,
    )

    await message.reply(f"✅ Scheduled {job_type} in {delay_token}\njob_id: {job_id}")
