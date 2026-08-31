#!/usr/bin/env python3
"""Generates stock-footage search queries for every block of a script.

Usage: python 03_shotlist.py <idea_id>
"""

import argparse
import json
import re

import anthropic
import config
import common

PROMPT = """Ниже — блоки сценария YouTube-ролика о производственном процессе. \
Для каждого блока предложи 2-3 коротких поисковых запроса на английском для \
поиска стокового видео на Pexels/Videvo (конкретные, визуальные, например: \
"guitar body sanding closeup", "wood bending steam factory").

Блоки:
{blocks}

Ответь СТРОГО валидным JSON-объектом вида {{"<index>": ["query1", "query2"]}}, \
без markdown-обёртки, ключи — индексы блоков строкой.
"""


def _extract_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    if not match:
        raise ValueError(f"Claude не вернул JSON-объект: {text[:200]}")
    return json.loads(match.group(0))


def _format_blocks(blocks: list[dict]) -> str:
    return "\n".join(f"{b['index']}. [{b['role']}] {b['text']}" for b in blocks)


def generate_shotlist(blocks: list[dict]) -> dict:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.SHOTLIST_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": PROMPT.format(blocks=_format_blocks(blocks))}],
    )
    raw = _extract_json_object(common.extract_text(response))
    return {int(k): v for k, v in raw.items()}


def main():
    if not config.ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY не задан. Добавьте его в madeinside/.env")

    parser = argparse.ArgumentParser()
    parser.add_argument("idea_id")
    args = parser.parse_args()

    script = common.load_script(args.idea_id)
    queries_by_block = generate_shotlist(script["blocks"])

    shotlist = []
    for block in script["blocks"]:
        shotlist.append(
            {
                "index": block["index"],
                "label": block["label"],
                "queries": queries_by_block.get(block["index"], []),
            }
        )

    common.write_json(common.shotlist_path(args.idea_id), {"id": args.idea_id, "blocks": shotlist})
    print(f"Shotlist сохранён: {common.shotlist_path(args.idea_id)}\n")
    for item in shotlist:
        print(f"[{item['index']}] {item['label']}: {', '.join(item['queries'])}")


if __name__ == "__main__":
    main()
