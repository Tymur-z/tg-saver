import asyncio
import json
import sqlite3
from datetime import datetime

DB_PATH = "/home/ec2-user/tg-forwarder/data/forwarder.db"

def run_migration():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # 1. Create table chat_daily_memories if not exists
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_daily_memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        date_str TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        key_facts TEXT NOT NULL DEFAULT '[]',
        last_msg_id INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(chat_id, date_str)
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_memories_date ON chat_daily_memories(chat_id, date_str);")
    
    # 2. Update app_state settings for Richard
    settings = {
        "llm_companion_persona": "student",
        "llm_temperature": "0.7",
        "llm_max_tokens": "800",
        "llm_context_limit": "40",
    }
    for k, v in settings.items():
        cur.execute("""
        INSERT INTO app_state (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
        """, (k, v))
        
    # 3. Seed daily memory for the active group chats
    today_str = datetime.now().strftime("%Y-%m-%d")
    chats = [-1002255156347, -1004479083851, -1004321632420]
    
    summary = (
        "3 ноября 2026: MixaRed приехал в гости к Тимуру домой, занял его комп ('шкаф 2 на 2'). "
        "Миша переоделся в костюм горничной/кошкодевочки с ушками, хвостом и чулками прямо у Тимура дома, фоткался и слал в чат. "
        "Абисс (Миша Пилот) выпал в осадок от увиденного. Тимур уговаривал Мишу снять наряд до прихода мамы. "
        "Миша спрашивал про ДДОС Вардогс, стебал Тимура за никнейм 'Тимур2000' против 'МСВП2055', и весь день пытался разводить Ричарда детскими вопросами про фуфлыжников и школу."
    )
    key_facts = json.dumps([
        "MixaRed сидит у Тимура дома и играет на его ПК",
        "MixaRed надел ушки и хвост горничной/кошкодевочки у Тимура дома, чат угарал и был в шоке",
        "MixaRed спамит вопросами про фуфлыжников в тюрьме и опросниками",
        "Тимур передал пас Ричарду, чтобы заткнуть провокации Миши",
        "Тимур @Tymur2000 — создатель бота и админ, с ним общаемся на равных без клоунады и подхалимажа"
    ], ensure_ascii=False)
    
    for cid in chats:
        cur.execute("""
        INSERT INTO chat_daily_memories (chat_id, date_str, summary, key_facts, last_msg_id, updated_at)
        VALUES (?, ?, ?, ?, 999999, CURRENT_TIMESTAMP)
        ON CONFLICT(chat_id, date_str) DO UPDATE SET
            summary = excluded.summary,
            key_facts = excluded.key_facts,
            updated_at = CURRENT_TIMESTAMP;
        """, (cid, today_str, summary, key_facts))
        
    conn.commit()
    conn.close()
    print("Migration and memory seeding completed successfully.")

if __name__ == "__main__":
    run_migration()
