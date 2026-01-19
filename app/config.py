from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: str = "data/todo.db"


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    if not token:
        raise RuntimeError("Missing BOT_TOKEN (or TELEGRAM_BOT_TOKEN) in environment.")
    db_path = os.getenv("DB_PATH") or "data/todo.db"
    return Settings(bot_token=token, db_path=db_path)
