"""Control experiment #3: bare FastAPI + Starlette's SessionMiddleware,
but deliberately NO custom logging middleware. Isolates whether
SessionMiddleware itself (added via worcadian_agent.session) is the
problem, independent of our own logging middleware. See api/health.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from worcadian_agent.session import add_session_middleware  # noqa: E402

app = FastAPI()
add_session_middleware(app)


@app.get("/api/health_session")
def health_session():
    return {"status": "ok"}
