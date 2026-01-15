from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.infra.db.connection import Database
from app.infra.clock.system_clock import SystemClock
from app.domain.common.time import to_iso
from app.ui.telegram.keyboards.common import main_menu_kb
from app.domain.oppari.models import AGENT_ID

router = Router()


@router.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer("LifeOps online.", reply_markup=main_menu_kb())


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "Commands:\n"
        "/start\n"
        "/help\n"
        "/status\n"
        "/agents\n"
        "/agent enable [id]\n"
        "/agent disable [id]\n"
        "/agent info [id]\n"
        "/opp_start /opp_end /opp_status\n"
        "/ping"
    )


@router.message(Command("ping"))
async def ping(message: Message):
    await message.answer("pong")


@router.message(Command("status"))
async def status_cmd(message: Message, db: Database):
    user_id = message.from_user.id

    # enabled agents for user
    rows = await db.fetchall(
        """
        SELECT a.agent_id, a.name, a.category,
               COALESCE(s.is_enabled, 1) AS is_enabled
        FROM agents a
        LEFT JOIN agent_user_settings s
          ON s.agent_id = a.agent_id AND s.user_id = ?
        ORDER BY a.category, a.agent_id;
        """,
        (user_id,),
    )

    enabled = [r for r in rows if int(r["is_enabled"]) == 1]
    txt = ["<b>Status</b>"]
    if not enabled:
        txt.append("No enabled agents (default is enabled if not set).")
    else:
        txt.append("Enabled agents:")
        for r in enabled:
            txt.append(f"- {r['agent_id']} ({r['category']})")

    # quick open-session check for Oppari
    open_row = await db.fetchone(
        """
        SELECT start_at FROM worklog_entries
        WHERE user_id = ? AND agent_id = ? AND end_at IS NULL
        ORDER BY start_at DESC
        LIMIT 1;
        """,
        (user_id, AGENT_ID),
    )
    if open_row:
        txt.append(f"\nOppari running since: {open_row['start_at']}")
    else:
        txt.append("\nOppari not running.")

    await message.answer("\n".join(txt))


@router.message(Command("agents"))
async def agents_cmd(message: Message, db: Database):
    user_id = message.from_user.id
    rows = await db.fetchall(
        """
        SELECT a.agent_id, a.name, a.category,
               COALESCE(s.is_enabled, 1) AS is_enabled
        FROM agents a
        LEFT JOIN agent_user_settings s
          ON s.agent_id = a.agent_id AND s.user_id = ?
        ORDER BY a.category, a.agent_id;
        """,
        (user_id,),
    )
    if not rows:
        await message.answer("No agents registered yet.")
        return

    lines = ["<b>Agents</b>"]
    for r in rows:
        onoff = "enabled" if int(r["is_enabled"]) == 1 else "disabled"
        lines.append(f"- <b>{r['agent_id']}</b> • {r['name']} • {r['category']} • {onoff}")
    await message.answer("\n".join(lines))


@router.message(Command("agent"))
async def agent_cmd(message: Message, db: Database, clock: SystemClock):
    """
    Usage:
      /agent enable <id>
      /agent disable <id>
      /agent info <id>
    """
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("Usage: /agent enable|disable|info <agent_id>")
        return

    action = parts[1].strip().lower()
    agent_id = parts[2].strip().lower()
    user_id = message.from_user.id
    now_iso = to_iso(clock.now())

    arow = await db.fetchone("SELECT agent_id, name, category FROM agents WHERE agent_id = ?;", (agent_id,))
    if not arow:
        await message.answer(f"Unknown agent_id: {agent_id}")
        return

    if action == "info":
        srow = await db.fetchone(
            "SELECT is_enabled FROM agent_user_settings WHERE user_id = ? AND agent_id = ?;",
            (user_id, agent_id),
        )
        is_enabled = 1 if srow is None else int(srow["is_enabled"])
        await message.answer(
            f"<b>{agent_id}</b>\n"
            f"Name: {arow['name']}\n"
            f"Category: {arow['category']}\n"
            f"Enabled: {'yes' if is_enabled == 1 else 'no'}"
        )
        return

    if action not in ("enable", "disable"):
        await message.answer("Unknown action. Use enable|disable|info.")
        return

    is_enabled = 1 if action == "enable" else 0

    await db.execute(
        """
        INSERT INTO agent_user_settings(user_id, agent_id, is_enabled, settings_json, updated_at)
        VALUES (?, ?, ?, NULL, ?)
        ON CONFLICT(user_id, agent_id)
        DO UPDATE SET is_enabled = excluded.is_enabled, updated_at = excluded.updated_at;
        """,
        (user_id, agent_id, is_enabled, now_iso),
    )

    await message.answer(f"{agent_id} -> {'enabled' if is_enabled == 1 else 'disabled'}")


# Callback hooks from main menu keyboard
@router.callback_query(lambda c: (c.data or "").startswith("admin:"))
async def admin_callbacks(cb: CallbackQuery, db: Database):
    data = cb.data or ""
    if data == "admin:agents":
        await cb.answer()
        fake_msg = cb.message
        # reuse agents output
        user_id = cb.from_user.id
        rows = await db.fetchall(
            """
            SELECT a.agent_id, a.name, a.category,
                   COALESCE(s.is_enabled, 1) AS is_enabled
            FROM agents a
            LEFT JOIN agent_user_settings s
              ON s.agent_id = a.agent_id AND s.user_id = ?
            ORDER BY a.category, a.agent_id;
            """,
            (user_id,),
        )
        if not rows:
            await fake_msg.answer("No agents registered yet.")
            return
        lines = ["<b>Agents</b>"]
        for r in rows:
            onoff = "enabled" if int(r["is_enabled"]) == 1 else "disabled"
            lines.append(f"- <b>{r['agent_id']}</b> • {r['name']} • {r['category']} • {onoff}")
        await fake_msg.answer("\n".join(lines))
        return

    if data == "admin:status":
        await cb.answer()
        # just tell user to run /status to keep it simple
        await cb.message.answer("Use /status")
        return
