"""Post an image to Instagram via "Instagram API with Instagram Login" --
Meta's standalone product that authenticates directly against an Instagram
professional (Business/Creator) account, with no Facebook Page required.

Flow:
    1. build_authorize_url(state) -- send the browser here to log in
    2. Instagram redirects back to PUBLIC_BASE_URL + "/api/instagram/callback"
       with ?code=...&state=...
    3. exchange_code_for_tokens(code) -- trades the code for a short-lived
       token, then immediately exchanges that for a long-lived token
       (~60 days) and persists it (see token_store.py)
    4. post_image(image_url, caption) -- creates a media container from a
       PUBLIC image URL (Instagram's API fetches it directly; it does not
       accept uploaded bytes), polls it until Instagram has finished
       fetching/processing the image (even single-image containers aren't
       necessarily publishable instantly), then publishes it -- refreshing
       the long-lived token first if it's getting close to expiry

Unlike X's OAuth2 refresh token (which rotates and is invalidated on every
use), Instagram's long-lived token is refreshed "in place": the same token
string gets a new ~60-day expiry each time, valid any time after it's 24h
old and not yet expired. No separate refresh token to track.

One-time setup (as an allowlisted, logged-in user): visit
/api/instagram/authorize (see api/app.py), approve access, and the resulting
token is stored automatically. Redo only if access is revoked, or the token
expires from ~60 days of disuse without a refresh.

Env vars:
    INSTAGRAM_APP_ID      required -- the Meta App's Instagram App ID
    INSTAGRAM_APP_SECRET  required -- the Meta App's Instagram App Secret
    PUBLIC_BASE_URL       required -- reused from oauth.py; PUBLIC_BASE_URL +
                          /api/instagram/callback must be registered as a
                          valid OAuth redirect URI on the Instagram App
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from worcadian_agent import token_store

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
SHORT_LIVED_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
LONG_LIVED_EXCHANGE_URL = "https://graph.instagram.com/access_token"
REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
GRAPH_API_VERSION = "v21.0"  # bump periodically as Meta deprecates old versions
GRAPH_BASE = f"https://graph.instagram.com/{GRAPH_API_VERSION}"
CALLBACK_PATH = "/api/instagram/callback"
SCOPES = "instagram_business_basic,instagram_business_content_publish"

# Refresh the long-lived token once it's within this many days of expiry --
# Instagram allows refreshing any time after the token is 24h old and before
# it expires, so this leaves a comfortable margin either side.
REFRESH_WHEN_DAYS_REMAINING = 7

# Even a single *image* container (not just video) isn't necessarily
# publishable the instant it's created -- Instagram fetches and processes
# the image from image_url asynchronously, and media_publish fails with
# "Media ID is not available" (error_subcode 2207027) if called too soon.
# Poll the container's status_code until it's FINISHED, rather than assuming
# it's ready right away.
MEDIA_READY_POLL_INTERVAL_SECONDS = 1.5
MEDIA_READY_MAX_ATTEMPTS = 20


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


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": _required_env("INSTAGRAM_APP_ID"),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _save(access_token: str, ig_user_id: str, expires_in_seconds: int) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
    token_store.save_instagram_tokens(access_token, ig_user_id, expires_at)


def exchange_code_for_tokens(code: str) -> None:
    """Exchange an authorization `code` for a short-lived token, immediately
    upgrade that to a long-lived one, and persist it."""
    logger.info("Instagram OAuth: exchanging authorization code for a short-lived token")
    resp = requests.post(
        SHORT_LIVED_TOKEN_URL,
        data={
            "client_id": _required_env("INSTAGRAM_APP_ID"),
            "client_secret": _required_env("INSTAGRAM_APP_SECRET"),
            "grant_type": "authorization_code",
            "redirect_uri": _redirect_uri(),
            "code": code,
        },
        timeout=15,
    )
    if not resp.ok:
        logger.error("Instagram token exchange failed status=%s body=%s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"Instagram token exchange failed: {resp.status_code} {resp.text[:300]}")
    short_lived = resp.json()
    ig_user_id = str(short_lived["user_id"])

    logger.info("Instagram OAuth: exchanging for a long-lived token")
    long_resp = requests.get(
        LONG_LIVED_EXCHANGE_URL,
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": _required_env("INSTAGRAM_APP_SECRET"),
            "access_token": short_lived["access_token"],
        },
        timeout=15,
    )
    if not long_resp.ok:
        logger.error(
            "Instagram long-lived token exchange failed status=%s body=%s",
            long_resp.status_code, long_resp.text[:500],
        )
        raise RuntimeError(f"Instagram long-lived token exchange failed: {long_resp.status_code} {long_resp.text[:300]}")
    long_lived = long_resp.json()
    _save(long_lived["access_token"], ig_user_id, long_lived["expires_in"])
    logger.info("Instagram OAuth: initial authorization succeeded ig_user_id=%s", ig_user_id)


def _refresh_if_needed(tokens: dict) -> dict:
    remaining = tokens["expires_at"] - datetime.now(timezone.utc)
    if remaining > timedelta(days=REFRESH_WHEN_DAYS_REMAINING):
        return tokens

    logger.info("Instagram OAuth: refreshing long-lived token (%s remaining)", remaining)
    resp = requests.get(
        REFRESH_URL,
        params={"grant_type": "ig_refresh_token", "access_token": tokens["access_token"]},
        timeout=15,
    )
    if not resp.ok:
        # Non-fatal: the existing token may still work until it actually
        # expires, so don't block posting on a failed refresh attempt.
        logger.error("Instagram token refresh failed status=%s body=%s", resp.status_code, resp.text[:500])
        return tokens
    data = resp.json()
    _save(data["access_token"], tokens["ig_user_id"], data["expires_in"])
    return token_store.load_instagram_tokens()


def _wait_until_media_ready(creation_id: str, access_token: str) -> None:
    """Poll the media container's status_code until Instagram has finished
    fetching/processing the image from image_url, raising if it errors out
    or doesn't become ready within MEDIA_READY_MAX_ATTEMPTS."""
    for attempt in range(1, MEDIA_READY_MAX_ATTEMPTS + 1):
        resp = requests.get(
            f"{GRAPH_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=15,
        )
        if resp.ok:
            status_code = resp.json().get("status_code")
            logger.info("Instagram media container %s status=%s (attempt %d/%d)", creation_id, status_code, attempt, MEDIA_READY_MAX_ATTEMPTS)
            if status_code == "FINISHED":
                return
            if status_code == "ERROR":
                raise RuntimeError(f"Instagram failed to process the image (creation_id={creation_id}).")
        else:
            logger.warning(
                "Instagram media status check failed status=%s body=%s (attempt %d/%d)",
                resp.status_code, resp.text[:300], attempt, MEDIA_READY_MAX_ATTEMPTS,
            )
        if attempt < MEDIA_READY_MAX_ATTEMPTS:
            time.sleep(MEDIA_READY_POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"Instagram media container {creation_id} did not become ready in time.")


