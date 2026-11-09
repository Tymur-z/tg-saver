import json
import sqlite3
from datetime import datetime

DB_PATH = "/home/ec2-user/tg-forwarder/data/forwarder.db"

def seed_memory():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    today_str = datetime.now().strftime("%Y-%m-%d")  # 2026-11-04
    
    summary = (
        "4 ноября 2026: Утром Соль записала кружок, как спешит пешком в школу (никто не подвёз) "
        "и молится, чтобы её божественная укладка на скорую руку не распалась по дороге. "
        "Ночью и накануне обсуждали чёрную вязаную балаклаву и маски (Миша Пилот шутил про колготы на голову), "
        "MixaRed кидал тиктоки с идеями, а Тимур присылал фото с комментарием 'попробовать можно'. "
        "Вчера (3 ноября) MixaRed сидел у Тимура дома и наряжался в ушки и хвост кошкодевочки/горничной у компа Тимура."
    )
    key_facts = json.dumps([
        "Утром 4 ноября Соль записала кружок: спешит пешком в школу и переживает за свою укладку",
        "Ночью обсуждали чёрную вязаную балаклаву и маски (Миша Пилот шутил про колготы на голову)",
        "MixaRed кидает тиктоки с идеями образов и масок",
        "Тимур скидывал фото с мыслью 'попробовать можно'",
        "Вчера MixaRed у Тимура дома примерял ободок с ушками и хвост горничной",
        "Тимур @Tymur2000 — создатель и разраб бота, общаемся по-братски, на равных, без клоунады и без подобострастия"
    ], ensure_ascii=False)
    
    chats = [-1002255156347, -1004479083851, -1004321632420]
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
    print(f"Memory for {today_str} seeded successfully in {len(chats)} chats.")

if __name__ == "__main__":
    seed_memory()
