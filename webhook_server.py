"""HTTP-обёртка над sales_ai.py для внешних систем (CRM, веб-виджет),
которые не могут напрямую импортировать Python-код бота — только ходят
по HTTP. Логика продаж (факты, возражения, эскалация, выбор фото) вся
остаётся в sales_ai.py, этот файл только принимает запрос и отдаёт
готовый ответ.
"""

import datetime
import functools
import glob
import json
import logging
import os
import sqlite3
import time

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

import review_store
from sales_ai import get_lead_reply

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
MEDIA_DIR = os.path.join(BASE_DIR, "media")
DB_PATH = os.path.join(BASE_DIR, "webhook_conversations.db")

API_KEY = os.environ["WEBHOOK_API_KEY"]
# Отдельный ключ для агента ежедневного разбора диалогов: только чтение
# диалогов и сообщения владельцу в Telegram, писать клиентам и сбрасывать
# историю им нельзя. Необязательный — без него адреса /api/review/* закрыты.
REVIEW_API_KEY = os.environ.get("REVIEW_API_KEY")

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

with sqlite3.connect(DB_PATH) as _conn:
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS conversations "
        "(conversation_id TEXT PRIMARY KEY, messages TEXT NOT NULL, created_at INTEGER)"
    )
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS unknown_questions "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, "
        "question TEXT NOT NULL, created_at INTEGER NOT NULL)"
    )
    try:
        _conn.execute("ALTER TABLE conversations ADD COLUMN created_at INTEGER")
    except sqlite3.OperationalError:
        pass

review_store.init_db()


def load_history(conversation_id: str) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT messages FROM conversations WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
    return json.loads(row[0]) if row else []


