#!/usr/bin/env python3
"""Uploads the approved video to YouTube, scheduled per schedule.json.

Usage: python 10_publish.py <idea_id> [--publish-at 2026-09-02T20:00:00Z]

First run opens a browser for a one-time OAuth consent (needs
madeinside/client_secret.json from Google Cloud Console — a Desktop app
OAuth client with the YouTube Data API v3 enabled); the token is then
cached at madeinside/token.json and reused silently after that.
"""

import argparse
import datetime
import os

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9, shouldn't happen but keep it explicit
    ZoneInfo = None

import config
import common

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def get_credentials():
    # Imported lazily: google-auth pulls in a native `cryptography` build
    # that some systems (this repo's dev sandbox included) have conflicting
    # versions of, and every other step in the pipeline works fine without it.
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(config.YOUTUBE_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(config.YOUTUBE_TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(config.YOUTUBE_CLIENT_SECRETS_PATH):
                raise SystemExit(
                    f"Нет {config.YOUTUBE_CLIENT_SECRETS_PATH}. Скачайте OAuth-клиент "
                    "(Desktop app) в Google Cloud Console и сохраните туда."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                config.YOUTUBE_CLIENT_SECRETS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(config.YOUTUBE_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def load_schedule() -> dict:
    schedule = common.read_json(config.SCHEDULE_PATH)
    if not schedule:
        raise SystemExit(f"Нет {config.SCHEDULE_PATH}. Создайте расписание публикаций.")
    return schedule


def already_scheduled_times() -> list[datetime.datetime]:
    times = []
    for idea in common.load_backlog():
        ts = idea.get("scheduled_at")
        if ts:
            times.append(datetime.datetime.fromisoformat(ts))
    return times


def compute_next_slot(schedule: dict, used: list[datetime.datetime]) -> datetime.datetime:
    if ZoneInfo is None:
        raise SystemExit("Нужен Python 3.9+ (модуль zoneinfo) для расчёта расписания.")

    tz = ZoneInfo(schedule["timezone"])
    hour, minute = (int(x) for x in schedule["time"].split(":"))
    weekdays = {WEEKDAYS[d.lower()] for d in schedule["days"]}

    used_utc = {t.astimezone(datetime.timezone.utc).replace(second=0, microsecond=0) for t in used}

    day = datetime.datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(60):  # search up to 60 days ahead
        if day.weekday() in weekdays:
            candidate = day.replace(hour=hour, minute=minute)
            candidate_utc = candidate.astimezone(datetime.timezone.utc).replace(second=0, microsecond=0)
            if candidate_utc > datetime.datetime.now(datetime.timezone.utc) and candidate_utc not in used_utc:
                return candidate_utc
        day += datetime.timedelta(days=1)
    raise SystemExit("Не удалось найти свободный слот в расписании за 60 дней.")


def upload_video(youtube, idea_id: str, metadata: dict, publish_at: str) -> str:
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(common.render_path(idea_id), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  загрузка: {int(status.progress() * 100)}%")
    return response["id"]


def set_thumbnail(youtube, video_id: str, thumbnail_path: str) -> None:
    if not os.path.exists(thumbnail_path):
        return
    from googleapiclient.http import MediaFileUpload

    youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_path)).execute()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("idea_id")
    parser.add_argument("--publish-at", default=None, help="RFC3339 UTC, например 2026-09-02T20:00:00Z")
    parser.add_argument("--thumbnail", type=int, default=0, help="номер варианта превью (0-2)")
    args = parser.parse_args()

    idea = common.find_idea(args.idea_id)
    if not idea:
        raise SystemExit(f"Идея '{args.idea_id}' не найдена в ideas_backlog.json")
    if idea.get("status") != "approved":
        raise SystemExit(
            f"Идея имеет статус '{idea.get('status')}', а не 'approved'. "
            f"Сначала пройдите проверку: python 09_review.py {args.idea_id}"
        )

    metadata = common.read_json(common.metadata_path(args.idea_id))
    if not metadata:
        raise SystemExit(f"Нет метаданных. Сначала: python 08_metadata.py {args.idea_id}")
    if not os.path.exists(common.render_path(args.idea_id)):
        raise SystemExit(f"Нет рендера. Сначала: python 06_assemble.py {args.idea_id}")

    if args.publish_at:
        publish_at = args.publish_at
    else:
        schedule = load_schedule()
        slot = compute_next_slot(schedule, already_scheduled_times())
        publish_at = slot.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Публикация запланирована на {publish_at} (UTC)")

    from googleapiclient.discovery import build

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    video_id = upload_video(youtube, args.idea_id, metadata, publish_at)
    set_thumbnail(youtube, video_id, common.thumbnail_path(args.idea_id, args.thumbnail))

    ideas = common.load_backlog()
    for i in ideas:
        if i["id"] == args.idea_id:
            i["status"] = "scheduled"
            i["scheduled_at"] = publish_at
            i["youtube_video_id"] = video_id
    common.save_backlog(ideas)

    print(f"\nЗагружено: https://studio.youtube.com/video/{video_id}/edit")
    print(f"Выйдет в эфир: {publish_at}")


if __name__ == "__main__":
    main()
