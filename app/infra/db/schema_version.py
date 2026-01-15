from __future__ import annotations

from pathlib import Path
from app.infra.db.connection import Database


async def apply_migrations(db: Database, migrations_dir: str, now_iso: str) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
    )

    dir_path = Path(migrations_dir)
    files = sorted([p for p in dir_path.glob("*.sql") if p.is_file()])

    for p in files:
        version = int(p.stem.split("_")[0])

        row = await db.fetchone("SELECT version FROM schema_migrations WHERE version = ?;", (version,))
        if row:
            continue

        sql = p.read_text(encoding="utf-8")
        await db.executescript(sql)

        await db.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?);",
            (version, now_iso),
        )