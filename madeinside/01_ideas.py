#!/usr/bin/env python3
"""Generates video ideas for the channel and appends them to ideas_backlog.json.

Usage: python 01_ideas.py [--count 10]
"""

import argparse
import json
import re

import anthropic
import config
import common

PROMPT = """Предложи {count} тем в формате "Как делают X" для YouTube-канала \
о производственных процессах (ниша: craftsmanship/manufacturing — гитары, \
стекло, кроссовки, шоколад, мебель и похожие темы).

Для каждой темы дай:
- title: название на английском
- hook: потенциальный хук (первые 15 секунд ролика)
- visual_richness: "high", "medium" или "low" — насколько легко найти \
archival/stock footage по теме

Ответь СТРОГО валидным JSON-массивом без markdown-обёртки, например:
[{{"title": "...", "hook": "...", "visual_richness": "high"}}]
"""


def _extract_json_array(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text.strip(), re.DOTALL)
    if not match:
        raise ValueError(f"Claude не вернул JSON-массив: {text[:200]}")
    return json.loads(match.group(0))


def generate_ideas(count: int) -> list[dict]:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.IDEAS_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": PROMPT.format(count=count)}],
    )
    raw_ideas = _extract_json_array(response.content[0].text)

    ideas = []
    for raw in raw_ideas:
        ideas.append(
            {
                "id": common.make_id(raw["title"]),
                "title": raw["title"],
                "hook": raw["hook"],
                "visual_richness": raw["visual_richness"],
                "status": "backlog",
            }
        )
    return ideas


def main():
    if not config.ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY не задан. Добавьте его в madeinside/.env")

    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()

    new_ideas = generate_ideas(args.count)
    backlog = common.load_backlog()
    backlog.extend(new_ideas)
    common.save_backlog(backlog)

    print(f"Добавлено {len(new_ideas)} идей в {config.IDEAS_BACKLOG_PATH}:\n")
    for idea in new_ideas:
        print(f"[{idea['visual_richness']:>6}] {idea['id']}")
        print(f"         {idea['title']}")
        print(f"         Хук: {idea['hook']}\n")


if __name__ == "__main__":
    main()
