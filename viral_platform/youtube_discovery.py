"""Finds trending YouTube Shorts via the official YouTube Data API v3.

Uses plain HTTP (requests) instead of the google-api-python-client SDK —
one dependency less, and the API surface we need is tiny (search + videos).
"""

import re
from datetime import datetime, timedelta, timezone

import requests

from . import config, db

API_BASE = "https://www.googleapis.com/youtube/v3"

_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)


def parse_iso8601_duration(value: str) -> int:
    """'PT1M30S' -> 90. Returns 0 for anything it can't parse."""
    match = _DURATION_RE.match(value or "")
    if not match:
        return 0
    parts = match.groupdict()
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = int(parts["seconds"] or 0)
    return hours * 3600 + minutes * 60 + seconds


def compute_viral_score(view_count: int, published_at: str) -> float:
    """Views per day since publish — surfaces videos going viral *now*,
    not just old videos that slowly racked up huge totals."""
    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - published).total_seconds() / 86400
    return view_count / max(age_days, 0.5)


def discover_trending_shorts(
    query: str = "",
    max_results: int = 25,
    published_after_days: int = 7,
) -> list[dict]:
    """Searches recent, high-view vertical Shorts, saves them to the DB,
    and returns the parsed video list (also DB-ready dicts)."""
    if not config.YOUTUBE_API_KEY:
        raise RuntimeError(
            "YOUTUBE_API_KEY не задан. Добавьте его в viral_platform/.env"
        )

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=published_after_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    search_params = {
        "key": config.YOUTUBE_API_KEY,
        "part": "id",
        "type": "video",
        "videoDuration": "short",
        "order": "viewCount",
        "publishedAfter": published_after,
        "maxResults": min(max_results, 50),
        "safeSearch": "none",
    }
    if query:
        search_params["q"] = query

    search_resp = requests.get(f"{API_BASE}/search", params=search_params, timeout=20)
    search_resp.raise_for_status()
    video_ids = [item["id"]["videoId"] for item in search_resp.json().get("items", [])]
    if not video_ids:
        return []

    videos_resp = requests.get(
        f"{API_BASE}/videos",
        params={
            "key": config.YOUTUBE_API_KEY,
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
        },
        timeout=20,
    )
    videos_resp.raise_for_status()

    results = []
    for item in videos_resp.json().get("items", []):
        duration_seconds = parse_iso8601_duration(
            item["contentDetails"]["duration"]
        )
        if duration_seconds > config.MAX_SHORT_SECONDS:
            continue  # not actually a Short despite videoDuration=short

        snippet = item["snippet"]
        stats = item.get("statistics", {})
        view_count = int(stats.get("viewCount", 0))

        video = {
            "video_id": item["id"],
            "title": snippet["title"],
            "channel_title": snippet["channelTitle"],
            "published_at": snippet["publishedAt"],
            "duration_seconds": duration_seconds,
            "view_count": view_count,
            "like_count": int(stats.get("likeCount", 0)),
            "comment_count": int(stats.get("commentCount", 0)),
            "viral_score": round(
                compute_viral_score(view_count, snippet["publishedAt"]), 1
            ),
            "search_query": query,
            "thumbnail_url": snippet["thumbnails"]
            .get("high", snippet["thumbnails"]["default"])["url"],
        }
        db.upsert_video(video)
        results.append(video)

    results.sort(key=lambda v: v["viral_score"], reverse=True)
    return results
