#!/usr/bin/env python3
"""Generates narration audio for every script block.

Usage: python 05_tts.py <idea_id>

Provider is config.TTS_PROVIDER ("elevenlabs" or "google"):
- elevenlabs: higher quality, paid past the free tier.
- google: cheaper (Google Cloud Text-to-Speech), needs
  GOOGLE_APPLICATION_CREDENTIALS pointing at a service account json.
"""

import argparse
import os

import requests
import config
import common

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def synth_elevenlabs(text: str, dest_path: str) -> None:
    resp = requests.post(
        ELEVENLABS_TTS_URL.format(voice_id=config.ELEVENLABS_VOICE_ID),
        headers={
            "xi-api-key": config.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": config.ELEVENLABS_MODEL_ID,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=120,
    )
    resp.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(resp.content)


def synth_google(text: str, dest_path: str) -> None:
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            language_code="en-US", name=config.GOOGLE_TTS_VOICE
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        ),
    )
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(response.audio_content)


def synth(text: str, dest_path: str) -> None:
    if config.TTS_PROVIDER == "google":
        synth_google(text, dest_path)
    else:
        synth_elevenlabs(text, dest_path)


def main():
    if config.TTS_PROVIDER == "elevenlabs" and not (
        config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID
    ):
        raise SystemExit(
            "ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID не заданы в madeinside/.env "
            "(или переключите TTS_PROVIDER=google)"
        )

    parser = argparse.ArgumentParser()
    parser.add_argument("idea_id")
    args = parser.parse_args()

    script = common.load_script(args.idea_id)
    audio_dir = common.audio_dir(args.idea_id)

    for block in script["blocks"]:
        dest = os.path.join(audio_dir, f"{block['index']}.mp3")
        synth(block["text"], dest)
        print(f"[{block['index']}] {block['label']} -> {dest}")

    print(f"\nОзвучка готова: {audio_dir}")


if __name__ == "__main__":
    main()
