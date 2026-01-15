# app/infra/db/connection.py
from __future__ import annotations

import aiosqlite
from typing import Any, Iterable, Optional, Sequence


class Database:
    """
    Async SQLite helper:
    - opens a new connection per operation (simple + safe)
    - sets row_factory to aiosqlite.Row
    - enables WAL + foreign keys
    """

    def __init__(self, path: str) -> None:
        self._path = path

    async def executescript(self, sql: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.executescript(sql)
            await db.commit()

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute(sql, params)
            await db.commit()

    async def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.executemany(sql, seq_of_params)
            await db.commit()

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[aiosqlite.Row]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON;")
            cur = await db.execute(sql, params)
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON;")
            cur = await db.execute(sql, params)
            return await cur.fetchall()
