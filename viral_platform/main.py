"""FastAPI dashboard: discover viral Shorts, view them, transcribe, build a
storyboard, and generate an original script.

Run from the repo root: uvicorn viral_platform.main:app --reload --port 8001
"""

import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, db, script_writer, storyboard, transcribe, youtube_discovery

BASE_DIR = os.path.dirname(__file__)

app = FastAPI(title="Viral Video Platform")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

db.init_db()


@app.get("/")
def index(request: Request):
    videos = db.list_videos()
    return templates.TemplateResponse(request, "index.html", {"videos": videos})


@app.post("/discover")
def discover(query: str = Form(""), days: int = Form(7)):
    youtube_discovery.discover_trending_shorts(query=query, published_after_days=days)
    return RedirectResponse("/", status_code=303)


@app.get("/video/{video_id}")
def video_detail(request: Request, video_id: str):
    video = db.get_video(video_id)
    transcript = db.get_transcript(video_id)
    board = db.get_storyboard(video_id)
    scripts = db.list_scripts(video_id)
    return templates.TemplateResponse(
        request,
        "video.html",
        {
            "video": video,
            "transcript": transcript,
            "storyboard": board,
            "scripts": scripts,
            "niche_context": config.read_niche_context(),
        },
    )


@app.post("/video/{video_id}/transcribe")
def do_transcribe(video_id: str):
    transcribe.transcribe_video(video_id, force=True)
    return RedirectResponse(f"/video/{video_id}", status_code=303)


@app.post("/video/{video_id}/storyboard")
def do_storyboard(video_id: str):
    storyboard.build_storyboard(video_id, force=True)
    return RedirectResponse(f"/video/{video_id}", status_code=303)


@app.post("/video/{video_id}/script")
def do_script(video_id: str, niche_context: str = Form(""), extra_instructions: str = Form("")):
    script_writer.generate_script(video_id, niche_context, extra_instructions)
    return RedirectResponse(f"/video/{video_id}", status_code=303)
