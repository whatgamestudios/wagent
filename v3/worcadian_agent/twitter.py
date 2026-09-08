"""Post a tweet to X (Twitter) via the v2 API.

This posts as a single, pre-authorized X account -- not a per-user login
flow. X's tweet-creation endpoint (POST /2/tweets) requires user-context
auth; the simplest way to get that for one fixed account (rather than
building a full "login with X" OAuth dance for every visitor) is OAuth 1.0a
signed with that account's own permanent Access Token, which the X Developer
Portal issues directly without further interaction.

Setup (in the X Developer Portal, developer.x.com):
    1. Create a Project and App with **Read and Write** permissions
       (User authentication settings -> App permissions).
    2. Under "Keys and tokens", generate both the Consumer Keys (API Key /
       API Key Secret) and, for the account that should post, an Access
       Token & Secret.

Env vars:
    X_API_KEY               required -- the App's Consumer Key (API Key)
    X_API_SECRET            required -- the App's Consumer Secret (API Key Secret)
    X_ACCESS_TOKEN          required -- the posting account's Access Token
    X_ACCESS_TOKEN_SECRET   required -- the posting account's Access Token Secret
"""

from __future__ import annotations

import logging
import os

import requests
from requests_oauthlib import OAuth1

logger = logging.getLogger(__name__)

TWEET_URL = "https://api.x.com/2/tweets"


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set.")
    return value


def _auth() -> OAuth1:
    return OAuth1(
        _required_env("X_API_KEY"),
        _required_env("X_API_SECRET"),
        _required_env("X_ACCESS_TOKEN"),
        _required_env("X_ACCESS_TOKEN_SECRET"),
    )


def post_tweet(text: str) -> dict:
    """Post `text` as a tweet. Returns the created tweet's data ({"id", "text"}, per X's API)."""
    logger.info("posting tweet (%d chars)", len(text))
    resp = requests.post(TWEET_URL, auth=_auth(), json={"text": text}, timeout=15)
    if not resp.ok:
        logger.error("tweet post failed status=%s body=%s", resp.status_code, resp.text[:500])
        raise RuntimeError(f"X API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json().get("data", {})
    logger.info("tweet posted id=%s", data.get("id"))
    return data
