#!/usr/bin/env python3
"""Turns one backlog idea into a narration script with timecodes.

Usage: python 02_script.py <idea_id>

Timecodes are computed locally from word count at a fixed speaking rate
(config.WORDS_PER_MINUTE) rather than trusted from the model — LLMs are
unreliable at arithmetic like "at 150 wpm this paragraph takes 18 seconds".
"""

import argparse
import json
import re

import anthropic
import config
import common

PROMPT = """Напиши сценарий озвучки для YouTube-ролика "{title}" \
(хук: {hook}) в нише craftsmanship/manufacturing.

Требования:
- Разговорный английский, без канцелярита, живой темп речи.
- Структура из 6-7 блоков: hook, затем 4-5 этапов процесса (stage), затем \
outro с призывом подписаться.
- Хронометраж на озвучку 3-4 минуты (~450-600 слов суммарно).
- Конкретные факты (цифры, температуры, время, материалы) вместо общих фраз.
- На сложных/рискованных этапах процесса — драматургия: подчеркни, что \
может пойти не так, почему это сложно.

Ответь СТРОГО валидным JSON-массивом объектов, только текст для озвучки \
(без ремарок о видеоряде), например:
[
  {{"role": "hook", "label": "hook", "text": "..."}},
  {{"role": "stage", "label": "Cutting the body", "text": "..."}},
  {{"role": "outro", "label": "outro", "text": "..."}}
]
"""


def _extract_json_array(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text.strip(), re.DOTALL)
    if not match:
        raise ValueError(f"Claude не вернул JSON-массив: {text[:200]}")
    return json.loads(match.group(0))


def _with_timecodes(blocks: list[dict]) -> list[dict]:
    words_per_sec = config.WORDS_PER_MINUTE / 60
    timed = []
    cursor = 0.0
    for i, block in enumerate(blocks):
        word_count = len(block["text"].split())
        duration = round(word_count / words_per_sec, 1)
        timed.append(
            {
                "index": i,
                "role": block["role"],
                "label": block["label"],
                "text": block["text"],
                "word_count": word_count,
                "start": round(cursor, 1),
                "end": round(cursor + duration, 1),
                "duration": duration,
            }
        )
        cursor += duration
    return timed


def generate_script(idea: dict) -> list[dict]:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.SCRIPT_MODEL,
        max_tokens=3000,
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(title=idea["title"], hook=idea["hook"]),
            }
        ],
    )
    blocks = _extract_json_array(response.content[0].text)
    return _with_timecodes(blocks)


def main():
    if not config.ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY не задан. Добавьте его в madeinside/.env")

    parser = argparse.ArgumentParser()
    parser.add_argument("idea_id")
    args = parser.parse_args()

    idea = common.find_idea(args.idea_id)
    if not idea:
        raise SystemExit(f"Идея '{args.idea_id}' не найдена в ideas_backlog.json")

    blocks = generate_script(idea)
    common.write_json(
        common.script_path(idea["id"]),
        {"id": idea["id"], "title": idea["title"], "blocks": blocks},
    )
    common.set_idea_status(idea["id"], "scripted")

    total = blocks[-1]["end"] if blocks else 0
    print(f"Сценарий сохранён: {common.script_path(idea['id'])}")
    print(f"Хронометраж: ~{total:.0f}с ({total / 60:.1f} мин)\n")
    for b in blocks:
        print(f"[{b['start']:>5}-{b['end']:<5}] {b['role']:<6} {b['label']}")


if __name__ == "__main__":
    main()
