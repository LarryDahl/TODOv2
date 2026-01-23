from __future__ import annotations

import asyncio
import json
import aiosqlite
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.constants import (
    ACTION_TASK_COMPLETED,
    ACTION_TASK_DELETED,
    ACTION_TASK_EDITED,
    TASK_ACTION_COMPLETED,
    TASK_ACTION_DELETED,
)
from app.priority import parse_priority
from app.priority_compute import compute_deadline_priority, compute_schedule_priority


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
                    action TEXT NOT NULL,         -- TASK_ACTION_COMPLETED | TASK_ACTION_DELETED
                    text TEXT NOT NULL,
                    at TEXT NOT NULL
                );
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_task_events_user_id ON task_events(user_id);")
            
            # Suggestion tracking table (to avoid showing same suggestions repeatedly)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS suggestion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_id INTEGER NOT NULL,
                    action TEXT NOT NULL,  -- 'accepted' | 'snoozed' | 'ignored'
                    at TEXT NOT NULL
                );
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_suggestion_log_user_event ON suggestion_log(user_id, event_id);")
            
            # Action logging table (lightweight event logging)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS action_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,  -- 'task_created', 'task_completed', 'task_edited', 'task_deleted', 'suggestion_shown', 'suggestion_accepted', 'suggestion_ignored'
                    task_id INTEGER,
                    payload TEXT,  -- JSON string with action-specific data
                    at TEXT NOT NULL  -- ISO datetime in UTC
                );
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_action_log_user_at ON action_log(user_id, at);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_action_log_action ON action_log(action);")
            await db.commit()

    async def list_tasks(self, user_id: int, limit: int = 50) -> list[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Fetch all tasks to ensure consistent sorting across different views
            cur = await db.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, created_at, updated_at
                FROM tasks
                WHERE user_id = ?;
                """,
                (user_id,),
            )
            tasks = [Task(**dict(r)) for r in await cur.fetchall()]
            
            # Sort by priority rules (explicit ordering):
            # 1. Higher '!' priority first (base priority from parse_priority, 0-5)
            # 2. Then deadline/schedule urgency (computed boost from deadline/schedule proximity)
            # 3. Then creation time (older first for same priority)
            now = datetime.now(timezone.utc)
            
            def sort_key(task: Task) -> tuple:
                # Primary: base priority from '!' (higher first)
                base_prio = task.priority
                
                # Secondary: computed urgency boost (deadline/schedule)
                # Extract just the boost part (without base priority)
                deadline_boost = compute_deadline_priority(task.deadline, now)
                schedule_boost = compute_schedule_priority(task.schedule_kind, task.schedule_json, now)
                urgency_boost = deadline_boost + schedule_boost
                
                # Tertiary: creation time (older first = ascending)
                created_at = task.created_at
                
                # Return tuple for sorting: negative for descending, positive for ascending
                return (-base_prio, -urgency_boost, created_at)
            
            tasks.sort(key=sort_key)
            return tasks[:limit]
    
    async def list_completed_tasks(self, user_id: int, limit: int = 3) -> list[dict]:
        """Get most recently completed tasks"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, task_id, text, at
                FROM task_events
                WHERE user_id = ? AND action = ?
                ORDER BY at DESC
                LIMIT ?;
                """,
                (user_id, TASK_ACTION_COMPLETED, limit),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
    
    async def _list_event_tasks(self, user_id: int, action: str, limit: int, offset: int) -> list[dict]:
        """Helper to list tasks from events (done/deleted)."""
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
                    ? as status,
                    e.at as updated_at
                FROM task_events e
                WHERE e.user_id = ? AND e.action = ?
                ORDER BY e.at DESC
                LIMIT ? OFFSET ?;
                """,
                (action, user_id, action, limit, offset),
            )
            return [dict(r) for r in await cur.fetchall()]
    
    async def list_done_tasks(self, user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
        """List completed tasks with deadline and schedule metadata."""
        return await self._list_event_tasks(user_id, TASK_ACTION_COMPLETED, limit, offset)
    
    async def list_deleted_tasks(self, user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
        """List deleted (cancelled) tasks with deadline and schedule metadata."""
        return await self._list_event_tasks(user_id, TASK_ACTION_DELETED, limit, offset)

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
            task_id = int(cur.lastrowid)
            
            # Log action (non-blocking)
            await self.log_action(
                user_id=user_id,
                action='task_created',
                task_id=task_id,
                payload={'text': clean_title, 'task_type': task_type, 'priority': priority},
            )
            
            return task_id

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
            success = cur.rowcount > 0
            
            # Log action (non-blocking)
            if success:
                await self.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={'new_text': clean_title, 'priority': priority},
                )
            
            return success
    
    async def update_task_meta(
        self,
        user_id: int,
        task_id: int,
        patch: dict,
    ) -> bool:
        """
        Update task metadata using a patch dict.
        
        Args:
            user_id: User ID
            task_id: Task ID
            patch: Dict with fields to update. Supported keys:
                - 'text': Update task text (priority will be re-parsed)
                - 'priority': Update priority directly (0-5)
                - 'deadline': Set deadline (ISO datetime string in UTC, or None to clear)
                - 'increment_priority': Increment priority by 1 (clamped to 0-5)
                - 'decrement_priority': Decrement priority by 1 (clamped to 0-5)
        
        Returns:
            True if task was updated, False if not found or unauthorized
        """
        # Get current task
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if not task:
            return False
        
        now = self._now_iso()
        updates = []
        params = []
        
        # Handle text update (re-parse priority)
        if 'text' in patch:
            clean_title, priority = parse_priority(patch['text'])
            updates.append("text = ?")
            updates.append("priority = ?")
            updates.append("priority_source = ?")
            params.extend([clean_title, priority, 'bang_suffix'])
        
        # Handle direct priority update
        elif 'priority' in patch:
            priority = max(0, min(5, int(patch['priority'])))
            updates.append("priority = ?")
            params.append(priority)
        
        # Handle priority increment
        elif 'increment_priority' in patch:
            new_priority = min(5, task.priority + 1)
            updates.append("priority = ?")
            params.append(new_priority)
        
        # Handle priority decrement
        elif 'decrement_priority' in patch:
            new_priority = max(0, task.priority - 1)
            updates.append("priority = ?")
            params.append(new_priority)
        
        # Handle deadline update
        if 'deadline' in patch:
            updates.append("deadline = ?")
            params.append(patch['deadline'])
        
        # Always update updated_at
        updates.append("updated_at = ?")
        params.append(now)
        
        # Add WHERE clause params
        params.extend([user_id, task_id])
        
        if not updates:
            return False
        
        async with aiosqlite.connect(self._db_path) as db:
            sql = f"""
                UPDATE tasks
                SET {', '.join(updates)}
                WHERE user_id = ? AND id = ?;
            """
            cur = await db.execute(sql, params)
            await db.commit()
            success = cur.rowcount > 0
            
            # Log action (non-blocking)
            if success:
                await self.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload=patch,
                )
            
            return success

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

        await self._log_event(user_id=user_id, task_id=task_id, action=TASK_ACTION_COMPLETED, text=task.text)

        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                "DELETE FROM tasks WHERE user_id = ? AND id = ?;",
                (user_id, task_id),
            )
            await db.commit()
            success = cur.rowcount > 0
            
            # Log action (non-blocking)
            if success:
                await self.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_COMPLETED,
                    task_id=task_id,
                    payload={'text': task.text},
                )
            
            return success
    
    async def restore_completed_task(self, user_id: int, event_id: int) -> bool:
        """Restore a completed task back to the task list using event id"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Get the completed task event
            cur = await db.execute(
                """
                SELECT id, task_id, text, at
                FROM task_events
                WHERE user_id = ? AND action = ? AND id = ?;
                """,
                (user_id, TASK_ACTION_COMPLETED, event_id),
            )
            row = await cur.fetchone()
            if not row:
                return False
            
            # Guard: Check if task is already active (exists in tasks table)
            if row['task_id']:
                existing_task = await self.get_task(user_id=user_id, task_id=row['task_id'])
                if existing_task:
                    # Task is already active, cannot restore
                    return False
                
                # Guard: Check if task was deleted (exists in deleted events)
                cur = await db.execute(
                    """
                    SELECT id FROM task_events
                    WHERE user_id = ? AND task_id = ? AND action = ?;
                    """,
                    (user_id, row['task_id'], TASK_ACTION_DELETED),
                )
                if await cur.fetchone():
                    # Task was deleted, cannot restore from completed
                    return False
            
            # Try to get original task data if task_id exists (might be None if task was already deleted)
            original_task = None
            if row['task_id']:
                # Try to get from tasks table (might not exist if task was deleted)
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
                WHERE user_id = ? AND action = ?
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
                WHERE user_id = ? AND action = ? AND id = ?;
                """,
                (user_id, TASK_ACTION_DELETED, event_id),
            )
            row = await cur.fetchone()
            if not row:
                return False
            
            # Try to get priority from action_log (where it was stored during deletion)
            priority = 0
            priority_source = 'bang_suffix'
            if row['task_id']:
                # Try to get priority from action_log payload
                cur = await db.execute(
                    """
                    SELECT payload
                    FROM action_log
                    WHERE user_id = ? AND task_id = ? AND action = ?
                    ORDER BY at DESC
                    LIMIT 1;
                    """,
                    (user_id, row['task_id'], ACTION_TASK_DELETED),
                )
                log_row = await cur.fetchone()
                if log_row and log_row['payload']:
                    try:
                        payload = json.loads(log_row['payload'])
                        # Priority might be stored in payload, or we parse from text
                        if 'priority' in payload:
                            priority = payload['priority']
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
            
            # If priority not found in action_log, try to parse from text
            if priority == 0:
                restore_text = row['text']
                # Remove reason suffix if present (format: "text | Syy: reason")
                if " | Syy: " in restore_text:
                    restore_text = restore_text.split(" | Syy: ")[0]
                clean_title, priority = parse_priority(restore_text)
            
            # Get other metadata from action_log if available
            task_type = 'regular'
            difficulty = 5
            category = ''
            deadline = None
            scheduled_time = None
            schedule_kind = None
            schedule_json = None
            
            if row['task_id']:
                # Try to get full task metadata from action_log
                cur = await db.execute(
                    """
                    SELECT payload
                    FROM action_log
                    WHERE user_id = ? AND task_id = ? AND action = ?
                    ORDER BY at DESC
                    LIMIT 1;
                    """,
                    (user_id, row['task_id'], ACTION_TASK_DELETED),
                )
                log_row = await cur.fetchone()
                if log_row and log_row['payload']:
                    try:
                        payload = json.loads(log_row['payload'])
                        task_type = payload.get('task_type', 'regular')
                        difficulty = payload.get('difficulty', 5)
                        category = payload.get('category', '')
                        deadline = payload.get('deadline')
                        scheduled_time = payload.get('scheduled_time')
                        schedule_kind = payload.get('schedule_kind')
                        schedule_json = payload.get('schedule_json')
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
            
            # Clean text (remove reason suffix if present)
            restore_text = row['text']
            if " | Syy: " in restore_text:
                restore_text = restore_text.split(" | Syy: ")[0]
            clean_title, _ = parse_priority(restore_text)  # Priority already set above
            
            now = self._now_iso()
            cur = await db.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id,
                    clean_title,
                    task_type,
                    difficulty,
                    category,
                    deadline,
                    scheduled_time,
                    priority,
                    priority_source,
                    schedule_kind,
                    schedule_json,
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
                WHERE user_id = ? AND action = ? 
                AND datetime(at) >= datetime('now', '-' || ? || ' days');
                """,
                (user_id, TASK_ACTION_COMPLETED, days),
            )
            completed = (await cur.fetchone())['count']
            
            # Get deleted tasks count
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ?
                AND datetime(at) >= datetime('now', '-' || ? || ' days');
                """,
                (user_id, TASK_ACTION_DELETED, days),
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
                WHERE user_id = ? AND action = ?
                AND date(at) = date('now');
                """,
                (user_id, TASK_ACTION_COMPLETED),
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

    async def delete_task_with_log(self, user_id: int, task_id: int, reason: str = "") -> bool:
        """
        Delete a task and log the deletion event with reason.
        
        Args:
            user_id: User ID
            task_id: Task ID to delete
            reason: Optional deletion reason (defaults to empty string)
        
        Returns:
            True if task was deleted, False if task not found or already deleted
        """
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if not task:
            return False

        # Store task text and reason in event (format: "task_text | reason" or just "task_text" if no reason)
        event_text = task.text
        if reason:
            event_text = f"{task.text} | Syy: {reason}"

        await self._log_event(user_id=user_id, task_id=task_id, action="deleted", text=event_text)
        
        # Delete task from tasks table
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "DELETE FROM tasks WHERE user_id = ? AND id = ?;",
                (user_id, task_id),
            )
            await db.commit()
        
        # Log action with full task metadata for restoration (non-blocking)
        await self.log_action(
            user_id=user_id,
            action=ACTION_TASK_DELETED,
            task_id=task_id,
            payload={
                'reason': reason,
                'text': task.text,
                'priority': task.priority,
                'task_type': task.task_type,
                'difficulty': task.difficulty,
                'category': task.category,
                'deadline': task.deadline,
                'scheduled_time': task.scheduled_time,
                'schedule_kind': task.schedule_kind,
                'schedule_json': task.schedule_json,
            },
        )
    
    async def get_backlog_tasks(self, user_id: int, limit: int = 100) -> tuple[list[dict], list[dict]]:
        """
        Get backlog tasks (completed + deleted) with metadata.
        
        Returns:
            Tuple of (completed_tasks, deleted_tasks) where each is a list of dicts
            with keys: id, task_id, text, at, deadline, schedule_kind, schedule_json, priority
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get completed tasks with metadata from tasks table if task_id exists
            cur = await db.execute(
                """
                SELECT 
                    e.id,
                    e.task_id,
                    e.text,
                    e.at,
                    t.deadline,
                    t.schedule_kind,
                    t.schedule_json,
                    t.priority
                FROM task_events e
                LEFT JOIN tasks t ON e.task_id = t.id AND e.user_id = t.user_id
                WHERE e.user_id = ? AND e.action = ?
                ORDER BY e.at DESC
                LIMIT ?;
                """,
                (user_id, TASK_ACTION_COMPLETED, limit),
            )
            completed = [dict(r) for r in await cur.fetchall()]
            
            # Get deleted tasks with metadata
            cur = await db.execute(
                """
                SELECT 
                    e.id,
                    e.task_id,
                    e.text,
                    e.at,
                    t.deadline,
                    t.schedule_kind,
                    t.schedule_json,
                    t.priority
                FROM task_events e
                LEFT JOIN tasks t ON e.task_id = t.id AND e.user_id = t.user_id
                WHERE e.user_id = ? AND e.action = ?
                ORDER BY e.at DESC
                LIMIT ?;
                """,
                (user_id, TASK_ACTION_DELETED, limit),
            )
            deleted = [dict(r) for r in await cur.fetchall()]
            
            return (completed, deleted)
    
    async def log_suggestion_action(
        self, user_id: int, event_id: int, action: str
    ) -> None:
        """
        Log a suggestion action (accepted/snoozed/ignored).
        
        Args:
            user_id: User ID
            event_id: Event ID from task_events
            action: 'accepted' | 'snoozed' | 'ignored'
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO suggestion_log (user_id, event_id, action, at)
                VALUES (?, ?, ?, ?);
                """,
                (user_id, event_id, action, self._now_iso()),
            )
            await db.commit()
    
    async def get_snoozed_event_ids(self, user_id: int, days: int = 7) -> set[int]:
        """
        Get event IDs that were snoozed within the last N days.
        These should not be shown as suggestions.
        
        Args:
            user_id: User ID
            days: Number of days to look back (default 7)
        
        Returns:
            Set of event IDs that were snoozed recently
        """
        async with aiosqlite.connect(self._db_path) as db:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            cur = await db.execute(
                """
                SELECT DISTINCT event_id
                FROM suggestion_log
                WHERE user_id = ? AND action = 'snoozed' AND at > ?;
                """,
                (user_id, cutoff),
            )
            return {row[0] for row in await cur.fetchall()}
    
    async def log_action(
        self,
        user_id: int,
        action: str,
        task_id: Optional[int] = None,
        payload: Optional[dict] = None,
    ) -> None:
        """
        Log an action event (non-blocking, errors are silently ignored).
        
        Args:
            user_id: User ID
            action: Action type (use constants from app.constants: ACTION_TASK_* or ACTION_SUGGESTION_*)
            task_id: Optional task ID
            payload: Optional dict with action-specific data (will be JSON-encoded)
        """
        try:
            payload_json = json.dumps(payload) if payload else None
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """
                    INSERT INTO action_log (user_id, action, task_id, payload, at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (user_id, action, task_id, payload_json, self._now_iso()),
                )
                await db.commit()
        except Exception:
            # Non-blocking: silently ignore logging errors
            pass
    
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
            success = cur.rowcount > 0
            
            # Log action (non-blocking)
            if success:
                await self.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={'new_text': clean_title, 'priority': priority},
                )
            
            return success
    
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
            success = cur.rowcount > 0
            
            # Log action (non-blocking)
            if success:
                await self.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={'new_text': clean_title, 'priority': priority},
                )
            
            return success
    
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
            success = cur.rowcount > 0
            
            # Log action (non-blocking)
            if success:
                await self.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={'new_text': clean_title, 'priority': priority},
                )
            
            return success
    
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
            success = cur.rowcount > 0
            
            # Log action (non-blocking)
            if success:
                await self.log_action(
                    user_id=user_id,
                    action=ACTION_TASK_EDITED,
                    task_id=task_id,
                    payload={'new_text': clean_title, 'priority': priority},
                )
            
            return success