def post_image(image_url: str, caption: str = "") -> dict:
    """Publish `image_url` (must be a public, fetchable HTTPS URL) to Instagram.
    Returns the created post's data ({"id": ...})."""
    tokens = token_store.load_instagram_tokens()
    if tokens is None:
        raise RuntimeError(
            "Instagram is not connected yet. Visit /api/instagram/authorize (while logged in) to authorize this app once."
        )
    tokens = _refresh_if_needed(tokens)
    access_token = tokens["access_token"]
    ig_user_id = tokens["ig_user_id"]

    logger.info("creating Instagram media container image_url=%s", image_url)
    create_resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": access_token},
        timeout=30,
    )
    if not create_resp.ok:
        logger.error("Instagram media creation failed status=%s body=%s", create_resp.status_code, create_resp.text[:500])
        raise RuntimeError(f"Instagram API error {create_resp.status_code}: {create_resp.text[:300]}")
    creation_id = create_resp.json()["id"]

    _wait_until_media_ready(creation_id, access_token)

    logger.info("publishing Instagram media creation_id=%s", creation_id)
    publish_resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=30,
    )
    if not publish_resp.ok:
        logger.error("Instagram media publish failed status=%s body=%s", publish_resp.status_code, publish_resp.text[:500])
        raise RuntimeError(f"Instagram API error {publish_resp.status_code}: {publish_resp.text[:300]}")
    result = publish_resp.json()
    logger.info("Instagram post published id=%s", result.get("id"))
    return result
