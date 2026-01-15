from dataclasses import dataclass
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_telegram_id: int
    timezone: str
    db_path: Path


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    owner_id = int(os.getenv("OWNER_TELEGRAM_ID", "0").strip())
    tz = os.getenv("TZ", "Europe/Helsinki").strip()
    db_raw = os.getenv("DB_PATH", "data/lifeops.db").strip()

    if not bot_token:
        raise RuntimeError("BOT_TOKEN missing in .env")
    if owner_id <= 0:
        raise RuntimeError("OWNER_TELEGRAM_ID missing/invalid in .env")

    # TÄRKEÄ: db_path ei vielä absoluuttinen
    return Settings(
        bot_token=bot_token,
        owner_telegram_id=owner_id,
        timezone=tz,
        db_path=Path(db_raw),
    )
