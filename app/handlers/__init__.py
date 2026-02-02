"""
Handlers module - combines all handler routers.
"""
from __future__ import annotations

from aiogram import Router

from app.handlers import add_task, deadline, project_edit, schedule, suggestions, tasks, views, text_messages  # noqa: F401

# Create main router
router = Router()

# Include all sub-routers
# IMPORTANT: text_messages.router must be included LAST so that FSM state handlers
# get priority over the catch-all text message handler
router.include_router(views.router)
router.include_router(tasks.router)
router.include_router(deadline.router)
router.include_router(schedule.router)
router.include_router(add_task.router)
router.include_router(project_edit.router)
router.include_router(suggestions.router)
router.include_router(text_messages.router)  # Must be last (catch-all for text messages)

# Export common types for use in other modules
from app.handlers.common import CtxKeys, Flow

__all__ = ["router", "Flow", "CtxKeys"]
