"""Post a tweet to X (Twitter) via the v2 API, OAuth 2.0 Authorization Code
flow with PKCE.

Unlike OAuth 1.0a (this project's earlier approach), X does not offer a
static, permanent user-context credential under OAuth 2.0 -- posting
requires a one-time browser authorization producing a short-lived access
token (~2 hours) kept alive by a refresh token. That refresh token ROTATES
on every use -- X invalidates the old one and issues a brand new one each
time -- so the current pair is persisted in Postgres (see token_store.py)
rather than a static env var, and refreshed automatically here whenever it's
close to expiring.

One-time setup (as an allowlisted, logged-in user): visit /api/x/authorize
(see api/app.py), approve access on X, and the resulting token pair is
stored automatically. This only needs to be redone if the refresh token is
ever revoked, or expires from prolonged (~6 months) disuse.

Env vars:
    X_API_KEY        required -- the X App's OAuth 2.0 Client ID
    X_API_SECRET     required -- the X App's OAuth 2.0 Client Secret
    PUBLIC_BASE_URL  required -- reused from oauth.py; PUBLIC_BASE_URL +
                     /api/x/callback must be registered as a Callback URI on
                     the X App (User authentication settings)
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from worcadian_agent import token_store

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
TWEET_URL = "https://api.x.com/2/tweets"
CALLBACK_PATH = "/api/x/callback"
SCOPES = "tweet.read tweet.write users.read offline.access"

# Refresh this many seconds before actual expiry, to comfortably outrun
# clock skew and request latency rather than cutting it exactly at the wire.
EXPIRY_SAFETY_MARGIN_SECONDS = 120


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set.")
    return value


def _redirect_uri() -> str:
    base = _required_env("PUBLIC_BASE_URL").rstrip("/")
    return f"{base}{CALLBACK_PATH}"


def new_state() -> str:
    """A random, unguessable token to protect the OAuth flow against CSRF."""
    return secrets.token_urlsafe(24)


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for the S256 PKCE method."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def build_authorize_url(state: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": _required_env("X_API_KEY"),
        "redirect_uri": _redirect_uri(),
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _token_request(data: dict) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data=data,
        auth=(_required_env("X_API_KEY"), _required_env("X_API_SECRET")),
        timeout=15,
    )
    if not resp.ok:
        logger.error("X OAuth2 token request failed status=%s body=%s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"X OAuth2 token request failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()


def _save_token_payload(payload: dict) -> str:
    access_token = payload["access_token"]
    refresh_token = payload["refresh_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload["expires_in"])
    token_store.save_tokens(access_token, refresh_token, expires_at)
    return access_token


def exchange_code_for_tokens(code: str, code_verifier: str) -> None:
    """Exchange an authorization `code` for an access/refresh token pair and persist it."""
    payload = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
            "code_verifier": code_verifier,
        }
    )
    _save_token_payload(payload)
    logger.info("X OAuth2: initial authorization succeeded")


def refresh_access_token(refresh_token: str) -> str:
    """Exchange `refresh_token` for a fresh access token, persisting the (rotated)
    result. Public because it doubles as the one-time seeding operation for an
    access/refresh token pair generated directly in console.x.com, rather than
    through the /api/x/authorize browser flow -- see scripts/seed_x_tokens.py."""
    logger.info("X OAuth2: refreshing access token")
    payload = _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
    return _save_token_payload(payload)


def _get_valid_access_token() -> str:
    tokens = token_store.load_tokens()
    if tokens is None:
        raise RuntimeError(
            "X is not connected yet. Visit /api/x/authorize (while logged in) to authorize this app once."
        )
    if datetime.now(timezone.utc) >= tokens["expires_at"] - timedelta(seconds=EXPIRY_SAFETY_MARGIN_SECONDS):
        return refresh_access_token(tokens["refresh_token"])
    return tokens["access_token"]


def _post(access_token: str, text: str) -> requests.Response:
    return requests.post(
        TWEET_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        json={"text": text},
        timeout=15,
    )


def post_tweet(text: str) -> dict:
    """Post `text` as a tweet. Returns the created tweet's data ({"id", "text"}, per X's API)."""
    access_token = _get_valid_access_token()
    logger.info("posting tweet (%d chars)", len(text))
    resp = _post(access_token, text)

    if resp.status_code == 401:
        # Our stored expiry bookkeeping might have drifted from reality (e.g.
        # the token was revoked, or clock skew) -- force one refresh and
        # retry before giving up.
        logger.warning("tweet post got 401 with a token believed valid; forcing a refresh and retrying once")
        tokens = token_store.load_tokens()
        if tokens is None:
            raise RuntimeError("X is not connected. Visit /api/x/authorize (while logged in) to authorize this app.")
        access_token = refresh_access_token(tokens["refresh_token"])
        resp = _post(access_token, text)

    if not resp.ok:
        logger.error("tweet post failed status=%s body=%s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"X API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json().get("data", {})
    logger.info("tweet posted id=%s", data.get("id"))
    return data
