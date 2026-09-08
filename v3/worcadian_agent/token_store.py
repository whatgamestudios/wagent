"""Persists OAuth token pairs (X, Instagram) in Postgres (Neon).

Vercel functions are stateless between invocations, but X's refresh token
ROTATES every time it's used -- the old one is invalidated and a brand new
one issued -- and Instagram's long-lived token needs periodic refreshing
too. Either way the current value has to live somewhere durable, not a
static env var, or the connection silently breaks. There's only ever one
row per provider: this app posts as a single, pre-authorized account per
platform, not a per-user store.

Env vars:
    DATABASE_URL   required -- see db.py
"""

from __future__ import annotations

import logging
from datetime import datetime

from worcadian_agent.db import connect

logger = logging.getLogger(__name__)

_CREATE_X_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS x_oauth_tokens (
    id INTEGER PRIMARY KEY DEFAULT 1,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT x_oauth_tokens_single_row CHECK (id = 1)
)
"""

_CREATE_INSTAGRAM_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS instagram_oauth_tokens (
    id INTEGER PRIMARY KEY DEFAULT 1,
    access_token TEXT NOT NULL,
    ig_user_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT instagram_oauth_tokens_single_row CHECK (id = 1)
)
"""


def load_x_tokens() -> dict | None:
    """Return {"access_token", "refresh_token", "expires_at"}, or None if X
    has never been authorized (see /api/x/authorize)."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_X_TABLE_SQL)
        cur.execute("SELECT access_token, refresh_token, expires_at FROM x_oauth_tokens WHERE id = 1")
        row = cur.fetchone()
        conn.commit()
    if row is None:
        return None
    access_token, refresh_token, expires_at = row
    return {"access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at}


def save_x_tokens(access_token: str, refresh_token: str, expires_at: datetime) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_X_TABLE_SQL)
        cur.execute(
            """
            INSERT INTO x_oauth_tokens (id, access_token, refresh_token, expires_at, updated_at)
            VALUES (1, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = now()
            """,
            (access_token, refresh_token, expires_at),
        )
        conn.commit()
    logger.info("saved X OAuth2 token pair, expires_at=%s", expires_at)


def load_instagram_tokens() -> dict | None:
    """Return {"access_token", "ig_user_id", "expires_at"}, or None if
    Instagram has never been authorized (see /api/instagram/authorize)."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_INSTAGRAM_TABLE_SQL)
        cur.execute("SELECT access_token, ig_user_id, expires_at FROM instagram_oauth_tokens WHERE id = 1")
        row = cur.fetchone()
        conn.commit()
    if row is None:
        return None
    access_token, ig_user_id, expires_at = row
    return {"access_token": access_token, "ig_user_id": ig_user_id, "expires_at": expires_at}


def save_instagram_tokens(access_token: str, ig_user_id: str, expires_at: datetime) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_INSTAGRAM_TABLE_SQL)
        cur.execute(
            """
            INSERT INTO instagram_oauth_tokens (id, access_token, ig_user_id, expires_at, updated_at)
            VALUES (1, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                ig_user_id = EXCLUDED.ig_user_id,
                expires_at = EXCLUDED.expires_at,
                updated_at = now()
            """,
            (access_token, ig_user_id, expires_at),
        )
        conn.commit()
    logger.info("saved Instagram OAuth token, ig_user_id=%s expires_at=%s", ig_user_id, expires_at)
