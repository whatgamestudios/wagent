"""Serves the public landing page (index.html) -- no login required.

Deployed as its own Vercel function at /api/welcome; vercel.json rewrites
"/" here with a plain, exact (non-wildcard) rewrite -- the same kind already
proven to work for /api/press-release and /api/cron/daily-tasks.

Renamed from landing.py: hitting /api/landing directly (bypassing the "/"
rewrite entirely) still 404'd with the exact same logged scope_path, ruling
out a routing/rewrite problem -- so this tests whether "landing" was itself
somehow a reserved/special name to Vercel, the same way "index" turned out to
be earlier in this project. Also added /api/welcome/ping, a route with no
dependencies at all (no file read, nothing), to isolate whether *any* route
in this function works, versus something specific to the original one.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worcadian_agent.welcome")

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse

load_dotenv()

from worcadian_agent.app_setup import configure_app  # noqa: E402

app = FastAPI()
configure_app(app, logger)

INDEX_HTML_PATH = Path(__file__).resolve().parent.parent / "index.html"


@app.get("/api/welcome/ping")
def ping():
    return PlainTextResponse("pong")


@app.get("/api/welcome")
@app.get("/")
def welcome():
    return HTMLResponse(INDEX_HTML_PATH.read_text())
