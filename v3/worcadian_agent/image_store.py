"""Temporarily hosts generated images in Postgres (Neon) so external services
that require a fetchable URL -- Instagram's API, notably, which needs a
public image_url and won't accept raw bytes -- can retrieve them.

Images are keyed by a random UUID (not sequential, to avoid enumeration) and
served back unauthenticated at GET /api/images/{id} (see api/app.py) --
that endpoint has to be public since Instagram's own servers fetch it
directly, with no way to send our session cookie.

Env vars:
    DATABASE_URL   required -- see db.py
"""

from __future__ import annotations

import logging
import uuid

import psycopg2

from worcadian_agent.db import connect

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS hosted_images (
    id UUID PRIMARY KEY,
    content BYTEA NOT NULL,
    content_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def save_image(content: bytes, content_type: str = "image/png") -> str:
    """Store `content` and return its new id (a UUID string)."""
    image_id = str(uuid.uuid4())
    with connect() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_TABLE_SQL)
        cur.execute(
            "INSERT INTO hosted_images (id, content, content_type) VALUES (%s, %s, %s)",
            (image_id, psycopg2.Binary(content), content_type),
        )
        conn.commit()
    logger.info("hosted image id=%s bytes=%d", image_id, len(content))
    return image_id


def load_image(image_id: str) -> tuple[bytes, str] | None:
    """Return (content, content_type) for `image_id`, or None if not found."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_TABLE_SQL)
        cur.execute("SELECT content, content_type FROM hosted_images WHERE id = %s", (image_id,))
        row = cur.fetchone()
        conn.commit()
    if row is None:
        return None
    content, content_type = row
    return bytes(content), content_type
