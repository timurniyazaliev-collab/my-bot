#!/usr/bin/env python3
"""Composes 2-3 thumbnail variants from a video frame + bold text overlay.

Usage: python 07_thumbnail.py <idea_id> [--text "CUSTOM TEXT"] [--variants 3]

No image-generation API was in the account's key list (Anthropic, Pexels,
ElevenLabs, YouTube/Google — no DALL-E/Stability/etc.), so this composes
thumbnails the way a lot of real faceless channels do it: a striking frame
from the footage + bold text, via Pillow. If you'd rather wire up an
image-gen model instead, that's a config swap away — say the word.

Thumbnails are always 1280x720 (YouTube's fixed thumbnail aspect, 16:9,
regardless of the video's own orientation).
"""

import argparse
import glob
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

import config
import common

THUMB_SIZE = (1280, 720)


def _find_source_clip(idea_id: str) -> str | None:
    shotlist = common.read_json(common.shotlist_path(idea_id))
    indices = [b["index"] for b in shotlist["blocks"]] if shotlist else range(10)
    for index in indices:
        clips = sorted(glob.glob(os.path.join(common.raw_footage_dir(idea_id), f"{index}_*.mp4")))
        if clips:
            return clips[0]
    return None


def _clip_duration(clip_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", clip_path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def _extract_frame(clip_path: str, at_fraction: float, out_path: str) -> None:
    timestamp = _clip_duration(clip_path) * at_fraction
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{timestamp:.2f}", "-i", clip_path, "-vframes", "1", "-q:v", "2", out_path],
        check=True, capture_output=True,
    )


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(config.THUMBNAIL_FONT_PATH, size)
    except OSError:
        print(
            f"Шрифт {config.THUMBNAIL_FONT_PATH} не найден — текст будет мелким. "
            "Укажите THUMBNAIL_FONT_PATH в madeinside/.env."
        )
        return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def compose_thumbnail(base_image: Image.Image, text: str, text_position: str, out_path: str) -> None:
    img = base_image.copy().resize(THUMB_SIZE)
    draw = ImageDraw.Draw(img, "RGBA")

    font = _load_font(size=88)
    margin = 48
    lines = _wrap_text(draw, text.upper(), font, THUMB_SIZE[0] - 2 * margin)
    line_height = font.size + 12
    block_height = line_height * len(lines) + 40

    if text_position == "bottom":
        band_top = THUMB_SIZE[1] - block_height
    elif text_position == "top":
        band_top = 0
    else:  # center
        band_top = (THUMB_SIZE[1] - block_height) // 2

    draw.rectangle([0, band_top, THUMB_SIZE[0], band_top + block_height], fill=(0, 0, 0, 160))

    y = band_top + 20
    for line in lines:
        width = draw.textlength(line, font=font)
        x = (THUMB_SIZE[0] - width) // 2
        draw.text((x, y), line, font=font, fill="white", stroke_width=4, stroke_fill="black")
        y += line_height

    img.convert("RGB").save(out_path, quality=92)


def generate_thumbnails(idea_id: str, text: str, variants: int) -> list[str]:
    clip = _find_source_clip(idea_id)
    positions = ["bottom", "top", "center"][:variants]
    fractions = [0.15, 0.5, 0.8][:variants]

    out_dir = os.path.dirname(common.thumbnail_path(idea_id, 0))
    os.makedirs(out_dir, exist_ok=True)

    outputs = []
    for i, (position, fraction) in enumerate(zip(positions, fractions)):
        out_path = common.thumbnail_path(idea_id, i)
        if clip:
            frame_path = os.path.join(out_dir, f"_frame_{i}.jpg")
            _extract_frame(clip, fraction, frame_path)
            base = Image.open(frame_path)
        else:
            base = Image.new("RGB", THUMB_SIZE, (34, 34, 34))
        compose_thumbnail(base, text, position, out_path)
        outputs.append(out_path)

    if not clip:
        print(
            "Нет скачанного footage — превью на сплошном фоне. "
            "Запустите python 04_fetch_footage.py и пересоздайте превью."
        )
    return outputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("idea_id")
    parser.add_argument("--text", default=None, help="текст на превью (по умолчанию — хук идеи)")
    parser.add_argument("--variants", type=int, default=3)
    args = parser.parse_args()

    idea = common.find_idea(args.idea_id)
    if not idea:
        raise SystemExit(f"Идея '{args.idea_id}' не найдена в ideas_backlog.json")

    text = args.text or " ".join(idea["hook"].split()[:6])
    outputs = generate_thumbnails(args.idea_id, text, args.variants)

    print(f"Готово {len(outputs)} вариантов превью:")
    for p in outputs:
        print(f"  {p}")


if __name__ == "__main__":
    main()
