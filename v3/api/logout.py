"""Clears the session and ends the Auth0-side SSO session too, at its plain
native address /api/logout (see api/home.py's docstring for why this doesn't
use a "/auth/logout" rewrite)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worcadian_agent.logout")

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

load_dotenv()

from worcadian_agent.app_setup import configure_app  # noqa: E402
from worcadian_agent.oauth import build_logout_url  # noqa: E402

app = FastAPI()
configure_app(app, logger)


@app.get("/api/logout")
def logout(request: Request):
    email = request.session.get("user_email")
    request.session.clear()
    logger.info("logout: cleared local session for email=%s; redirecting to Auth0 logout", email)
    return RedirectResponse(url=build_logout_url())
