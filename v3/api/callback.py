"""Handles Auth0's OAuth redirect back. vercel.json rewrites /auth/callback here.

See api/home.py's docstring for why this is its own dedicated function file.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worcadian_agent.callback")

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

load_dotenv()

from worcadian_agent.app_setup import configure_app  # noqa: E402
from worcadian_agent.oauth import exchange_code_for_email, is_email_allowed  # noqa: E402

app = FastAPI()
configure_app(app, logger)


@app.get("/auth/callback")
@app.get("/api/callback")  # friendly alias for local uvicorn/vercel-dev testing
def callback(request: Request):
    error = request.query_params.get("error")
    if error:
        logger.warning("oauth callback error=%s", error)
        return HTMLResponse(f"<p>Login failed: {error}</p>", status_code=400)

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    expected_state = request.session.pop("oauth_state", None)
    if not code or not state or not expected_state or state != expected_state:
        logger.warning("oauth callback: missing or mismatched state (possible CSRF or expired attempt)")
        return HTMLResponse("<p>Login failed: invalid or expired login attempt. Please try again.</p>", status_code=400)

    try:
        email = exchange_code_for_email(code)
    except Exception:
        logger.exception("oauth callback: token exchange failed")
        return HTMLResponse("<p>Login failed.</p>", status_code=400)

    if not is_email_allowed(email):
        logger.warning("oauth callback: email=%s is not in ALLOWED_EMAILS", email)
        return HTMLResponse("<p>Access denied: this account is not authorized to use this app.</p>", status_code=403)

    request.session["user_email"] = email
    logger.info("oauth callback: login succeeded email=%s", email)
    return RedirectResponse(url="/")
