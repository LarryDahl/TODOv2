# -*- coding: utf-8 -*-
"""Domain repositories. Public API: use app.db.TasksRepo and app.db.Task."""

from app.repos.base import BaseRepo
from app.repos.tasks_repo import TasksRepoImpl
from app.repos.suggestions_repo import SuggestionsRepo
from app.repos.stats_repo import StatsRepo
from app.repos.projects_repo import ProjectsRepo

__all__ = [
    "BaseRepo",
    "TasksRepoImpl",
    "SuggestionsRepo",
    "StatsRepo",
    "ProjectsRepo",
]
