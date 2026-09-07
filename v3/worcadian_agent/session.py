"""Shared session-cookie configuration for the OAuth-gated site.

Each api/*.py file (see api/app.py, api/home.py, api/login.py,
api/callback.py, api/logout.py) is deployed as its own separate Vercel
serverless function -- but Starlette's SessionMiddleware stores session data
in a signed cookie (via itsdangerous), not server-side memory. As long as
every function adds the middleware with the SAME SESSION_SECRET_KEY, a cookie
set by one function (e.g. the OAuth callback, which sets user_email) is fully
readable by another (e.g. the home page, which checks it) -- no shared state
between the separately deployed functions is needed.

Env vars:
    SESSION_SECRET_KEY   required -- random secret used to sign the session
                         cookie. Generate one with:
                             python -c "import secrets; print(secrets.token_urlsafe(32))"
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

SESSION_COOKIE_NAME = "worcadian_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14  # 14 days


def add_session_middleware(app: FastAPI) -> None:
    secret_key = os.getenv("SESSION_SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SESSION_SECRET_KEY is not set. Generate one with:\n"
            '    python -c "import secrets; print(secrets.token_urlsafe(32))"\n'
            "and set it as an env var."
        )
    # Vercel sets VERCEL=1 in its deployed runtime; require HTTPS-only cookies
    # there, but not for local http://localhost testing (where the cookie
    # would otherwise never be sent back).
    is_deployed = bool(os.getenv("VERCEL"))
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie=SESSION_COOKIE_NAME,
        same_site="lax",
        https_only=is_deployed,
        max_age=SESSION_MAX_AGE_SECONDS,
    )
