"""Settings for the MadeInside pipeline, loaded from madeinside/.env.

Fully independent of the Telegram bot and of viral_platform — its own
requirements.txt, its own .env, not part of the bot's autodeploy.
"""

import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

# --- API keys -----------------------------------------------------------

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
VIDEVO_API_KEY = os.environ.get("VIDEVO_API_KEY", "")  # optional, see README

TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "elevenlabs")  # elevenlabs | google
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")
GOOGLE_TTS_VOICE = os.environ.get("GOOGLE_TTS_VOICE", "en-US-Studio-O")

YOUTUBE_CLIENT_SECRETS_PATH = os.path.join(
    BASE_DIR, os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE", "client_secret.json")
)
YOUTUBE_TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

# --- Claude models --------------------------------------------------------
# Creative steps get the stronger model; mechanical/templated steps get the
# cheaper one — no reason to pay opus prices for search-term lists.

IDEAS_MODEL = os.environ.get("IDEAS_MODEL", "claude-opus-5")
SCRIPT_MODEL = os.environ.get("SCRIPT_MODEL", "claude-opus-5")
SHOTLIST_MODEL = os.environ.get("SHOTLIST_MODEL", "claude-sonnet-5")
METADATA_MODEL = os.environ.get("METADATA_MODEL", "claude-sonnet-5")

# --- Script timing ---------------------------------------------------------
# We compute timecodes ourselves from word count instead of trusting the
# model's arithmetic — a typical narration speaking rate.

WORDS_PER_MINUTE = int(os.environ.get("WORDS_PER_MINUTE", "150"))

# --- Video output -----------------------------------------------------------

TARGET_ORIENTATION = os.environ.get("TARGET_ORIENTATION", "horizontal")  # horizontal | vertical
RESOLUTIONS = {
    "horizontal": (1920, 1080),
    "vertical": (1080, 1920),
}
MUSIC_PATH = os.environ.get("MUSIC_PATH", "")  # optional royalty-free background track

# Bold font for thumbnail text — no image-gen API is wired up (none was in
# the account's key list), so thumbnails are composed from a video frame +
# text overlay via Pillow instead. Override if the default isn't on disk.
THUMBNAIL_FONT_PATH = os.environ.get(
    "THUMBNAIL_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
)

# --- Paths -------------------------------------------------------------

IDEAS_BACKLOG_PATH = os.path.join(BASE_DIR, "ideas_backlog.json")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
RENDER_DIR = os.path.join(BASE_DIR, "render")
METADATA_DIR = os.path.join(BASE_DIR, "metadata")
SCHEDULE_PATH = os.path.join(BASE_DIR, "schedule.json")
PERSONA_PATH = os.path.join(BASE_DIR, "persona.md")


def read_persona() -> str:
    if not os.path.exists(PERSONA_PATH):
        return ""
    with open(PERSONA_PATH, "r", encoding="utf-8") as f:
        return f.read()
