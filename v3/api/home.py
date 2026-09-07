"""Serves the OAuth-gated dashboard page (dashboard.html).

Deployed as its own Vercel function at its plain, native, zero-config
address: Vercel's Python convention maps api/home.py -> /api/home
deterministically, with no rewrite involved. That's deliberate -- custom
"source"/"destination" rewrites for pretty URLs (trying to serve this at "/",
or at "/auth/login" etc. for the sibling auth routes) repeatedly misbehaved
in production in ways that were never fully explained even after several
fixes, so every auth-related route in this app now uses its plain
/api/<filename> address directly instead of a rewrite. The genuinely public
landing page lives at "/" as a real static index.html (see that file) with a
"Log in" button pointing straight at /api/login; this dashboard page is only
reachable after that login flow completes.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worcadian_agent.home")

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

load_dotenv()

from worcadian_agent.app_setup import configure_app  # noqa: E402
from worcadian_agent.oauth import is_email_allowed  # noqa: E402

app = FastAPI()
configure_app(app, logger)

DASHBOARD_HTML_PATH = Path(__file__).resolve().parent.parent / "dashboard.html"


@app.get("/api/home")
def home(request: Request):
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        logger.info("home: no valid session (email=%s); redirecting to the public landing page", email)
        return RedirectResponse(url="/")
    return HTMLResponse(DASHBOARD_HTML_PATH.read_text())
