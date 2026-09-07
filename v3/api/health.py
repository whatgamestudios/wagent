"""Absolute-minimal control experiment: no session middleware, no custom
logging middleware, no dotenv, no sys.path manipulation -- just bare FastAPI.

Purpose: every other new function added to this app (landing/welcome, home,
login, callback, logout) has 404'd on every route in production despite
locally-verified-correct code and scope data, while the original api/app.py
was last confirmed working before OAuth/session middleware was added to it.
This isolates whether that shared setup code is the common thread, or
whether *any* newly added function file has this problem regardless of what
it contains.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI()


@app.get("/api/health")
def health():
    return {"status": "ok"}
