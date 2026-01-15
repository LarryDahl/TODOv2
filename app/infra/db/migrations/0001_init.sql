PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  user_id      INTEGER PRIMARY KEY,
  created_at   TEXT NOT NULL,
  last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS agents (
  agent_id    TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  category    TEXT NOT NULL,
  is_active   INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_user_settings (
  user_id       INTEGER NOT NULL,
  agent_id      TEXT NOT NULL,
  is_enabled    INTEGER NOT NULL DEFAULT 1,
  settings_json TEXT,
  updated_at    TEXT NOT NULL,
  PRIMARY KEY (user_id, agent_id),
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worklog_entries (
  entry_id      TEXT PRIMARY KEY,
  user_id       INTEGER NOT NULL,
  agent_id      TEXT NOT NULL,
  project       TEXT,
  category      TEXT,
  start_at      TEXT NOT NULL,
  end_at        TEXT,
  break_minutes INTEGER NOT NULL DEFAULT 0,
  description   TEXT NOT NULL,
  metadata_json TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_worklog_user_time
ON worklog_entries(user_id, start_at);

CREATE INDEX IF NOT EXISTS idx_worklog_user_agent_time
ON worklog_entries(user_id, agent_id, start_at);

CREATE INDEX IF NOT EXISTS idx_worklog_open_entries
ON worklog_entries(user_id, agent_id)
WHERE end_at IS NULL;

CREATE TABLE IF NOT EXISTS events (
  event_id     TEXT PRIMARY KEY,
  user_id      INTEGER NOT NULL,
  agent_id     TEXT NOT NULL,
  event_type   TEXT NOT NULL,
  payload_json TEXT,
  created_at   TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_user_time
ON events(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_events_user_agent_time
ON events(user_id, agent_id, created_at);
