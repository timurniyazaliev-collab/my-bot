"""Settings for the viral video platform, loaded from .env.

Independent of the Telegram bot's config — this module never imports
bot.py or sales_ai.py, and vice versa.
"""

import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)

load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"))

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "base")

DB_PATH = os.path.join(BASE_DIR, os.environ.get("DB_PATH", "viral_platform.db"))

# YouTube extended Shorts to up to 3 minutes in 2024 — keep a little headroom.
MAX_SHORT_SECONDS = int(os.environ.get("MAX_SHORT_SECONDS", "183"))

STORYBOARD_MODEL = os.environ.get("STORYBOARD_MODEL", "claude-opus-5")
SCRIPT_MODEL = os.environ.get("SCRIPT_MODEL", "claude-opus-5")

NICHE_CONTEXT_PATH = os.path.join(BASE_DIR, "niche.md")


def read_niche_context() -> str:
    if not os.path.exists(NICHE_CONTEXT_PATH):
        return ""
    with open(NICHE_CONTEXT_PATH, "r", encoding="utf-8") as f:
        return f.read()
