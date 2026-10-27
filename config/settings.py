from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Set

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = ...
    OWNER_ID: int = 0
    ADMIN_IDS: str = ""

    DATABASE_PATH: str = "data/forwarder.db"

    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/bot.log"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    FORWARD_RATE_LIMIT_PER_MINUTE: int = 20
    QUEUE_MAX_SIZE: int = 500
    ALBUM_DEBOUNCE_SECONDS: float = 0.8
    MAX_RETRY_ATTEMPTS: int = 3

    ANALYTICS_ENABLED: bool = True
    DATA_RETENTION_DAYS: int = 30
    MIN_MESSAGES_FOR_ANALYSIS: int = 10
    DISCARD_RAW_TEXT_AFTER_ANALYSIS: bool = True

    ACCESS_PASSWORD: str = "changeme"
    PASSWORD_REQUIRED: bool = True

    LLM_ENABLED: bool = False
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def normalize_admin_ids(cls, v: object) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return ",".join(str(x) for x in v)
        return str(v)

    @property
    def admin_id_list(self) -> List[int]:
        ids: Set[int] = set()
        if self.OWNER_ID > 0:
            ids.add(self.OWNER_ID)
        if self.ADMIN_IDS:
            for part in self.ADMIN_IDS.split(","):
                cleaned = part.strip()
                if cleaned.isdigit():
                    ids.add(int(cleaned))
        return sorted(list(ids))

    def is_admin(self, user_id: int) -> bool:
        if self.OWNER_ID > 0 and user_id == self.OWNER_ID:
            return True
        return user_id in self.admin_id_list

    def ensure_directories(self) -> None:
        db_file = Path(self.DATABASE_PATH)
        if db_file.parent:
            db_file.parent.mkdir(parents=True, exist_ok=True)

        log_file = Path(self.LOG_FILE)
        if log_file.parent:
            log_file.parent.mkdir(parents=True, exist_ok=True)


class SensitiveDataFilter(logging.Filter):

    def __init__(self, bot_token: str | None = None) -> None:
        super().__init__()
        self.bot_token = bot_token

    def filter(self, record: logging.LogRecord) -> bool:
        if self.bot_token and self.bot_token in record.getMessage():
            record.msg = record.msg.replace(self.bot_token, "[REDACTED_BOT_TOKEN]")
        return True


def setup_logging(settings: Settings) -> logging.Logger:
    settings.ensure_directories()

    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(level)

    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SensitiveDataFilter(settings.BOT_TOKEN))
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        filename=settings.LOG_FILE,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SensitiveDataFilter(settings.BOT_TOKEN))
    logger.addHandler(file_handler)

    return logging.getLogger("forwarder")
