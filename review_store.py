"""Хранилище для ежедневного разбора диалогов (см. AUTONOMY-PASSPORT.html).

Общее для webhook_server.py (который пишет, в какие дни был активен
диалог, и отправляет отчёты разбора владельцу в Telegram) и bot.py
(который по реплаю владельца на отчёт понимает, к какому дню он
относится). Лежит в той же SQLite-базе, что и история диалогов вебхука.
"""

import datetime
import hashlib
import json
import os
import sqlite3
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "webhook_conversations.db")
OWNER_CHAT_ID_PATH = os.path.join(BASE_DIR, "owner_chat_id.txt")

# День разбора считаем по Бишкеку, а не по часам сервера (он в UTC).
BISHKEK_TZ = datetime.timezone(datetime.timedelta(hours=6))
TELEGRAM_MAX_LEN = 4096


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS conversation_days "
            "(conversation_id TEXT NOT NULL, day TEXT NOT NULL, PRIMARY KEY (conversation_id, day))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS escalations "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, day TEXT NOT NULL, "
            "created_at INTEGER NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS review_messages "
            "(dedupe_key TEXT PRIMARY KEY, sent_at INTEGER NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS review_reply_targets "
            "(message_id INTEGER PRIMARY KEY, review_date TEXT NOT NULL)"
        )
        # Диалоги, сохранённые до появления conversation_days, — хотя бы по дню начала.
        for conv_id, created_at in conn.execute(
            "SELECT conversation_id, created_at FROM conversations WHERE created_at IS NOT NULL"
        ).fetchall():
            conn.execute(
                "INSERT OR IGNORE INTO conversation_days (conversation_id, day) VALUES (?, ?)",
                (conv_id, day_of(created_at)),
            )


def today() -> str:
    return datetime.datetime.now(BISHKEK_TZ).date().isoformat()


def day_of(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts, BISHKEK_TZ).date().isoformat()


def mark_active(conversation_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversation_days (conversation_id, day) VALUES (?, ?)",
            (conversation_id, today()),
        )


def log_escalation(conversation_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO escalations (conversation_id, day, created_at) VALUES (?, ?, ?)",
            (conversation_id, today(), int(time.time())),
        )


def conversation_ref(conversation_id: str) -> str:
    """Обезличенная метка диалога для разбора: conversation_id в CRM может
    содержать номер телефона, агенту и отчёту он не нужен."""
    return hashlib.sha256(conversation_id.encode()).hexdigest()[:8]


def dialogs_for_day(day: str) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT c.conversation_id, c.messages, c.created_at FROM conversation_days d "
            "JOIN conversations c ON c.conversation_id = d.conversation_id "
            "WHERE d.day = ? ORDER BY c.created_at",
            (day,),
        ).fetchall()
        start = int(datetime.datetime.fromisoformat(day).replace(tzinfo=BISHKEK_TZ).timestamp())
        unknown = conn.execute(
            "SELECT conversation_id, question FROM unknown_questions WHERE created_at >= ? AND created_at < ?",
            (start, start + 86400),
        ).fetchall()
        escalated = {
            r[0] for r in conn.execute("SELECT conversation_id FROM escalations WHERE day = ?", (day,))
        }

    unknown_by_conv: dict[str, list[str]] = {}
    for conv_id, question in unknown:
        unknown_by_conv.setdefault(conv_id, []).append(question)

    return [
        {
            "ref": conversation_ref(conv_id),
            "started_on": day_of(created_at) if created_at else None,
            "escalated_on_this_day": conv_id in escalated,
            "unknown_questions": unknown_by_conv.get(conv_id, []),
            "messages": json.loads(messages),
        }
        for conv_id, messages, created_at in rows
    ]


def load_owner_chat_id() -> int | None:
    try:
        with open(OWNER_CHAT_ID_PATH) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _telegram_send(token: str, chat_id: int, text: str) -> int:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)["result"]["message_id"]


def claim_dedupe_key(dedupe_key: str) -> bool:
    """True, если сообщение с этим ключом ещё не отправлялось (и теперь
    считается отправленным) — защита от повторной отправки отчёта."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO review_messages (dedupe_key, sent_at) VALUES (?, ?)",
            (dedupe_key, int(time.time())),
        )
        return cur.rowcount == 1


def release_dedupe_key(dedupe_key: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM review_messages WHERE dedupe_key = ?", (dedupe_key,))


def send_to_owner(text: str, review_date: str | None) -> list[int]:
    """Отправляет текст владельцу. Если указан review_date — владелец
    может ответить на это сообщение реплаем, и бот передаст ответ агенту."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = load_owner_chat_id()
    if chat_id is None:
        raise RuntimeError("owner chat id is not set")
    ids = [
        _telegram_send(token, chat_id, text[i:i + TELEGRAM_MAX_LEN])
        for i in range(0, len(text), TELEGRAM_MAX_LEN)
    ]
    if review_date:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO review_reply_targets (message_id, review_date) VALUES (?, ?)",
                [(i, review_date) for i in ids],
            )
    return ids


def review_date_for_reply(message_id: int) -> str | None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT review_date FROM review_reply_targets WHERE message_id = ?", (message_id,)
            ).fetchone()
    except sqlite3.OperationalError:  # вебхук ещё ни разу не запускался с этой таблицей
        return None
    return row[0] if row else None


def fire_apply_routine(text: str) -> None:
    """Запускает Routine «Применить ответ» (Claude Code) через её API-триггер."""
    req = urllib.request.Request(
        os.environ["REVIEW_APPLY_ROUTINE_URL"],
        data=json.dumps({"text": text}).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['REVIEW_APPLY_ROUTINE_TOKEN']}",
            "anthropic-beta": "experimental-cc-routine-2026-04-01",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()
