"""Persists the X (Twitter) OAuth 2.0 token pair in Postgres (Neon).

Vercel functions are stateless between invocations, but X's refresh token
ROTATES every time it's used -- the old one is invalidated and a brand new
one issued -- so the current pair has to live somewhere durable, not a
static env var, or the connection silently breaks the first time it's
refreshed. There's only ever one row: this app posts as a single,
pre-authorized X account, not a per-user store.

Env vars:
    DATABASE_URL   required -- a Postgres connection string, e.g. Neon's
                   postgresql://user:password@host/dbname?sslmode=require
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import psycopg2

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS x_oauth_tokens (
    id INTEGER PRIMARY KEY DEFAULT 1,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT x_oauth_tokens_single_row CHECK (id = 1)
)
"""


def _connect():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg2.connect(database_url)


def load_tokens() -> dict | None:
    """Return {"access_token", "refresh_token", "expires_at"}, or None if X
    has never been authorized (see /api/x/authorize)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_TABLE_SQL)
        cur.execute("SELECT access_token, refresh_token, expires_at FROM x_oauth_tokens WHERE id = 1")
        row = cur.fetchone()
        conn.commit()
    if row is None:
        return None
    access_token, refresh_token, expires_at = row
    return {"access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at}


def save_tokens(access_token: str, refresh_token: str, expires_at: datetime) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_TABLE_SQL)
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
