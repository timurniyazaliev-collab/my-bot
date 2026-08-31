"""Turns a transcript into a scene-by-scene storyboard via Claude.

The point isn't just "what was said" — it's *why the video works*: how the
first seconds hook attention, and what role each scene plays (hook, problem,
proof, payoff, call to action, ...).
"""

import json
import re

import anthropic

from . import config, db, transcribe

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


PROMPT_TEMPLATE = """Ты — эксперт по коротким вирусным видео (YouTube Shorts, \
TikTok, Reels). Ниже — транскрипт ролика с таймкодами (в секундах).

Разбей ролик на сцены и объясни, почему он цепляет зрителя. Ответь СТРОГО \
валидным JSON без markdown-обёртки, в такой форме:

{{
  "scenes": [
    {{"start": 0.0, "end": 3.2, "role": "hook", "description": "..."}},
    {{"start": 3.2, "end": 10.0, "role": "problem", "description": "..."}}
  ],
  "hook_analysis": "почему первые секунды удерживают внимание"
}}

Роли сцен: hook, problem, agitation, solution, proof, payoff, cta, other — \
выбирай наиболее подходящую по смыслу.

Транскрипт:
{transcript}
"""


def _format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']}-{s['end']}] {s['text']}" for s in segments)


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Claude не вернул JSON: {text[:200]}")
    return json.loads(match.group(0))


def build_storyboard(video_id: str, force: bool = False) -> dict:
    if not force:
        cached = db.get_storyboard(video_id)
        if cached:
            return cached

    transcript = db.get_transcript(video_id) or transcribe.transcribe_video(video_id)

    prompt = PROMPT_TEMPLATE.format(transcript=_format_transcript(transcript["segments"]))
    response = _get_client().messages.create(
        model=config.STORYBOARD_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Ответ Claude обрезан по лимиту max_tokens — увеличьте лимит.")
    text = "\n\n".join(b.text for b in response.content if b.type == "text")
    parsed = _extract_json(text)

    db.save_storyboard(video_id, parsed["scenes"], parsed["hook_analysis"])
    return {
        "video_id": video_id,
        "scenes": parsed["scenes"],
        "hook_analysis": parsed["hook_analysis"],
    }
