#!/usr/bin/env python3
"""Runs the whole MadeInside pipeline for one video idea.

Usage:
  python run_pipeline.py                       # new idea, steps 1-8, then review
  python run_pipeline.py --idea-id <id>         # skip step 1, use an existing idea
  python run_pipeline.py --idea-id <id> --from-step 5   # resume after a redo

Runs steps 1-8 automatically, then hands off to 09_review.py (interactive:
approve / reject / redo-step-N). Only on "approve" does it call 10_publish.py
— this checkpoint is intentionally never skipped.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import common

SCRIPT_DIR = Path(__file__).resolve().parent

STEP_SCRIPTS = {
    2: "02_script.py",
    3: "03_shotlist.py",
    4: "04_fetch_footage.py",
    5: "05_tts.py",
    6: "06_assemble.py",
    7: "07_thumbnail.py",
    8: "08_metadata.py",
}


def run_step(script_name: str, args: list[str]) -> None:
    cmd = [sys.executable, str(SCRIPT_DIR / script_name), *args]
    print(f"\n=== {script_name} {' '.join(args)} ===")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(f"Шаг {script_name} завершился с ошибкой (код {result.returncode}). Останавливаюсь.")


def pick_idea_interactively() -> str:
    candidates = [i for i in common.load_backlog() if i["status"] == "backlog"]
    if not candidates:
        raise SystemExit("В backlog нет новых идей.")

    print("\nНовые идеи:")
    for i, idea in enumerate(candidates):
        print(f"  {i}) [{idea['visual_richness']:>6}] {idea['title']} ({idea['id']})")

    choice = input("\nКакую делать? (номер): ").strip()
    try:
        return candidates[int(choice)]["id"]
    except (ValueError, IndexError):
        raise SystemExit("Некорректный выбор.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--idea-id", default=None)
    parser.add_argument("--count", type=int, default=10, help="сколько идей сгенерировать (шаг 1)")
    parser.add_argument("--from-step", type=int, default=2, choices=list(STEP_SCRIPTS.keys()))
    parser.add_argument("--crossfade", type=float, default=0.0)
    parser.add_argument("--no-music", action="store_true")
    args = parser.parse_args()

    idea_id = args.idea_id
    if not idea_id:
        run_step("01_ideas.py", ["--count", str(args.count)])
        idea_id = pick_idea_interactively()

    extra_args = {
        6: (["--crossfade", str(args.crossfade)] if args.crossfade else [])
        + (["--no-music"] if args.no_music else []),
    }

    for step in range(args.from_step, 9):
        run_step(STEP_SCRIPTS[step], [idea_id, *extra_args.get(step, [])])

    print(f"\n=== 09_review.py {idea_id} ===")
    review = subprocess.run([sys.executable, str(SCRIPT_DIR / "09_review.py"), idea_id])
    if review.returncode != 0:
        raise SystemExit("Проверка не пройдена корректно, останавливаюсь.")

    idea = common.find_idea(idea_id)
    status = idea["status"] if idea else None

    if status == "approved":
        run_step("10_publish.py", [idea_id])
    elif status and status.startswith("redo:"):
        step = int(status.split(":")[1])
        print(f"\nПосле правок запустите: python run_pipeline.py --idea-id {idea_id} --from-step {step}")
    else:
        print(f"\nСтатус идеи: {status}. Публикация не запущена.")


if __name__ == "__main__":
    main()
