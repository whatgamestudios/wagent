"""FastAPI app deployed as a Vercel serverless function.

Routes (see vercel.json for how /api/* is rewritten to this file):
    POST /api/press-release     build a press release on demand (used by the
                                 site's "Execute Daily Tasks" button)
    GET  /api/cron/daily-tasks  the scheduled daily_tasks job Vercel Cron hits
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from worcadian_agent.agent import build_press_release  # noqa: E402
from worcadian_agent.daily_tasks import daily_tasks  # noqa: E402

app = FastAPI()

OUTPUT_DIR = "/tmp/output"


class PressReleaseRequest(BaseModel):
    day: int | None = None


@app.post("/api/press-release")
def generate_press_release(payload: PressReleaseRequest) -> dict:
    try:
        path = build_press_release(day=payload.day, output_dir=OUTPUT_DIR)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    resolved_game_day = Path(path).stem.split("-", 1)[0]
    return {"game_day": resolved_game_day, "text": Path(path).read_text()}


@app.get("/api/cron/daily-tasks")
def run_daily_tasks(authorization: str | None = Header(default=None)) -> dict:
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        result = daily_tasks()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "ok", **result}


# Serves index.html for local dev (`uvicorn api.index:app`) so the page and
# API share an origin. In production Vercel serves index.html as a static
# file directly and never reaches this app for "/", since vercel.json only
# rewrites /api/* here — this mount is inert there.
app.mount("/", StaticFiles(directory=str(Path(__file__).resolve().parent.parent), html=True), name="static")
