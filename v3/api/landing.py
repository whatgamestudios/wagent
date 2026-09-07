"""Serves the public landing page (index.html) -- no login required.

Deployed as its own Vercel function at /api/landing; vercel.json rewrites
"/" here with a plain, exact (non-wildcard) rewrite -- the same kind already
proven to work for /api/press-release and /api/cron/daily-tasks. This exists
because relying on Vercel serving the root-level index.html as a plain
static file (no function involved at all) stopped working once this project
had multiple api/*.py functions and a non-trivial vercel.json -- worth
revisiting if that ever gets root-caused, but this sidesteps it by using the
same function+rewrite mechanism that's reliable everywhere else in this app.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worcadian_agent.landing")

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

load_dotenv()

from worcadian_agent.app_setup import configure_app  # noqa: E402

app = FastAPI()
configure_app(app, logger)

INDEX_HTML_PATH = Path(__file__).resolve().parent.parent / "index.html"


# Registered at both the function's native address AND "/": if Vercel's ASGI
# adapter sets scope["root_path"] to this function's own address and leaves
# scope["path"] as "" or "/" (Starlette's router matches on the bare "path",
# while request.url.path -- what our own logging prints -- reconstructs
# root_path + path, which would print "/api/landing" either way and mask the
# mismatch), only the "/" registration would actually match. Covering both
# costs nothing and removes the guesswork.
@app.get("/api/landing")
@app.get("/")
def landing():
    return HTMLResponse(INDEX_HTML_PATH.read_text())
