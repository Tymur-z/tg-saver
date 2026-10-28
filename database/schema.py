from __future__ import annotations

import logging
import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    chat_type TEXT NOT NULL,
    username TEXT,
    is_source BOOLEAN NOT NULL DEFAULT 0,
    is_destination BOOLEAN NOT NULL DEFAULT 0,
    registered_by_user_id INTEGER NOT NULL DEFAULT 0,
    profanity_filter_enabled BOOLEAN NOT NULL DEFAULT 0,
    profanity_warn_enabled BOOLEAN NOT NULL DEFAULT 0,
    profanity_delete_enabled BOOLEAN NOT NULL DEFAULT 0,
    chat_ai_enabled BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_chat_id INTEGER NOT NULL,
    destination_chat_id INTEGER NOT NULL,
    created_by_user_id INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'forward',
    filter_media_types TEXT DEFAULT '[]',
    filter_keywords TEXT DEFAULT '[]',
    filter_exclude_keywords TEXT DEFAULT '[]',
    clean_links BOOLEAN NOT NULL DEFAULT 0,
    clean_tags BOOLEAN NOT NULL DEFAULT 0,
    clean_mentions BOOLEAN NOT NULL DEFAULT 0,
    append_source_link BOOLEAN NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE,
    FOREIGN KEY (destination_chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE,
    UNIQUE(source_chat_id, destination_chat_id)
);

CREATE TABLE IF NOT EXISTS forward_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL,
    source_chat_id INTEGER NOT NULL,
    source_message_id INTEGER NOT NULL,
    dest_chat_id INTEGER NOT NULL,
    dest_message_id INTEGER,
    media_group_id TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE,
    UNIQUE(route_id, source_chat_id, source_message_id)
);
CREATE INDEX IF NOT EXISTS idx_forward_lookup ON forward_logs(source_chat_id, source_message_id);
CREATE INDEX IF NOT EXISTS idx_forward_created ON forward_logs(created_at);

CREATE TABLE IF NOT EXISTS user_style_profiles (
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    is_owner BOOLEAN NOT NULL DEFAULT 0,
    sample_count INTEGER NOT NULL DEFAULT 0,
    total_words INTEGER NOT NULL DEFAULT 0,
    total_characters INTEGER NOT NULL DEFAULT 0,
    avg_sentence_len REAL NOT NULL DEFAULT 0.0,
    lexical_richness REAL NOT NULL DEFAULT 0.0,
    punctuation_stats TEXT NOT NULL DEFAULT '{}',
    emoji_stats TEXT NOT NULL DEFAULT '{}',
    formality_markers TEXT NOT NULL DEFAULT '{}',
    activity_hours TEXT NOT NULL DEFAULT '{}',
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, chat_id)
);

CREATE TABLE IF NOT EXISTS privacy_settings (
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    is_excluded BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_type, entity_id)
);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    role TEXT NOT NULL DEFAULT 'user', -- 'owner', 'admin', 'user', 'guest'
    is_authorized BOOLEAN NOT NULL DEFAULT 0,
    is_blocked BOOLEAN NOT NULL DEFAULT 0,
    authorized_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db(conn: aiosqlite.Connection) -> None:
    logger.info("Initializing database schema...")
    await conn.executescript(SCHEMA_SQL)

    for col, col_type, default in [
        ("clean_links", "BOOLEAN", "0"),
        ("clean_tags", "BOOLEAN", "0"),
        ("clean_mentions", "BOOLEAN", "0"),
        ("append_source_link", "BOOLEAN", "0"),
        ("created_by_user_id", "INTEGER", "0"),
    ]:
        try:
            if default == "NULL":
                await conn.execute(f"ALTER TABLE routes ADD COLUMN {col} {col_type} DEFAULT NULL")
            else:
                await conn.execute(f"ALTER TABLE routes ADD COLUMN {col} {col_type} NOT NULL DEFAULT {default}")
        except Exception:
            pass

    for col, col_type, default in [
        ("registered_by_user_id", "INTEGER", "0"),
        ("profanity_filter_enabled", "BOOLEAN", "0"),
        ("profanity_warn_enabled", "BOOLEAN", "0"),
        ("profanity_delete_enabled", "BOOLEAN", "0"),
        ("chat_ai_enabled", "BOOLEAN", "0"),
    ]:
        try:
            await conn.execute(f"ALTER TABLE chats ADD COLUMN {col} {col_type} NOT NULL DEFAULT {default}")
        except Exception:
            pass

    try:
        await conn.execute("INSERT OR IGNORE INTO app_state (key, value) VALUES ('access_password', 'changeme')")
        await conn.execute("INSERT OR IGNORE INTO app_state (key, value) VALUES ('password_required', '1')")
    except Exception:
        pass

    await conn.commit()
    logger.info("Database schema initialized successfully.")
