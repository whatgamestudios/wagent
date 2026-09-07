"""Serves the OAuth-gated home page (index.html).

Deployed as its own Vercel function -- Vercel's zero-config Python convention
maps api/home.py -> /api/home deterministically; vercel.json rewrites "/"
here. It's a dedicated file rather than folded into api/app.py's existing
routes because of a gotcha discovered building this app: a rewrite's
destination collapses request.url.path to that literal destination for every
request going through it (confirmed empirically), so multiple *distinct* GET
endpoints sharing one destination need real disambiguation. A route with its
own dedicated function+destination needs none of that.
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

INDEX_HTML_PATH = Path(__file__).resolve().parent.parent / "index.html"


@app.get("/")
@app.get("/api/home")  # friendly alias for local uvicorn/vercel-dev testing
def home(request: Request):
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        logger.info("home: no valid session (email=%s); redirecting to login", email)
        return RedirectResponse(url="/auth/login")
    return HTMLResponse(INDEX_HTML_PATH.read_text())
