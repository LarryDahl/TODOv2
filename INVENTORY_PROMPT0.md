# PROMPT 0 — INVENTORY (TODOv2 / Dotolista)

**No code changes.** This document maps the current architecture.

---

## 1) Python entrypoint(s) for the Telegram bot

- **`app/main.py`** — Single entrypoint. `asyncio.run(main())` runs:
  - `load_settings()` from `app/config.py`
  - `TasksRepo(settings.db_path)` and `await repo.init()`
  - `Bot` + `Dispatcher` (MemoryStorage) + `dp.include_router(router)` from `app.handlers`
  - `await dp.start_polling(bot, repo=repo)`

---

## 2) DB access layer (SQLite), tasks schema, migration pattern

- **`app/db.py`** — Single DB layer. Uses **aiosqlite**.
- **Migration pattern:** In `TasksRepo.init()`: `CREATE TABLE IF NOT EXISTS` plus **PRAGMA table_info** checks; missing columns are added with `ALTER TABLE ... ADD COLUMN`. No separate migration scripts; all migrations are inline in `init()`.
- **Tasks table** and other relevant table schemas are listed in the “Exact SQLite schema” section below.

---

## 3) Task listing UI and inline keyboards

- **Single place for main (home) view:**
  - **`app/handlers/common.py`** — `render_home_message(user_id, repo, force_refresh)` is the **only** function that builds the main menu content. It:
    - Fetches completed (3), active tasks, active project steps, settings
    - Calls **`app/ui.py`**: `render_home_text(...)` for header and **`build_home_keyboard(...)`** for the keyboard
  - All flows that return “home” call **`return_to_main_menu(...)`** in `common.py`, which uses `render_home_message()` and then edits/sends the message.
- **Inline keyboards are built in `app/ui.py`:**
  - **`build_home_keyboard(completed_tasks, active_tasks, active_steps)`** — Main message: completed (3) with `completed:restore:{id}`, active task rows with `t:{task_id}`, Projektit button, bottom row [+][stats][settings][refresh]
  - Other keyboards: `settings_kb`, `edit_kb`, `task_action_kb`, `task_edit_menu_kb`, `plus_menu_kb`, `projects_list_kb`, `project_detail_view_kb`, etc.

---

## 4) Task statuses and where they are set/changed

- **No explicit `status` column on `tasks`.** Semantics:
  - **Active:** Row exists in **`tasks`** (user_id, task_id). Shown in main list.
  - **Done:** Row removed from `tasks`; a row is inserted in **`task_events`** with `action = 'completed'` (see `constants.TASK_ACTION_COMPLETED`). Shown in “3 done” via `list_completed_tasks()` (from `task_events`).
  - **Deleted:** Same as done but `task_events.action = 'deleted'`. Restore is only from “completed” events.
- **Where changed:**
  - **Done:** `app/db.py` — `complete_task(user_id, task_id)`: logs event, then **DELETE** from `tasks`. Handlers: `app/handlers/tasks.py` — `cb_done()` (callbacks `task:done:<id>`, `t:<id>`, and `ps:<step_id>` for project steps).
  - **Undo/Restore:** `app/db.py` — `restore_completed_task(user_id, event_id)`: reads `task_events` by event `id`, re-inserts into `tasks`, deletes that event row. Handlers: `app/handlers/tasks.py` — `cb_restore_completed()` (`completed:restore:<event_id>`); also `app/handlers/views.py` (done view) and `app/handlers/suggestions.py`.
  - **Delete (with reason):** `app/db.py` — `delete_task_with_log()`: logs to `task_events` (deleted) and **DELETE** from `tasks`. Handlers: `app/handlers/tasks.py` — delete flow (`task:del:<id>` → `waiting_delete_reason` → `msg_delete_reason`).
  - **Edit (text/priority/deadline):** `app/db.py` — `update_task()`, `update_task_meta()`. Handlers in `tasks.py` (edit menu, edit text, priority up/down, deadline, etc.).

---

## 5) Priority via “!” — parsing and storage

- **`app/priority.py`**:
  - **`parse_priority(text)`** → `(clean_title, priority)`. Counts **trailing** `!` only; priority = min(count, 5); clean_title is text with trailing `!` removed.
  - **`render_title_with_priority(clean_title, priority)`** — Appends `!` * priority for display.
- **Storage:** In **`app/db.py`**:
  - **`tasks`** table: columns **`priority`** (INTEGER 0–5) and **`priority_source`** (e.g. `'bang_suffix'`).
  - **`add_task()`** and **`update_task()`** call `parse_priority(text)` and persist `priority` and cleaned `text`.

---

## 6) Time handling (timezone, “now”, clock)

