from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class TasksFlow(StatesGroup):
    add_title = State()
    edit_title = State()
