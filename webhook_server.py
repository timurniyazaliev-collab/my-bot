"""HTTP-обёртка над sales_ai.py для внешних систем (CRM, веб-виджет),
которые не могут напрямую импортировать Python-код бота — только ходят
по HTTP. Логика продаж (факты, возражения, эскалация, выбор фото) вся
остаётся в sales_ai.py, этот файл только принимает запрос и отдаёт
готовый ответ.
"""

import functools
import glob
import json
import logging
import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from sales_ai import get_lead_reply

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
MEDIA_DIR = os.path.join(BASE_DIR, "media")
DB_PATH = os.path.join(BASE_DIR, "webhook_conversations.db")

API_KEY = os.environ["WEBHOOK_API_KEY"]

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

with sqlite3.connect(DB_PATH) as _conn:
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS conversations (conversation_id TEXT PRIMARY KEY, messages TEXT NOT NULL)"
    )


def load_history(conversation_id: str) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT messages FROM conversations WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
    return json.loads(row[0]) if row else []


def save_history(conversation_id: str, messages: list[dict]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO conversations (conversation_id, messages) VALUES (?, ?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET messages = excluded.messages",
            (conversation_id, json.dumps(messages, ensure_ascii=False)),
        )


def delete_history(conversation_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))


def require_api_key(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if request.headers.get("X-API-Key") != API_KEY:
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
    if not conversation_id or not message:
        return jsonify({"error": "conversation_id and message are required"}), 400

    history = load_history(conversation_id)
    history.append({"role": "user", "content": message})
    try:
        client_text, escalation_card, photo_categories, unknown_notes = get_lead_reply(history)
    except Exception:
        log.exception("lead_reply failed for conversation_id=%s", conversation_id)
        return jsonify({"error": "internal_error"}), 500

    history.append({"role": "assistant", "content": client_text})
    save_history(conversation_id, history[-30:])

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


if __name__ == "__main__":
    port = int(os.environ.get("WEBHOOK_PORT", 8000))
    app.run(host="0.0.0.0", port=port, threaded=True)
