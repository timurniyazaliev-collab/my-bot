#!/usr/bin/env python3
"""Manual quality gate — opens the render and metadata, waits for a verdict.

Usage: python 09_review.py <idea_id>

Deliberately not automated: unedited AI content gets suppressed by YouTube,
and this is the one checkpoint that catches a bad script, a mistimed cut,
or footage that doesn't match the narration before it goes out.
"""

import argparse
import platform
import subprocess

import common

VALID_REDO_STEPS = {2, 3, 4, 5, 6, 7, 8}


def open_file(path: str) -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", path], check=False)
        elif system == "Windows":
            import os

            os.startfile(path)  # noqa: no cross-platform alternative
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception as exc:
        print(f"Не удалось открыть {path} автоматически ({exc}) — откройте вручную.")


def print_metadata(idea_id: str) -> None:
    metadata = common.read_json(common.metadata_path(idea_id))
    if not metadata:
        print("Метаданные ещё не сгенерированы (python 08_metadata.py).")
        return
    print(f"\nTitle: {metadata['title']}")
    print(f"\nDescription:\n{metadata['description']}")
    print(f"\nTags: {', '.join(metadata['tags'])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("idea_id")
    args = parser.parse_args()
    idea_id = args.idea_id

    idea = common.find_idea(idea_id)
    if not idea:
        raise SystemExit(f"Идея '{idea_id}' не найдена в ideas_backlog.json")

    video_path = common.render_path(idea_id)
    print(f"Видео: {video_path}")
    open_file(video_path)

    print_metadata(idea_id)

    for i in range(3):
        thumb = common.thumbnail_path(idea_id, i)
        try:
            open_file(thumb)
        except Exception:
            pass

    print(
        "\nВведите решение: approve / reject / redo-step-N "
        "(N — номер шага 2-8, например redo-step-3)"
    )
    answer = input("> ").strip().lower()

    if answer == "approve":
        common.set_idea_status(idea_id, "approved")
        print(f"Одобрено. Публикация: python 10_publish.py {idea_id}")
    elif answer == "reject":
        common.set_idea_status(idea_id, "rejected")
        print("Отклонено.")
    elif answer.startswith("redo-step-"):
        try:
            step = int(answer.removeprefix("redo-step-"))
        except ValueError:
            step = None
        if step not in VALID_REDO_STEPS:
            raise SystemExit(f"Неизвестный шаг: {answer}")
        common.set_idea_status(idea_id, f"redo:{step}")
        script_by_step = {
            2: "02_script.py", 3: "03_shotlist.py", 4: "04_fetch_footage.py",
            5: "05_tts.py", 6: "06_assemble.py", 7: "07_thumbnail.py", 8: "08_metadata.py",
        }
        print(f"Запустите заново: python {script_by_step[step]} {idea_id}")
        print(f"(и все шаги после него — идею перезапустите через run_pipeline.py --idea-id {idea_id} --from-step {step})")
    else:
        raise SystemExit(f"Не понял ответ: '{answer}'")


if __name__ == "__main__":
    main()
