#!/usr/bin/env python3
"""Downloads stock footage for a shotlist from Pexels and logs licenses.

Usage: python 04_fetch_footage.py <idea_id> [--per-query 1]

Videvo doesn't offer a stable public search/download API for scripted use
(as of writing) — if VIDEVO_API_KEY is set this script just says so and
skips it; clips from Videvo still have to be downloaded by hand into the
same raw/ folder, and logged manually in sources.txt.
"""

import argparse
import datetime
import os

import requests
import config
import common

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PEXELS_LICENSE_NOTE = (
    "Pexels License — free for commercial & non-commercial use, "
    "no attribution required (attribution appreciated)."
)


def _pick_video_file(video: dict, orientation: str) -> dict | None:
    files = video.get("video_files", [])
    want_landscape = orientation == "horizontal"

    def matches_orientation(f):
        return (f["width"] >= f["height"]) == want_landscape

    candidates = [f for f in files if matches_orientation(f)] or files
    if not candidates:
        return None
    # prefer hd — good enough quality without huge downloads
    hd = [f for f in candidates if f.get("quality") == "hd"]
    return (hd or candidates)[0]


def search_pexels(query: str, per_page: int = 3) -> list[dict]:
    resp = requests.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": config.PEXELS_API_KEY},
        params={"query": query, "per_page": per_page, "size": "medium"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("videos", [])


def download_file(url: str, dest_path: str) -> None:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)


def log_source(sources_file: str, lines: list[str]) -> None:
    os.makedirs(os.path.dirname(sources_file), exist_ok=True)
    with open(sources_file, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")


def fetch_for_block(idea_id: str, block: dict, per_query: int) -> int:
    raw_dir = common.raw_footage_dir(idea_id)
    sources_file = common.sources_path(idea_id)
    downloaded = 0

    for query in block["queries"]:
        videos = search_pexels(query, per_page=per_query)
        if not videos:
            print(f"  [{block['index']}] '{query}': ничего не найдено")
            continue

        for n, video in enumerate(videos[:per_query]):
            file_info = _pick_video_file(video, config.TARGET_ORIENTATION)
            if not file_info:
                continue
            dest = os.path.join(raw_dir, f"{block['index']}_{query[:20].replace(' ', '_')}_{n}.mp4")
            download_file(file_info["link"], dest)
            downloaded += 1

            log_source(
                sources_file,
                [
                    f"[{datetime.datetime.now().isoformat(timespec='seconds')}] "
                    f"block {block['index']} query='{query}'",
                    f"  file: {os.path.basename(dest)}",
                    f"  source: https://www.pexels.com/video/{video['id']}/",
                    f"  author: {video['user']['name']} ({video['user']['url']})",
                    f"  license: {PEXELS_LICENSE_NOTE}",
                ],
            )
            print(f"  [{block['index']}] '{query}' -> {os.path.basename(dest)}")

    return downloaded


def main():
    if not config.PEXELS_API_KEY:
        raise SystemExit("PEXELS_API_KEY не задан. Добавьте его в madeinside/.env")

    parser = argparse.ArgumentParser()
    parser.add_argument("idea_id")
    parser.add_argument("--per-query", type=int, default=1, help="клипов на запрос")
    args = parser.parse_args()

    shotlist = common.read_json(common.shotlist_path(args.idea_id))
    if not shotlist:
        raise SystemExit(
            f"Нет shotlist для '{args.idea_id}'. Сначала запустите: "
            f"python 03_shotlist.py {args.idea_id}"
        )

    if config.VIDEVO_API_KEY:
        print(
            "VIDEVO_API_KEY задан, но у Videvo нет стабильного публичного API "
            "для скачивания по запросу — клипы оттуда придётся добавлять "
            f"вручную в {common.raw_footage_dir(args.idea_id)} "
            f"и вписывать в {common.sources_path(args.idea_id)}.\n"
        )

    total = 0
    for block in shotlist["blocks"]:
        total += fetch_for_block(args.idea_id, block, args.per_query)

    print(f"\nСкачано клипов: {total}")
    print(f"Источники и лицензии: {common.sources_path(args.idea_id)}")


if __name__ == "__main__":
    main()
