"""
Tests for shuffle_suggestion_slots: slots change when backlog > need_suggestions.

Uses a temporary DB file (in-memory SQLite would use a new DB per connection).
Run with: python -m pytest tests/test_suggestions_shuffle.py -v
"""
from __future__ import annotations

import asyncio
import os
import random
import tempfile

from app.db import TasksRepo


def _temp_db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


async def _run_with_db(test_fn):
    path = _temp_db_path()
    try:
        repo = TasksRepo(path)
        await repo.init()
        await test_fn(repo)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_shuffle_suggestion_slots_fills_slots_from_backlog():
    """When backlog >= need_suggestions, slots 0..need_suggestions-1 get task ids from backlog."""

    async def run(repo: TasksRepo):
        user_id = 1
        now = repo._now_iso()
        # Add 12 backlog tasks (no active)
        for i in range(12):
            await repo.add_task(user_id, f"Backlog task {i}")
        need_suggestions = 9
        await repo.shuffle_suggestion_slots(user_id, now, need_suggestions)
        slots = await repo.get_suggestion_slots(user_id)
        # First 9 slots should have task ids, rest None
        filled = [tid for tid in slots[:need_suggestions] if tid is not None]
        rest = slots[need_suggestions:]
        assert len(filled) == need_suggestions
        assert all(tid is None for tid in rest)
        # All filled ids should be from our backlog (we have 12 tasks, all backlog)
        tasks = await repo.list_tasks(user_id, limit=20)
        backlog_ids = {t.id for t in tasks}
        assert set(filled).issubset(backlog_ids)
        assert len(set(filled)) == need_suggestions  # no duplicates

    asyncio.run(_run_with_db(run))


def test_shuffle_suggestion_slots_changes_order_when_backlog_gt_need():
    """With backlog > need_suggestions, two shuffles with different seeds yield different slot assignments."""

    async def run(repo: TasksRepo):
        user_id = 1
        now = repo._now_iso()
        for i in range(15):
            await repo.add_task(user_id, f"Task {i}")
        need_suggestions = 9

        random.seed(42)
        await repo.shuffle_suggestion_slots(user_id, now, need_suggestions)
        slots_a = await repo.get_suggestion_slots(user_id)
        order_a = tuple(slots_a[i] for i in range(need_suggestions))

        random.seed(123)
        await repo.shuffle_suggestion_slots(user_id, now, need_suggestions)
        slots_b = await repo.get_suggestion_slots(user_id)
        order_b = tuple(slots_b[i] for i in range(need_suggestions))

        # Different seeds should produce different order (very unlikely to be equal by chance)
        assert order_a != order_b, "shuffle_suggestion_slots should change slot assignment with different random seed"
        # Both should still have exactly need_suggestions filled
        assert sum(1 for t in slots_a[:need_suggestions] if t is not None) == need_suggestions
        assert sum(1 for t in slots_b[:need_suggestions] if t is not None) == need_suggestions

    asyncio.run(_run_with_db(run))


def test_shuffle_suggestion_slots_clears_excess_slots():
    """Slots from need_suggestions to 8 are cleared."""

    async def run(repo: TasksRepo):
        user_id = 1
        now = repo._now_iso()
        await repo.add_task(user_id, "One")
        await repo.add_task(user_id, "Two")
        need_suggestions = 2
        await repo.shuffle_suggestion_slots(user_id, now, need_suggestions)
        slots = await repo.get_suggestion_slots(user_id)
        assert slots[0] is not None
        assert slots[1] is not None
        for i in range(2, 9):
            assert slots[i] is None, f"Slot {i} should be cleared"

    asyncio.run(_run_with_db(run))
