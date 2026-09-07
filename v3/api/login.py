"""Starts the Auth0 login flow, at its plain native address /api/login
(see api/home.py's docstring for why this doesn't use a "/auth/login"
rewrite)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worcadian_agent.login")

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

load_dotenv()

from worcadian_agent.app_setup import configure_app  # noqa: E402
from worcadian_agent.oauth import build_authorize_url, new_state  # noqa: E402

app = FastAPI()
configure_app(app, logger)


@app.get("/api/login")
def login(request: Request):
    state = new_state()
    request.session["oauth_state"] = state
    return RedirectResponse(url=build_authorize_url(state))
