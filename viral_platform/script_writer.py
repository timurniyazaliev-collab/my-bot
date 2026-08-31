"""Writes an original script for the user's own niche, inspired by a viral
video's structure — never by copying its wording or facts.

Copying someone else's video almost script-for-script is both a copyright
risk and bad strategy (platforms suppress near-duplicates). What actually
transfers is the *technique*: hook style, pacing, scene structure.
"""

import anthropic

from . import config, db, storyboard

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


PROMPT_TEMPLATE = """Ты — сценарист коротких вертикальных видео. Ниже — \
раскадровка чужого вирусного ролика (структура и приём, которым он держит \
внимание), и контекст ниши/бизнеса, для которого нужно написать НОВЫЙ ролик.

ВАЖНО: не копируй формулировки, факты или примеры исходного ролика. \
Используй только его структуру — порядок и роли сцен, темп, тип хука — \
и наполни её оригинальным содержанием под указанную нишу.

Структура исходного ролика (роль сцены — тайминг — о чём она):
{scene_structure}

Почему цепляет хук исходного ролика: {hook_analysis}

Контекст ниши/бизнеса:
{niche_context}

{extra_instructions}

Напиши сценарий нового ролика простым текстом:
- Хук (первые 2-3 секунды, дословная реплика или текст на экране)
- Сцены по порядку: что говорится/показывается, что за текст на экране
- Призыв к действию в конце
Без markdown-разметки, без комментариев о том, что это сгенерировано."""


def _format_scenes(scenes: list[dict]) -> str:
    return "\n".join(
        f"- {s['role']} ({s['start']}-{s['end']}с): {s['description']}"
        for s in scenes
    )


def generate_script(
    video_id: str, niche_context: str = "", extra_instructions: str = ""
) -> str:
    board = db.get_storyboard(video_id) or storyboard.build_storyboard(video_id)
    niche_context = niche_context or config.read_niche_context()

    prompt = PROMPT_TEMPLATE.format(
        scene_structure=_format_scenes(board["scenes"]),
        hook_analysis=board["hook_analysis"],
        niche_context=niche_context or "(не указан)",
        extra_instructions=extra_instructions,
    )
    response = _get_client().messages.create(
        model=config.SCRIPT_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Ответ Claude обрезан по лимиту max_tokens — увеличьте лимит.")
    script_text = "\n\n".join(b.text for b in response.content if b.type == "text").strip()
    db.save_script(video_id, script_text)
    return script_text
