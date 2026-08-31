#!/usr/bin/env python3
"""Assembles the final video: syncs footage to narration length per block,
concatenates blocks, mixes in music, normalizes loudness, writes subtitles.

Usage: python 06_assemble.py <idea_id> [--crossfade 0.4] [--no-music] [--burn-subtitles]

Design notes:
- Each block's picture track is built to *exactly* match that block's audio
  duration (clips are looped/trimmed with -stream_loop + -t), so narration
  never runs out of footage or waits on a frozen frame.
- Blocks with no downloaded footage get a plain color placeholder instead of
  crashing the whole render — the gap is reported at the end so it can be
  filled in before publishing.
- Crossfades (--crossfade) are applied between the clips inside a block via
  ffmpeg's xfade filter. This is more fragile than the hard-cut default
  (off, i.e. --crossfade 0) — test on one video before relying on it.
"""

import argparse
import glob
import os
import shutil
import subprocess
import tempfile

import config
import common

WIDTH, HEIGHT = config.RESOLUTIONS[config.TARGET_ORIENTATION]
FPS = 30


def ensure_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise SystemExit(
            "ffmpeg/ffprobe не найдены. Установите: apt install ffmpeg "
            "(или brew install ffmpeg на macOS)."
        )


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Команда упала: {' '.join(cmd)}\n--- stderr ---\n{result.stderr[-4000:]}"
        )


def ffprobe_duration(path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", path,
        ],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def build_segment(clip_path: str, length: float, out_path: str) -> None:
    """Loop/trim clip_path to exactly `length` seconds at the target res/fps."""
    run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", clip_path,
        "-t", f"{length:.3f}",
        "-vf",
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1,fps={FPS}",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        out_path,
    ])


def build_placeholder(length: float, out_path: str) -> None:
    run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=0x222222:s={WIDTH}x{HEIGHT}:d={length:.3f}:r={FPS}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        out_path,
    ])


def concat_hard_cut(segment_paths: list[str], out_path: str, work_dir: str) -> None:
    filelist = os.path.join(work_dir, f"concat_{os.path.basename(out_path)}.txt")
    with open(filelist, "w") as f:
        for p in segment_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", filelist, "-c", "copy", out_path])


def concat_with_xfade(segment_paths: list[str], per_clip_len: float, xfade: float, out_path: str) -> None:
    n = len(segment_paths)
    inputs = []
    for p in segment_paths:
        inputs += ["-i", p]

    filters = []
    prev_label = "0:v"
    for i in range(1, n):
        offset = i * (per_clip_len - xfade)
        out_label = f"v{i}" if i < n - 1 else "vout"
        filters.append(
            f"[{prev_label}][{i}:v]xfade=transition=fade:duration={xfade:.3f}:"
            f"offset={offset:.3f}[{out_label}]"
        )
        prev_label = out_label

    run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        out_path,
    ])


def mux_video_audio(video_path: str, audio_path: str, out_path: str) -> None:
    run([
        "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        out_path,
    ])


def mix_music(video_path: str, music_path: str, out_path: str, volume: float = 0.15) -> None:
    run([
        "ffmpeg", "-y", "-i", video_path, "-stream_loop", "-1", "-i", music_path,
        "-filter_complex",
        f"[1:a]volume={volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        out_path,
    ])


def apply_loudnorm(in_path: str, out_path: str) -> None:
    run([
        "ffmpeg", "-y", "-i", in_path,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "copy",
        out_path,
    ])


def burn_subtitles(in_path: str, srt_path: str, out_path: str) -> None:
    run([
        "ffmpeg", "-y", "-i", in_path,
        "-vf", f"subtitles={srt_path}",
        "-c:a", "copy",
        out_path,
    ])


