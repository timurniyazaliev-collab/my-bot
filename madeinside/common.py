"""Shared helpers used by every pipeline step: json I/O, ids, per-video paths."""

import json
import os
import re
import secrets

import config


def slugify(text: str, max_words: int = 6) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())[:max_words]
    return "-".join(words) or "idea"


def make_id(title: str) -> str:
    return f"{slugify(title)}-{secrets.token_hex(3)}"


def read_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_text(response) -> str:
    """Joins the text blocks of a Claude response, skipping thinking blocks
    (opus models can return a ThinkingBlock before the actual text)."""
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "Ответ Claude обрезан по лимиту max_tokens (часть бюджета уходит на "
            "скрытый 'thinking') — увеличьте лимит для этого шага в config.py."
        )
    return "\n\n".join(b.text for b in response.content if b.type == "text")


# --- ideas backlog --------------------------------------------------------

def load_backlog() -> list[dict]:
    return read_json(config.IDEAS_BACKLOG_PATH, default=[])


def save_backlog(ideas: list[dict]) -> None:
    write_json(config.IDEAS_BACKLOG_PATH, ideas)


def find_idea(idea_id: str) -> dict | None:
    for idea in load_backlog():
        if idea["id"] == idea_id:
            return idea
    return None


def set_idea_status(idea_id: str, status: str) -> None:
    ideas = load_backlog()
    for idea in ideas:
        if idea["id"] == idea_id:
            idea["status"] = status
    save_backlog(ideas)


# --- per-idea file paths ----------------------------------------------------

def script_path(idea_id: str) -> str:
    return os.path.join(config.SCRIPTS_DIR, f"{idea_id}.json")


def shotlist_path(idea_id: str) -> str:
    return os.path.join(config.SCRIPTS_DIR, f"{idea_id}.shotlist.json")


def raw_footage_dir(idea_id: str) -> str:
    return os.path.join(config.ASSETS_DIR, idea_id, "raw")


def audio_dir(idea_id: str) -> str:
    return os.path.join(config.ASSETS_DIR, idea_id, "audio")


def sources_path(idea_id: str) -> str:
    return os.path.join(config.ASSETS_DIR, idea_id, "sources.txt")


def render_path(idea_id: str) -> str:
    return os.path.join(config.RENDER_DIR, f"{idea_id}.mp4")


def srt_path(idea_id: str) -> str:
    return os.path.join(config.RENDER_DIR, f"{idea_id}.srt")


def thumbnail_path(idea_id: str, variant: int) -> str:
    return os.path.join(config.ASSETS_DIR, idea_id, f"thumbnail_{variant}.jpg")


def metadata_path(idea_id: str) -> str:
    return os.path.join(config.METADATA_DIR, f"{idea_id}.json")


def load_script(idea_id: str) -> dict:
    data = read_json(script_path(idea_id))
    if not data:
        raise SystemExit(
            f"Нет сценария для '{idea_id}'. Сначала запустите: "
            f"python 02_script.py {idea_id}"
        )
    return data
