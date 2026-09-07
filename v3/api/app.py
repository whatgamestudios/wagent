"""FastAPI app deployed as a Vercel serverless function.

Deliberately not named index.py: "index" is a special filename in Vercel's
filesystem routing (it collapses to the parent path, the same way
index.html does for static hosting), which made the rewrite destination
genuinely ambiguous between "/api" and "/api/index" and cost real debugging
time. "app.py" has no special meaning, so it can only ever route to exactly
/api/app -- see vercel.json's "rewrites" entry, which must point there.

IMPORTANT, confirmed empirically (not just from docs): Vercel's rewrite
preserves the original HTTP method and body but does NOT preserve the
original request path -- every request under /api/* arrives here with
request.url.path literally equal to "/api/app" (the rewrite's destination),
regardless of whether the browser called /api/press-release or
/api/cron/daily-tasks. Only the method still distinguishes them. That's why
every route below is registered at BOTH its real/friendly path (so direct
curl, `uvicorn`, and `vercel dev` testing all still work without going
through a rewrite) AND "/api/app" (what production traffic actually looks
like once Vercel's rewrite has run) -- do not remove the "/api/app"
decorator thinking it's a leftover duplicate.

Routes (see vercel.json for how /api/* is rewritten to this file):
    POST /api/press-release     build a press release on demand (used by the
                                 site's "Execute Daily Tasks" button)
    GET  /api/cron/daily-tasks  the scheduled daily_tasks job Vercel Cron hits

Logging: configured below with logging.basicConfig() so every logger.info()/
logger.exception() call in this module and in worcadian_agent.* reaches
stderr, which Vercel captures as Function Logs. A request-logging middleware
logs every request that actually reaches this app (method, path, status,
duration) -- if a request doesn't show up there at all, it never reached the
Python function (a routing/rewrite problem, not an app-code problem).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("worcadian_agent.api")

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from worcadian_agent.agent import build_press_release, gather_facts  # noqa: E402
from worcadian_agent.daily_tasks import daily_tasks  # noqa: E402
from worcadian_agent.dictionary_client import lookup_words  # noqa: E402

app = FastAPI()

OUTPUT_DIR = "/tmp/output"


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    logger.info("request start method=%s path=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request raised an unhandled exception method=%s path=%s", request.method, request.url.path)
        raise
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "request end method=%s path=%s status=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


class PressReleaseRequest(BaseModel):
    day: int | None = None


@app.post("/api/press-release")
@app.post("/api/app")  # see module docstring: production traffic arrives at this path, not the one above
def generate_press_release(payload: PressReleaseRequest) -> dict:
    logger.info("press-release requested day=%s", payload.day)
    try:
        facts_bundle = gather_facts(payload.day)
        words_to_look_up = [facts_bundle["seed_word"]] + [w["word"] for w in facts_bundle["notable_words"]]
        definitions = lookup_words(words_to_look_up)
        path = build_press_release(facts_bundle, output_dir=OUTPUT_DIR)
    except Exception as exc:
        logger.exception("press-release generation failed day=%s", payload.day)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("press-release generated game_day=%s path=%s", facts_bundle["game_day"], path)
    return {
        "game_day": facts_bundle["game_day"],
        "text": Path(path).read_text(),
        "definitions": definitions,
    }


@app.get("/api/cron/daily-tasks")
@app.get("/api/app")  # see module docstring: production traffic arrives at this path, not the one above
def run_daily_tasks(authorization: str | None = Header(default=None)) -> dict:
    logger.info("daily-tasks cron invoked")
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret and authorization != f"Bearer {cron_secret}":
        logger.warning("daily-tasks rejected: missing or invalid CRON_SECRET bearer token")
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        result = daily_tasks()
    except Exception as exc:
        logger.exception("daily-tasks failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("daily-tasks completed result=%s", result)
    return {"status": "ok", **result}


# Serves index.html for local dev (`uvicorn api.app:app`) so the page and
# API share an origin. In production Vercel serves index.html as a static
# file directly and never reaches this app for "/", since vercel.json only
# rewrites /api/* here — this mount is inert there.
app.mount("/", StaticFiles(directory=str(Path(__file__).resolve().parent.parent), html=True), name="static")
