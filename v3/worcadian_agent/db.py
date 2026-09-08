"""Shared Postgres connection helper (Neon), used by token_store.py and
image_store.py.

Env vars:
    DATABASE_URL   required -- a Postgres connection string, e.g. Neon's
                   postgresql://user:password@host/dbname?sslmode=require
"""

from __future__ import annotations

import os

import psycopg2


def connect():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg2.connect(database_url)