def _srt_timestamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(blocks: list[dict], out_path: str) -> None:
    lines = []
    for i, b in enumerate(blocks, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(b['start'])} --> {_srt_timestamp(b['end'])}")
        lines.append(b["text"])
        lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def assemble_block(idea_id: str, block: dict, work_dir: str, crossfade: float) -> tuple[str, bool]:
    """Returns (path to block_final.mp4, had_footage)."""
    audio_path = os.path.join(common.audio_dir(idea_id), f"{block['index']}.mp3")
    if not os.path.exists(audio_path):
        raise SystemExit(
            f"Нет озвучки для блока {block['index']}. Сначала запустите: "
            f"python 05_tts.py {idea_id}"
        )
    duration = ffprobe_duration(audio_path)

    clips = sorted(glob.glob(os.path.join(common.raw_footage_dir(idea_id), f"{block['index']}_*.mp4")))
    video_path = os.path.join(work_dir, f"video_{block['index']}.mp4")
    had_footage = bool(clips)

    if not clips:
        build_placeholder(duration, video_path)
    elif len(clips) == 1:
        build_segment(clips[0], duration, video_path)
    else:
        xf = crossfade if crossfade > 0 else 0.0
        per_clip_len = (duration + xf * (len(clips) - 1)) / len(clips)
        segments = []
        for j, clip in enumerate(clips):
            seg_path = os.path.join(work_dir, f"seg_{block['index']}_{j}.mp4")
            build_segment(clip, per_clip_len, seg_path)
            segments.append(seg_path)
        if xf > 0:
            concat_with_xfade(segments, per_clip_len, xf, video_path)
        else:
            concat_hard_cut(segments, video_path, work_dir)

    final_path = os.path.join(work_dir, f"block_final_{block['index']}.mp4")
    mux_video_audio(video_path, audio_path, final_path)
    return final_path, had_footage


def assemble(idea_id: str, crossfade: float, use_music: bool, burn_subs: bool) -> str:
    script = common.load_script(idea_id)
    blocks = script["blocks"]

    with tempfile.TemporaryDirectory(prefix=f"madeinside_{idea_id}_") as work_dir:
        block_finals = []
        gaps = []
        for block in blocks:
            path, had_footage = assemble_block(idea_id, block, work_dir, crossfade)
            block_finals.append(path)
            if not had_footage:
                gaps.append(f"  - блок {block['index']} ({block['label']}): нет footage, заглушка")

        stage1 = os.path.join(work_dir, "concat.mp4")
        concat_hard_cut(block_finals, stage1, work_dir)

        srt_out = common.srt_path(idea_id)
        os.makedirs(os.path.dirname(srt_out), exist_ok=True)
        generate_srt(blocks, srt_out)

        current = stage1
        if use_music and config.MUSIC_PATH:
            with_music = os.path.join(work_dir, "with_music.mp4")
            mix_music(current, config.MUSIC_PATH, with_music)
            current = with_music

        normalized = os.path.join(work_dir, "normalized.mp4")
        apply_loudnorm(current, normalized)
        current = normalized

        if burn_subs:
            with_subs = os.path.join(work_dir, "with_subs.mp4")
            burn_subtitles(current, srt_out, with_subs)
            current = with_subs

        final_out = common.render_path(idea_id)
        os.makedirs(os.path.dirname(final_out), exist_ok=True)
        shutil.copy(current, final_out)

        if gaps:
            print("ВНИМАНИЕ — блоки без footage (заглушка вместо кадров):")
            print("\n".join(gaps))
            print("Докачайте клипы (python 04_fetch_footage.py) и перезапустите сборку.\n")

        return final_out


def main():
    ensure_ffmpeg()
    parser = argparse.ArgumentParser()
    parser.add_argument("idea_id")
    parser.add_argument("--crossfade", type=float, default=0.0, help="секунды, 0 = жёсткая склейка")
    parser.add_argument("--no-music", action="store_true")
    parser.add_argument("--burn-subtitles", action="store_true")
    args = parser.parse_args()

    out_path = assemble(args.idea_id, args.crossfade, not args.no_music, args.burn_subtitles)
    print(f"Готово: {out_path}")
    print(f"Субтитры: {common.srt_path(args.idea_id)}")


if __name__ == "__main__":
    main()
