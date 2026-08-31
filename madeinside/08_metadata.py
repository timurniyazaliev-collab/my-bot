#!/usr/bin/env python3
"""Generates the YouTube title/description/tags for a finished video.

Usage: python 08_metadata.py <idea_id>
"""

import argparse
import json
import re

import anthropic
import config
import common

PROMPT = """Ты пишешь метаданные для YouTube-ролика "{title}" в нише \
craftsmanship/manufacturing (faceless-канал, английский язык).

Хук ролика: {hook}

Тайминги по блокам (для описания):
{timecodes}

Сгенерируй:
- title: заголовок до 60 символов, ключевое слово в начале
- description: хук одной фразой + 2-3 предложения о видео, затем таймкоды \
строками вида "0:00 Intro", затем 5-8 релевантных хэштегов
- tags: список из 10-15 тегов для YouTube (отдельные слова/фразы, без #)

Ответь СТРОГО валидным JSON без markdown-обёртки:
{{"title": "...", "description": "...", "tags": ["...", "..."]}}
"""


def _extract_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    if not match:
        raise ValueError(f"Claude не вернул JSON-объект: {text[:200]}")
    return json.loads(match.group(0))


def _format_timecodes(blocks: list[dict]) -> str:
    def mmss(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"

    return "\n".join(f"{mmss(b['start'])} {b['label']}" for b in blocks)


def generate_metadata(idea: dict, script: dict) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.METADATA_MODEL,
        max_tokens=1200,
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(
                    title=idea["title"],
                    hook=idea["hook"],
                    timecodes=_format_timecodes(script["blocks"]),
                ),
            }
        ],
    )
    return _extract_json_object(response.content[0].text)


def main():
    if not config.ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY не задан. Добавьте его в madeinside/.env")

    parser = argparse.ArgumentParser()
    parser.add_argument("idea_id")
    args = parser.parse_args()

    idea = common.find_idea(args.idea_id)
    if not idea:
        raise SystemExit(f"Идея '{args.idea_id}' не найдена в ideas_backlog.json")
    script = common.load_script(args.idea_id)

    metadata = generate_metadata(idea, script)
    common.write_json(common.metadata_path(args.idea_id), metadata)

    print(f"Метаданные сохранены: {common.metadata_path(args.idea_id)}\n")
    print(f"Title: {metadata['title']} ({len(metadata['title'])} символов)")
    print(f"\nDescription:\n{metadata['description']}")
    print(f"\nTags: {', '.join(metadata['tags'])}")


if __name__ == "__main__":
    main()
