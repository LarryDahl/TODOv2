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
# Note: compute_deadline_priority and compute_schedule_priority were replaced by compute_priority
# Import is done inline where needed to avoid circular imports


@dataclass(frozen=True)
class Task:
    id: int
    user_id: int
    text: str
    task_type: str  # 'deadline', 'scheduled', 'regular'
    difficulty: int  # percentage (1, 5, 10, or custom)
    category: str  # 'liikunta', 'arki', 'opiskelu', 'suhteet', 'muu', ''
    deadline: Optional[str]  # ISO datetime for deadline (latest-by), UTC (legacy, use deadline_time)
    scheduled_time: Optional[str]  # ISO datetime for scheduled tasks (deprecated, use schedule_kind/schedule_json or scheduled_time)
    priority: int  # 0 to 5, derived from trailing '!' in title
    priority_source: str  # 'bang_suffix' or future AI-based sources
    schedule_kind: Optional[str]  # 'none' | 'at_time' | 'time_range' | 'all_day' | None
    schedule_json: Optional[str]  # JSON string with schedule details
    deadline_time: Optional[str]  # ISO datetime for deadline (simplified, for priority computation), UTC
    scheduled_time_new: Optional[str]  # ISO datetime for scheduled time (simplified, for priority computation), UTC
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
                    deadline_time TEXT,
                    scheduled_time_new TEXT,
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
            # New simplified time fields for priority computation
            if 'deadline_time' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN deadline_time TEXT;")
            if 'scheduled_time_new' not in columns:
                await db.execute("ALTER TABLE tasks ADD COLUMN scheduled_time_new TEXT;")
            
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
            
            # User settings table (timezone, show_done, etc.)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    timezone TEXT NOT NULL DEFAULT 'Europe/Helsinki',
                    show_done_in_home BOOLEAN NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_action_log_action ON action_log(action);")
            
            # Projects table for backlog projects with ordered steps
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
            
            # Migration: Add completed_at column if it doesn't exist
            cursor = await db.execute("PRAGMA table_info(projects)")
            project_columns = [row[1] for row in await cursor.fetchall()]
            if 'completed_at' not in project_columns:
                await db.execute("ALTER TABLE projects ADD COLUMN completed_at TEXT;")
            
            # Project steps table
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
            
            # Indexes for project_steps
            await db.execute("CREATE INDEX IF NOT EXISTS idx_project_steps_project_id ON project_steps(project_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_project_steps_project_status ON project_steps(project_id, status);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_project_steps_project_order ON project_steps(project_id, order_index);")
            
            await db.commit()

    async def list_tasks(self, user_id: int, limit: int = 50) -> list[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Fetch all tasks to ensure consistent sorting across different views
            cur = await db.execute(
                """
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, created_at, updated_at
                FROM tasks
                WHERE user_id = ?;
                """,
                (user_id,),
            )
            tasks = [Task(**dict(r)) for r in await cur.fetchall()]
            
            # Sort by priority rules (explicit ordering):
            # Uses simplified priority computation with deadline_time and scheduled_time_new
            # 1. Effective priority (base_priority + time_boost) - higher first
            # 2. Creation time (older first for same priority)
            now = datetime.now(timezone.utc)
            
            def sort_key(task: Task) -> tuple:
                # Use simplified priority computation with deadline_time and scheduled_time_new
                from app.priority_compute import compute_priority
                
                # Compute effective priority using new simplified logic
                effective_priority = compute_priority(
                    base_priority=task.priority,
                    scheduled_time=task.scheduled_time_new,
                    deadline_time=task.deadline_time,
                    now=now
                )
                
                # Tertiary: creation time (older first = ascending)
                created_at = task.created_at
                
                # Return tuple for sorting: negative for descending, positive for ascending
                return (-effective_priority, created_at)
            
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
        
        # Set deadline_time and scheduled_time_new for simplified priority computation
        deadline_time = deadline  # Use deadline as deadline_time
        scheduled_time_new = scheduled_time  # Use scheduled_time as scheduled_time_new
        
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO tasks (user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (user_id, clean_title, task_type, difficulty, category, deadline, scheduled_time, priority, 'bang_suffix', None, None, deadline_time, scheduled_time_new, now, now),
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
                SELECT id, user_id, text, task_type, difficulty, category, deadline, scheduled_time, priority, priority_source, schedule_kind, schedule_json, deadline_time, scheduled_time_new, created_at, updated_at
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
        """Reset all data for a user (including tasks)"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM tasks WHERE user_id = ?;", (user_id,))
            await db.execute("DELETE FROM task_events WHERE user_id = ?;", (user_id,))
            await db.execute("DELETE FROM action_log WHERE user_id = ?;", (user_id,))
            await db.execute("DELETE FROM suggestion_log WHERE user_id = ?;", (user_id,))
            await db.commit()
    
    async def reset_stats(self, user_id: int) -> bool:
        """
        Reset only statistics and logs for a user (NOT tasks).
        
        Deletes:
        - task_events (completion/deletion logs)
        - action_log (action history)
        - suggestion_log (suggestion tracking)
        
        Does NOT delete:
        - tasks (active tasks remain)
        - projects (projects remain)
        
        Args:
            user_id: User ID
        
        Returns:
            True if successful
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM task_events WHERE user_id = ?;", (user_id,))
            await db.execute("DELETE FROM action_log WHERE user_id = ?;", (user_id,))
            await db.execute("DELETE FROM suggestion_log WHERE user_id = ?;", (user_id,))
            await db.commit()
            return True
    
    async def get_all_time_stats(self, user_id: int) -> dict:
        """
        Get all time statistics for a user.
        
        Returns:
            Dict with keys:
            - completed_count: Total completed tasks (from task_events)
            - active_count: Current active tasks
            - deleted_count: Total deleted tasks (from task_events)
            - cancelled_count: Total cancelled projects
            - done_today: Completed tasks today (optional, None if no timestamps)
            - done_this_week: Completed tasks this week (optional, None if no timestamps)
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Total completed tasks
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ?;
                """,
                (user_id, TASK_ACTION_COMPLETED),
            )
            completed_count = (await cur.fetchone())['count']
            
            # Total deleted tasks
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ?;
                """,
                (user_id, TASK_ACTION_DELETED),
            )
            deleted_count = (await cur.fetchone())['count']
            
            # Current active tasks
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM tasks
                WHERE user_id = ?;
                """,
                (user_id,),
            )
            active_count = (await cur.fetchone())['count']
            
            # Cancelled projects
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM projects
                WHERE status = 'cancelled';
                """,
            )
            cancelled_count = (await cur.fetchone())['count']
            
            # Done today (if timestamps available)
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ?
                AND date(at) = date('now');
                """,
                (user_id, TASK_ACTION_COMPLETED),
            )
            done_today = (await cur.fetchone())['count']
            
            # Done this week (last 7 days)
            cur = await db.execute(
                """
                SELECT COUNT(*) as count
                FROM task_events
                WHERE user_id = ? AND action = ?
                AND datetime(at) >= datetime('now', '-7 days');
                """,
                (user_id, TASK_ACTION_COMPLETED),
            )
            done_this_week = (await cur.fetchone())['count']
            
            return {
                'completed_count': completed_count,
                'active_count': active_count,
                'deleted_count': deleted_count,
                'cancelled_count': cancelled_count,
                'done_today': done_today,
                'done_this_week': done_this_week,
            }
    
    async def get_user_settings(self, user_id: int) -> dict:
        """
        Get user settings (timezone, show_done_in_home, etc.).
        
        Returns:
            Dict with keys:
            - timezone: str (default: 'Europe/Helsinki')
            - show_done_in_home: bool (default: True)
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT timezone, show_done_in_home
                FROM user_settings
                WHERE user_id = ?;
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            
            if row:
                return {
                    'timezone': row['timezone'],
                    'show_done_in_home': bool(row['show_done_in_home']),
                }
            else:
                # Return defaults if user has no settings
                return {
                    'timezone': 'Europe/Helsinki',
                    'show_done_in_home': True,
                }
    
    async def set_user_timezone(self, user_id: int, timezone: str) -> bool:
        """
        Set user timezone.
        
        Args:
            user_id: User ID
            timezone: Timezone string (e.g., 'Europe/Helsinki')
        
        Returns:
            True if successful
        """
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            # Use INSERT OR REPLACE to handle both new and existing users
            await db.execute(
                """
                INSERT OR REPLACE INTO user_settings (user_id, timezone, show_done_in_home, updated_at)
                VALUES (?, ?, COALESCE((SELECT show_done_in_home FROM user_settings WHERE user_id = ?), 1), ?);
                """,
                (user_id, timezone, user_id, now),
            )
            await db.commit()
            return True
    
    async def toggle_show_done_in_home(self, user_id: int) -> bool:
        """
        Toggle show_done_in_home setting for user.
        
        Args:
            user_id: User ID
        
        Returns:
            New value of show_done_in_home (True/False)
        """
        now = self._now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            # Get current value
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT show_done_in_home
                FROM user_settings
                WHERE user_id = ?;
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            
            # Default is True if no settings exist
            current_value = bool(row['show_done_in_home']) if row else True
            new_value = not current_value
            
            # Update or insert
            await db.execute(
                """
                INSERT OR REPLACE INTO user_settings (user_id, timezone, show_done_in_home, updated_at)
                VALUES (?, COALESCE((SELECT timezone FROM user_settings WHERE user_id = ?), 'Europe/Helsinki'), ?, ?);
                """,
                (user_id, user_id, new_value, now),
            )
            await db.commit()
            return new_value

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
                SET deadline = ?, deadline_time = ?, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (deadline_utc, deadline_utc, now, task_id, user_id),
            )
            await db.commit()
            success = cur.rowcount > 0
            
            # Log action (non-blocking)
            if success:
                # Get task to extract text and priority for logging
                task = await self.get_task(user_id=user_id, task_id=task_id)
                if task:
                    clean_title, priority = parse_priority(task.text)
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
                # Get task to extract text and priority for logging
                task = await self.get_task(user_id=user_id, task_id=task_id)
                if task:
                    clean_title, priority = parse_priority(task.text)
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
        
        # Extract scheduled_time_new for simplified priority computation
        scheduled_time_new = None
        if schedule_kind == 'at_time' and schedule_payload:
            scheduled_time_new = schedule_payload.get('timestamp')
        
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE tasks
                SET schedule_kind = ?, schedule_json = ?, scheduled_time_new = ?, updated_at = ?
                WHERE id = ? AND user_id = ?;
                """,
                (schedule_kind, schedule_json_str, scheduled_time_new, now, task_id, user_id),
            )
            await db.commit()
            success = cur.rowcount > 0
            
            # Log action (non-blocking)
            if success:
                # Get task to extract text and priority for logging
                task = await self.get_task(user_id=user_id, task_id=task_id)
                if task:
                    clean_title, priority = parse_priority(task.text)
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
                # Get task to extract text and priority for logging
                task = await self.get_task(user_id=user_id, task_id=task_id)
                if task:
                    clean_title, priority = parse_priority(task.text)
                    await self.log_action(
                        user_id=user_id,
                        action=ACTION_TASK_EDITED,
                        task_id=task_id,
                        payload={'new_text': clean_title, 'priority': priority},
                    )
            
            return success
    
    async def create_project(self, title: str, now: str) -> int:
        """
        Create a new project.
        
        Args:
            title: Project title
            now: ISO datetime string in UTC (use self._now_iso())
        
        Returns:
            Project ID
        """
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO projects (title, status, current_step_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (title, 'active', None, now, now),
            )
            await db.commit()
            return int(cur.lastrowid)
    
    async def add_project_steps(self, project_id: int, list_of_texts: list[str], now: str) -> None:
        """
        Add steps to a project.
        
        Args:
            project_id: Project ID
            list_of_texts: List of step texts (will be assigned order_index 1..N)
            now: ISO datetime string in UTC (use self._now_iso())
        """
        async with aiosqlite.connect(self._db_path) as db:
            for idx, text in enumerate(list_of_texts, start=1):
                await db.execute(
                    """
                    INSERT INTO project_steps (project_id, order_index, text, status, created_at, done_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (project_id, idx, text, 'pending', now, None),
                )
            await db.commit()
    
    async def get_active_project_steps(self) -> list[dict]:
        """
        Get all project steps with status='active', including project title and total step count.
        
        Returns:
            List of dicts with keys: id, project_id, order_index, text, status, created_at, done_at,
            project_title, total_steps
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT 
                    ps.id,
                    ps.project_id,
                    ps.order_index,
                    ps.text,
                    ps.status,
                    ps.created_at,
                    ps.done_at,
                    p.title as project_title,
                    (SELECT COUNT(*) FROM project_steps ps2 WHERE ps2.project_id = ps.project_id) as total_steps
                FROM project_steps ps
                JOIN projects p ON ps.project_id = p.id
                WHERE ps.status = ? AND p.status != 'cancelled';
                """,
                ('active',),
            )
            return [dict(r) for r in await cur.fetchall()]
    async def get_project_step(self, step_id: int) -> Optional[dict]:
        """
        Get a project step by ID.
        
        Args:
            step_id: Step ID
        
        Returns:
            Dict with keys: id, project_id, order_index, text, status, created_at, done_at
            Returns None if step not found
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, project_id, order_index, text, status, created_at, done_at
                FROM project_steps
                WHERE id = ?;
                """,
                (step_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def mark_project_step_completed(self, step_id: int, done_at: str) -> bool:
        """
        Mark a project step as completed.
        
        Args:
            step_id: Step ID
            done_at: ISO datetime string in UTC
        
        Returns:
            True if step was updated, False if not found
        """
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE project_steps
                SET status = ?, done_at = ?
                WHERE id = ?;
                """,
                ('completed', done_at, step_id),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def get_next_pending_step(self, project_id: int, after_order_index: int) -> Optional[dict]:
        """
        Get the next pending step for a project after a given order_index.
        
        Args:
            project_id: Project ID
            after_order_index: Order index to search after
        
        Returns:
            Dict with keys: id, project_id, order_index, text, status, created_at, done_at
            Returns None if no pending step found
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, project_id, order_index, text, status, created_at, done_at
                FROM project_steps
                WHERE project_id = ? AND status = ? AND order_index > ?
                ORDER BY order_index ASC
                LIMIT 1;
                """,
                (project_id, 'pending', after_order_index),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def set_project_step_active(self, step_id: int) -> bool:
        """
        Set a project step status to 'active'.
        
        Args:
            step_id: Step ID
        
        Returns:
            True if step was updated, False if not found
        """
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE project_steps
                SET status = ?
                WHERE id = ?;
                """,
                ('active', step_id),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def update_project_current_step(self, project_id: int, current_step_order: Optional[int], now: str) -> bool:
        """
        Update the current_step_order for a project.
        
        Args:
            project_id: Project ID
            current_step_order: New current step order index, or None
            now: ISO datetime string in UTC
        
        Returns:
            True if project was updated, False if not found
        """
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE projects
                SET current_step_order = ?, updated_at = ?
                WHERE id = ?;
                """,
                (current_step_order, now, project_id),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def activate_first_project_step(self, project_id: int, now: str) -> bool:
        """
        Atomically activate the first step of a project and update the project's current_step_order.
        This ensures consistency: if one operation fails, both are rolled back.
        
        Args:
            project_id: Project ID
            now: ISO datetime string in UTC
        
        Returns:
            True if both operations succeeded, False otherwise
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # Get the first step ID (order_index=1)
            cur = await db.execute(
                """
                SELECT id FROM project_steps
                WHERE project_id = ? AND order_index = 1;
                """,
                (project_id,),
            )
            row = await cur.fetchone()
            if not row:
                return False
            
            first_step_id = row['id']
            
            # Activate the step
            cur = await db.execute(
                """
                UPDATE project_steps
                SET status = ?
                WHERE id = ?;
                """,
                ('active', first_step_id),
            )
            if cur.rowcount == 0:
                return False
            
            # Update project current_step_order
            cur = await db.execute(
                """
                UPDATE projects
                SET current_step_order = ?, updated_at = ?
                WHERE id = ?;
                """,
                (1, now, project_id),
            )
            if cur.rowcount == 0:
                return False
            
            # Commit both operations atomically
            await db.commit()
            return True
    
    async def mark_project_completed(self, project_id: int, now: str) -> bool:
        """
        Mark a project as completed.
        
        Args:
            project_id: Project ID
            now: ISO datetime string in UTC
        
        Returns:
            True if project was updated, False if not found
        """
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE projects
                SET status = ?, current_step_order = NULL, updated_at = ?
                WHERE id = ?;
                """,
                ('completed', now, project_id),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def advance_project_step(self, step_id: int, now: str) -> dict:
        """
        Atomically advance a project step: mark current step completed and activate next pending step.
        If no next step exists, mark project as completed.
        
        Args:
            step_id: ID of the step to advance (must be currently 'active')
            now: ISO datetime string in UTC (use self._now_iso())
        
        Returns:
            Dict with keys:
            - action: "advanced" | "completed_project" | "noop"
            - project_id: int
            - completed_step_id: int
            - new_active_step_id: int | None
        """
        # Validate step exists and is active
        step = await self.get_project_step(step_id)
        if not step:
            raise ValueError(f"Step {step_id} not found")
        
        if step['status'] != 'active':
            # Idempotent: return no-op result if step is not active
            return {
                "action": "noop",
                "project_id": step['project_id'],
                "completed_step_id": step_id,
                "new_active_step_id": None,
            }
        
        project_id = step['project_id']
        current_order_index = step['order_index']
        
        # Perform atomic transaction
        async with aiosqlite.connect(self._db_path) as db:
            # Mark current step completed
            await db.execute(
                """
                UPDATE project_steps
                SET status = ?, done_at = ?
                WHERE id = ?;
                """,
                ('completed', now, step_id),
            )
            
            # Find next pending step
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, project_id, order_index, text, status, created_at, done_at
                FROM project_steps
                WHERE project_id = ? AND status = ? AND order_index > ?
                ORDER BY order_index ASC
                LIMIT 1;
                """,
                (project_id, 'pending', current_order_index),
            )
            next_step_row = await cur.fetchone()
            
            if next_step_row:
                # Activate next step
                next_step = dict(next_step_row)
                next_step_id = next_step['id']
                next_order_index = next_step['order_index']
                
                await db.execute(
                    """
                    UPDATE project_steps
                    SET status = ?
                    WHERE id = ?;
                    """,
                    ('active', next_step_id),
                )
                
                # Update project current_step_order, keep status='active'
                await db.execute(
                    """
                    UPDATE projects
                    SET current_step_order = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (next_order_index, now, project_id),
                )
                
                await db.commit()
                
                return {
                    "action": "advanced",
                    "project_id": project_id,
                    "completed_step_id": step_id,
                    "new_active_step_id": next_step_id,
                }
            else:
                # No more steps: mark project completed
                await db.execute(
                    """
                    UPDATE projects
                    SET status = ?, current_step_order = NULL, updated_at = ?, completed_at = ?
                    WHERE id = ?;
                    """,
                    ('completed', now, now, project_id),
                )
                
                await db.commit()
                
                return {
                    "action": "completed_project",
                    "project_id": project_id,
                    "completed_step_id": step_id,
                    "new_active_step_id": None,
                }
    
    async def get_project(self, project_id: int) -> Optional[dict]:
        """
        Get a project by ID.
        
        Args:
            project_id: Project ID
        
        Returns:
            Dict with keys: id, title, status, current_step_order, created_at, updated_at, completed_at
            Returns None if project not found
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, title, status, current_step_order, created_at, updated_at, completed_at
                FROM projects
                WHERE id = ?;
                """,
                (project_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def get_project_steps(self, project_id: int) -> list[dict]:
        """
        Get all steps for a project, ordered by order_index.
        
        Args:
            project_id: Project ID
        
        Returns:
            List of dicts with keys: id, project_id, order_index, text, status, created_at, done_at
            Ordered by order_index ASC
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, project_id, order_index, text, status, created_at, done_at
                FROM project_steps
                WHERE project_id = ?
                ORDER BY order_index ASC;
                """,
                (project_id,),
            )
            return [dict(r) for r in await cur.fetchall()]
    
    async def delete_project_step(self, step_id: int) -> bool:
        """
        Delete a project step. If the step is active, automatically advances the project.
        
        Args:
            step_id: Step ID to delete
        
        Returns:
            True if step was deleted, False if not found
        """
        # Get step info first
        step = await self.get_project_step(step_id)
        if not step:
            return False
        
        project_id = step['project_id']
        is_active = step['status'] == 'active'
        
        # If active, advance first (this will handle the transition)
        if is_active:
            now = self._now_iso()
            try:
                await self.advance_project_step(step_id=step_id, now=now)
            except ValueError:
                # Step might have been deleted already, continue with deletion
                pass
        
        # Delete the step
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                DELETE FROM project_steps
                WHERE id = ?;
                """,
                (step_id,),
            )
            await db.commit()
            return cur.rowcount > 0
    
    async def cancel_project(self, project_id: int, now: str) -> bool:
        """
        Cancel a project by marking it as 'cancelled'.
        This hides all steps from the active list.
        
        Args:
            project_id: Project ID
            now: ISO datetime string in UTC
        
        Returns:
            True if project was cancelled, False if not found
        """
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                UPDATE projects
                SET status = ?, updated_at = ?
                WHERE id = ?;
                """,
                ('cancelled', now, project_id),
            )
            await db.commit()
            return cur.rowcount > 0