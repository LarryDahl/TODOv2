"""
Handlers module - combines all handler routers.
"""
from __future__ import annotations

from aiogram import Router

from app.handlers import add_task, deadline, schedule, suggestions, tasks, views  # noqa: F401

# Create main router
router = Router()

# Include all sub-routers
router.include_router(views.router)
router.include_router(tasks.router)
router.include_router(deadline.router)
router.include_router(schedule.router)
router.include_router(add_task.router)
router.include_router(suggestions.router)

# Export common types for use in other modules
from app.handlers.common import CtxKeys, Flow

__all__ = ["router", "Flow", "CtxKeys"]
