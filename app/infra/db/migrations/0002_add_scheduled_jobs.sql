CREATE TABLE IF NOT EXISTS scheduled_jobs (
  job_id        TEXT PRIMARY KEY,
  user_id       INTEGER NOT NULL,
  agent_id      TEXT NOT NULL,

  job_type      TEXT NOT NULL,
  schedule_kind TEXT NOT NULL,
  schedule_json TEXT,
  payload_json  TEXT,

  status        TEXT NOT NULL DEFAULT 'pending',
  due_at        TEXT NOT NULL,
  completed_at  TEXT,

  run_count     INTEGER NOT NULL DEFAULT 0,
  last_run_at   TEXT,
  last_error    TEXT,

  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,

  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scheduled_due
  ON scheduled_jobs(status, due_at);

CREATE INDEX IF NOT EXISTS idx_scheduled_user
  ON scheduled_jobs(user_id, status, due_at);
