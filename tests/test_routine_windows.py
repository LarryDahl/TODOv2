"""
Unit tests for routine time windows: defaults, validation, and boundary logic.

Run with: python -m pytest tests/test_routine_windows.py -v
Or:       python tests/test_routine_windows.py  (if run from project root)
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import patch

from app.clock import SystemClock
from app.db import DEFAULT_EVENING_END, DEFAULT_EVENING_START, DEFAULT_MORNING_END, DEFAULT_MORNING_START, TasksRepo
from app.utils import time_in_window


# ----- time_in_window (pure, no DB) -----


def test_time_in_window_boundary_start_inclusive():
    """05:30 is inside window [05:30, 07:30)."""
    assert time_in_window(5, 30, "05:30", "07:30") is True


def test_time_in_window_boundary_just_before_end_inclusive():
    """07:29 is inside window [05:30, 07:30)."""
    assert time_in_window(7, 29, "05:30", "07:30") is True


def test_time_in_window_boundary_end_exclusive():
    """07:30 is outside window [05:30, 07:30) (end is exclusive)."""
    assert time_in_window(7, 30, "05:30", "07:30") is False


def test_time_in_window_mid_window():
    """06:15 is inside [05:30, 07:30)."""
    assert time_in_window(6, 15, "05:30", "07:30") is True


def test_time_in_window_before_start():
    """05:00 is outside [05:30, 07:30)."""
    assert time_in_window(5, 0, "05:30", "07:30") is False


def test_time_in_window_invalid_start_returns_false():
    """Invalid start_str -> False."""
    assert time_in_window(6, 0, "invalid", "07:30") is False


def test_time_in_window_invalid_end_returns_false():
    """Invalid end_str -> False."""
    assert time_in_window(6, 0, "05:30", "25:00") is False


def test_time_in_window_evening_example():
    """20:00 and 21:30 inside [20:00, 22:00); 22:00 outside."""
    assert time_in_window(20, 0, "20:00", "22:00") is True
    assert time_in_window(21, 30, "20:00", "22:00") is True
    assert time_in_window(22, 0, "20:00", "22:00") is False


# ----- get_routine_windows defaults (async, in-memory DB) -----


def test_get_routine_windows_returns_defaults_when_user_has_no_settings():
    """User with no settings (or old user without migration) gets default window values."""
    async def run():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            repo = TasksRepo(path)
            await repo.init()
            # User 999 has no row in user_settings; get_routine_windows uses get_user_settings
            # which creates a row with NULL for the 4 window columns -> defaults applied
            windows = await repo.get_routine_windows(999)
            assert windows["morning_start"] == DEFAULT_MORNING_START
            assert windows["morning_end"] == DEFAULT_MORNING_END
            assert windows["evening_start"] == DEFAULT_EVENING_START
            assert windows["evening_end"] == DEFAULT_EVENING_END
        finally:
            if os.path.exists(path):
                os.unlink(path)

    asyncio.run(run())


# ----- set_morning_window / set_evening_window reject start >= end -----


def test_set_morning_window_rejects_start_ge_end():
    """set_morning_window(..., start, end) returns False when start >= end."""
    async def run():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            repo = TasksRepo(path)
            await repo.init()
            user_id = 1
            # Ensure user has a row (get_user_settings creates it)
            await repo.get_user_settings(user_id)
            # end before start
            ok = await repo.set_morning_window(user_id, "07:30", "05:30")
            assert ok is False
            # start == end
            ok = await repo.set_morning_window(user_id, "06:00", "06:00")
            assert ok is False
            # valid
            ok = await repo.set_morning_window(user_id, "05:30", "07:30")
            assert ok is True
        finally:
            if os.path.exists(path):
                os.unlink(path)

    asyncio.run(run())


def test_set_evening_window_rejects_start_ge_end():
    """set_evening_window(..., start, end) returns False when start >= end."""
    async def run():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            repo = TasksRepo(path)
            await repo.init()
            user_id = 1
            await repo.get_user_settings(user_id)
            ok = await repo.set_evening_window(user_id, "22:00", "20:00")
            assert ok is False
            ok = await repo.set_evening_window(user_id, "21:00", "21:00")
            assert ok is False
            ok = await repo.set_evening_window(user_id, "20:00", "22:00")
            assert ok is True
        finally:
            if os.path.exists(path):
                os.unlink(path)

    asyncio.run(run())


# ----- is_in_morning_window boundaries (mocked clock) -----


def test_is_in_morning_window_boundaries():
    """is_in_morning_window uses get_routine_windows and clock; at 05:30 and 07:29 True, at 07:30 False."""
    async def run():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            repo = TasksRepo(path)
            await repo.init()
            user_id = 1
            await repo.get_user_settings(user_id)
            # User has default window 05:30–07:30 (end exclusive)

            with patch.object(SystemClock, "now_user_tz") as mock_now:
                # 05:30 -> inside [05:30, 07:30)
                mock_now.return_value = datetime(2025, 2, 3, 5, 30)
                assert await repo.is_in_morning_window(user_id) is True
                # 07:29 -> inside
                mock_now.return_value = datetime(2025, 2, 3, 7, 29)
                assert await repo.is_in_morning_window(user_id) is True
                # 07:30 -> outside (end exclusive)
                mock_now.return_value = datetime(2025, 2, 3, 7, 30)
                assert await repo.is_in_morning_window(user_id) is False
        finally:
            if os.path.exists(path):
                os.unlink(path)

    asyncio.run(run())


if __name__ == "__main__":
    test_time_in_window_boundary_start_inclusive()
    test_time_in_window_boundary_just_before_end_inclusive()
    test_time_in_window_boundary_end_exclusive()
    test_time_in_window_mid_window()
    test_time_in_window_before_start()
    test_time_in_window_invalid_start_returns_false()
    test_time_in_window_invalid_end_returns_false()
    test_time_in_window_evening_example()
    test_get_routine_windows_returns_defaults_when_user_has_no_settings()
    test_set_morning_window_rejects_start_ge_end()
    test_set_evening_window_rejects_start_ge_end()
    test_is_in_morning_window_boundaries()
    print("All tests passed.")
    sys.exit(0)
