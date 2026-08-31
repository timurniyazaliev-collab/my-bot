"""Downloads a video's audio and transcribes it with faster-whisper.

Runs locally (no paid transcription API) — needs ffmpeg on the machine
for yt-dlp to extract audio.
"""

import os
import tempfile

import yt_dlp

from . import config, db

_model = None  # lazy singleton — loading the whisper model is slow


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(config.WHISPER_MODEL_SIZE, compute_type="int8")
    return _model


def _download_audio(video_id: str, tmp_dir: str) -> str:
    out_template = os.path.join(tmp_dir, f"{video_id}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
        "quiet": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    return os.path.join(tmp_dir, f"{video_id}.mp3")


def transcribe_video(video_id: str, force: bool = False) -> dict:
    """Returns {"text": str, "segments": [{"start", "end", "text"}]}."""
    if not force:
        cached = db.get_transcript(video_id)
        if cached:
            return cached

    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = _download_audio(video_id, tmp_dir)
        model = _get_model()
        segments_iter, _info = model.transcribe(audio_path, vad_filter=True)
        segments = [
            {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segments_iter
        ]

    text = " ".join(s["text"] for s in segments)
    db.save_transcript(video_id, text, segments)
    return {"video_id": video_id, "text": text, "segments": segments}
