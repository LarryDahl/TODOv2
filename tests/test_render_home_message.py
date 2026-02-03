"""
Tests for render_home_message: suggestions are fetched in one batch (no N+1).

Uses a temporary DB file. Verifies that get_tasks_by_ids is called exactly once
for the suggestion task ids, not get_task in a loop.
Run with: python -m pytest tests/test_render_home_message.py -v
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Optional

from app.db import TasksRepo
from app.handlers.common import render_home_message


def _temp_db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


class SpyTasksRepo:
    """Wraps TasksRepo and records get_tasks_by_ids / get_task call counts and args."""

    def __init__(self, real: TasksRepo) -> None:
        self._real = real
        self.get_tasks_by_ids_calls: list[tuple[int, list[int]]] = []
        self.get_task_calls: list[tuple[int, int]] = []

    def __getattr__(self, name: str):
        """Delegate all other attributes to the real repo."""
        return getattr(self._real, name)

    async def get_tasks_by_ids(
        self, user_id: int, ids: list[int]
    ) -> dict[int, "object"]:
        self.get_tasks_by_ids_calls.append((user_id, list(ids)))
        return await self._real.get_tasks_by_ids(user_id, ids)

    async def get_task(
        self, user_id: int, task_id: int
    ) -> Optional["object"]:
        self.get_task_calls.append((user_id, task_id))
        return await self._real.get_task(user_id, task_id)


async def _run_with_db(test_fn):
    path = _temp_db_path()
    try:
        repo = TasksRepo(path)
        await repo.init()
        await test_fn(repo)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_render_home_message_fetches_suggestions_in_single_batch():
    """render_home_message must call get_tasks_by_ids exactly once for suggestion tasks (no N+1)."""

    async def run(repo: TasksRepo):
        user_id = 1
        # Create backlog tasks and fill suggestion slots so we have several suggestion ids
        for i in range(5):
            await repo.add_task(user_id, f"Backlog {i}")
        now = repo._now_iso()
        await repo.fill_suggestion_slots(user_id, now)
        slot_ids = await repo.get_suggestion_slots(user_id)
        ids_filled = [tid for tid in slot_ids if tid is not None]
        assert len(ids_filled) >= 1, "need at least one suggestion slot filled to test batch fetch"

        spy = SpyTasksRepo(repo)
        text, keyboard = await render_home_message(
            user_id=user_id,
            repo=spy,
            force_refresh=False,
            shuffle_suggestions=False,
        )

        # Must use one batch query for suggestion tasks, not N get_task calls
        assert len(spy.get_tasks_by_ids_calls) == 1, (
            "get_tasks_by_ids should be called exactly once (no N+1)"
        )
        uid, ids = spy.get_tasks_by_ids_calls[0]
        assert uid == user_id
        assert set(ids) == set(ids_filled), "should fetch exactly the suggestion slot task ids in one go"

        # get_task must not be used for fetching suggestion tasks (would be N+1)
        suggestion_ids = set(ids_filled)
        get_task_for_suggestions = [
            (u, tid) for u, tid in spy.get_task_calls if tid in suggestion_ids
        ]
        assert len(get_task_for_suggestions) == 0, (
            "get_task must not be called for suggestion task ids (N+1)"
        )

    asyncio.run(_run_with_db(run))


def test_render_home_message_returns_text_and_keyboard():
    """render_home_message returns (header_text, keyboard) with non-empty text."""

    async def run(repo: TasksRepo):
        user_id = 1
        await repo.get_user_settings(user_id)  # ensure user exists
        text, keyboard = await render_home_message(
            user_id=user_id,
            repo=repo,
            force_refresh=False,
            shuffle_suggestions=False,
        )
        assert isinstance(text, str)
        assert len(text) > 0
        assert keyboard is not None

    asyncio.run(_run_with_db(run))