def save_history(conversation_id: str, messages: list[dict]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO conversations (conversation_id, messages, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET messages = excluded.messages",
            (conversation_id, json.dumps(messages, ensure_ascii=False), int(time.time())),
        )
    review_store.mark_active(conversation_id)


def delete_history(conversation_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM unknown_questions WHERE conversation_id = ?", (conversation_id,))


def log_unknown_questions(conversation_id: str, notes: list[str]) -> None:
    if not notes:
        return
    now = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            "INSERT INTO unknown_questions (conversation_id, question, created_at) VALUES (?, ?, ?)",
            [(conversation_id, note, now) for note in notes],
        )


def _day_bounds(date_str: str | None) -> tuple[int, int]:
    day = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
    start = int(datetime.datetime.combine(day, datetime.time.min).timestamp())
    return start, start + 86400


def require_api_key(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if request.headers.get("X-API-Key") != API_KEY:
            return jsonify({"error": "unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapped


def require_review_key(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not REVIEW_API_KEY or request.headers.get("X-API-Key") != REVIEW_API_KEY:
            return jsonify({"error": "unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapped


def _files(subdir: str, prefix: str) -> list[str]:
    return sorted(glob.glob(os.path.join(MEDIA_DIR, subdir, f"{prefix}*.jpg")))


PHOTO_FILES = {
    "exterior_hero": _files("exterior", "hero"),
    "exterior_yard": _files("exterior", "yard"),
    "exterior_commercial": _files("exterior", "commercial"),
    "exterior_entrance": _files("exterior", "entrance"),
    "plan_1k": _files("plans", "plan_1k"),
    "plan_2k": _files("plans", "plan_2k"),
    "plan_3k_86": _files("plans", "plan_3k_86"),
    "plan_3k_95": _files("plans", "plan_3k_95"),
    "plan_4k": _files("plans", "plan_4k"),
    "plan_penthouse": _files("plans", "plan_penthouse"),
    "plan_commercial": _files("plans", "plan_commercial"),
}


def _photo_urls(category: str) -> list[str]:
    base = request.url_root.rstrip("/")
    return [
        f"{base}/media/{os.path.relpath(path, MEDIA_DIR)}"
        for path in PHOTO_FILES.get(category, [])
    ]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/media/<path:filepath>")
def media(filepath):
    return send_from_directory(MEDIA_DIR, filepath)


@app.post("/api/lead-reply")
@require_api_key
def lead_reply():
    data = request.get_json(silent=True) or {}
    conversation_id = str(data.get("conversation_id", "")).strip()
    message = str(data.get("message", "")).strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    if not message:
        message = (
            "(клиент отправил сообщение без текста — вероятно, переслал пост, "
            "reels или карусель по рекламе, ничего не написав от себя)"
        )

    history = load_history(conversation_id)
    history.append({"role": "user", "content": message})
    try:
        client_text, escalation_card, photo_categories, unknown_notes = get_lead_reply(history)
    except Exception:
        log.exception("lead_reply failed for conversation_id=%s", conversation_id)
        return jsonify({"error": "internal_error"}), 500

    history.append({"role": "assistant", "content": client_text})
    save_history(conversation_id, history[-30:])
    log_unknown_questions(conversation_id, unknown_notes)
    if escalation_card is not None:
        review_store.log_escalation(conversation_id)

    return jsonify(
        {
            "reply": client_text,
            "escalate": escalation_card is not None,
            "escalation_card": escalation_card,
            "photos": [{"category": cat, "urls": _photo_urls(cat)} for cat in photo_categories],
            "unknown_questions": unknown_notes,
        }
    )


@app.post("/api/reset")
@require_api_key
def reset_conversation():
    data = request.get_json(silent=True) or {}
    conversation_id = str(data.get("conversation_id", "")).strip()
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    delete_history(conversation_id)
    return jsonify({"status": "reset"})


@app.get("/api/conversation/<conversation_id>")
@require_api_key
def get_conversation(conversation_id):
    return jsonify({"conversation_id": conversation_id, "messages": load_history(conversation_id)})


@app.post("/api/conversation/<conversation_id>/sync")
@require_api_key
def sync_conversation(conversation_id):
    """Replace stored history with messages CRM knows about (e.g. what a
    human manager said while the bot was off this dialogue), so the bot has
    real context if it's handed the conversation back later."""
    data = request.get_json(silent=True) or {}
    messages = data.get("messages")
    if not isinstance(messages, list):
        return jsonify({"error": "messages must be a list"}), 400

    cleaned = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            return jsonify({"error": "each message needs role 'user' or 'assistant' and content"}), 400
        cleaned.append({"role": m["role"], "content": str(m.get("content", ""))})

    save_history(conversation_id, cleaned[-30:])
    return jsonify({"status": "synced", "message_count": len(cleaned[-30:])})


@app.get("/api/stats")
@require_api_key
def stats():
    date_str = request.args.get("date")
    start, end = _day_bounds(date_str)
    with sqlite3.connect(DB_PATH) as conn:
        new_conversations = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE created_at >= ? AND created_at < ?", (start, end)
        ).fetchone()[0]
        unknown_count = conn.execute(
            "SELECT COUNT(*) FROM unknown_questions WHERE created_at >= ? AND created_at < ?", (start, end)
        ).fetchone()[0]
    return jsonify(
        {
            "date": date_str or datetime.date.today().isoformat(),
            "new_conversations": new_conversations,
            "unknown_questions": unknown_count,
        }
    )


@app.get("/api/conversations")
@require_api_key
def list_conversations():
    date_str = request.args.get("date")
    with sqlite3.connect(DB_PATH) as conn:
        if date_str:
            start, end = _day_bounds(date_str)
            rows = conn.execute(
                "SELECT conversation_id, messages, created_at FROM conversations "
                "WHERE created_at >= ? AND created_at < ? ORDER BY created_at DESC",
                (start, end),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT conversation_id, messages, created_at FROM conversations "
                "ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
    return jsonify(
        [
            {"conversation_id": r[0], "message_count": len(json.loads(r[1])), "created_at": r[2]}
            for r in rows
        ]
    )


@app.get("/api/unknown-questions")
@require_api_key
def list_unknown_questions():
    date_str = request.args.get("date")
    with sqlite3.connect(DB_PATH) as conn:
        if date_str:
            start, end = _day_bounds(date_str)
            rows = conn.execute(
                "SELECT conversation_id, question, created_at FROM unknown_questions "
                "WHERE created_at >= ? AND created_at < ? ORDER BY created_at DESC",
                (start, end),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT conversation_id, question, created_at FROM unknown_questions "
                "ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
    return jsonify([{"conversation_id": r[0], "question": r[1], "created_at": r[2]} for r in rows])


@app.get("/api/review/dialogs")
@require_review_key
def review_dialogs():
    """Все диалоги, в которых была активность в этот день (по Бишкеку), целиком,
    с обезличенной меткой вместо conversation_id. По умолчанию — вчера."""
    day = request.args.get("date")
    if day:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD"}), 400
    else:
        day = (datetime.date.fromisoformat(review_store.today()) - datetime.timedelta(days=1)).isoformat()
    dialogs = review_store.dialogs_for_day(day)
    return jsonify({"date": day, "count": len(dialogs), "dialogs": dialogs})


@app.post("/api/review/message")
@require_review_key
def review_message():
    """Сообщение от агента разбора владельцу в Telegram.
    dedupe_key — не отправлять повторно (например, "report:2026-09-25");
    review_date — владелец сможет ответить реплаем, ответ уйдёт агенту."""
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    dedupe_key = str(data.get("dedupe_key", "")).strip() or None
    review_date = str(data.get("review_date", "")).strip() or None
    if not text:
        return jsonify({"error": "text is required"}), 400
    if dedupe_key and not review_store.claim_dedupe_key(dedupe_key):
        return jsonify({"status": "already_sent"})
    try:
        ids = review_store.send_to_owner(text, review_date)
    except Exception:
        log.exception("review message send failed")
        if dedupe_key:
            review_store.release_dedupe_key(dedupe_key)
        return jsonify({"error": "send_failed"}), 502
    return jsonify({"status": "sent", "message_count": len(ids)})


if __name__ == "__main__":
    port = int(os.environ.get("WEBHOOK_PORT", 8000))
    app.run(host="0.0.0.0", port=port, threaded=True)