- **`app/clock.py`** — **SystemClock** (static helpers):
  - **`now_utc()`**, **`now_helsinki()`** (legacy), **`now_user_tz(timezone)`**
  - **`now_helsinki_iso()`**, **`now_user_tz_iso(timezone)`** — Return UTC ISO strings for storage.
  - **`add_hours_helsinki(hours)`**, **`add_hours_user_tz(hours, timezone)`** — For deadlines/scheduling.
  - Uses **zoneinfo** (or backports.zoneinfo) for Europe/Helsinki and user timezone.
- **`app/db.py`** — **`_now_iso()`**: `datetime.now(timezone.utc).isoformat()` for DB timestamps.
- **`app/utils.py`** — Date/time parsing helpers (e.g. `parse_time_input`, `get_date_offset_days`).
- **User timezone:** Stored in **`user_settings.timezone`** (e.g. `'Europe/Helsinki'`). Used in `count_completed_tasks_today()` and anywhere user-facing “today” is needed.

---

## Key files (short list)

| File | Responsibility |
|------|----------------|
| **app/main.py** | Bot entrypoint; load config, init DB, run polling. |
| **app/config.py** | Load settings (bot token, db path). |
| **app/db.py** | SQLite access; TasksRepo; tasks, task_events, user_settings, projects, project_steps, suggestion_log, action_log; migrations in init(). |
| **app/constants.py** | TASK_ACTION_COMPLETED/DELETED; ACTION_TASK_* for action_log. |
| **app/priority.py** | parse_priority (trailing !), render_title_with_priority. |
| **app/priority_compute.py** | compute_priority (effective priority for sorting). |
| **app/clock.py** | SystemClock: now_utc, now_user_tz, add_hours_*, ISO strings. |
| **app/utils.py** | parse_callback_data, parse_int_safe, time/date helpers. |
| **app/ui.py** | All inline keyboards and header/text builders (build_home_keyboard, render_home_text, settings, edit, stats, projects, etc.). |
| **app/handlers/common.py** | render_home_message(), return_to_main_menu(); Flow (FSM), CtxKeys. |
| **app/handlers/views.py** | home, refresh, settings, edit view, done/deleted views, stats, projects list/detail, proj step toggle. |
| **app/handlers/tasks.py** | complete, restore, delete flow, task edit menu, priority, deadline, project detail (p:), ps:del. |
| **app/handlers/project_edit.py** | edit projects/steps, delete project, step CRUD/reorder/rewrite. |
| **app/handlers/add_task.py** | Plus menu, add task/project flows. |
| **app/handlers/suggestions.py** | Suggestion view and accept/snooze. |
| **app/handlers/deadline.py**, **schedule.py** | Deadline/schedule flows. |
| **app/suggestions.py** | Suggestion scoring (score_suggestion). |

---

## Exact current SQLite schema

### tasks

- **PROMPT 2:** `tags` (TEXT NOT NULL DEFAULT '[]', JSON array string). Migrations add `status`, `cooldown_until`, `tags` if missing.

```sql
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
CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
```

### task_events

```sql
CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    task_id INTEGER,
    action TEXT NOT NULL,         -- 'completed' | 'deleted'
    text TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_events_user_id ON task_events(user_id);
```

### user_settings

- **PROMPT 2:** `day_start_time`, `day_end_time` (TEXT, nullable) for preferred time window (e.g. "09:00", "17:00"). Migrations add `active_card_message_id`, `day_start_time`, `day_end_time` if missing.

```sql
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    timezone TEXT NOT NULL DEFAULT 'Europe/Helsinki',
    show_done_in_home BOOLEAN NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
```

### progress_log (PROMPT 2)

```sql
CREATE TABLE IF NOT EXISTS progress_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    task_id INTEGER,
    amount REAL NOT NULL DEFAULT 1,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_progress_log_user_at ON progress_log(user_id, at);
```
- Written by `complete_task()` (source = `task_completed`) for progress/XP hooks.

### action_log

```sql
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    task_id INTEGER,
    payload TEXT,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_log_user_at ON action_log(user_id, at);
CREATE INDEX IF NOT EXISTS idx_action_log_action ON action_log(action);
```

### suggestion_log

```sql
CREATE TABLE IF NOT EXISTS suggestion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    action TEXT NOT NULL,  -- 'accepted' | 'snoozed' | 'ignored'
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_suggestion_log_user_event ON suggestion_log(user_id, event_id);
```

### projects

```sql
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    current_step_order INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
```

### project_steps

```sql
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
CREATE INDEX IF NOT EXISTS idx_project_steps_project_id ON project_steps(project_id);
CREATE INDEX IF NOT EXISTS idx_project_steps_project_status ON project_steps(project_id, status);
CREATE INDEX IF NOT EXISTS idx_project_steps_project_order ON project_steps(project_id, order_index);
```

---

*End of PROMPT 0 — INVENTORY.*
