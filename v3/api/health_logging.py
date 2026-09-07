"""Control experiment #2: bare FastAPI + our custom logging middleware,
but deliberately NO SessionMiddleware. Isolates whether the logging
middleware (and its sys.path/dotenv/logging.basicConfig boilerplate) is the
problem, independent of session cookie support. See api/health.py."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("worcadian_agent.health_logging")

from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv()

app = FastAPI()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    logger.info("request start method=%s path=%s", request.method, request.url.path)
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info("request end method=%s path=%s status=%s duration_ms=%.1f", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.get("/api/health_logging")
def health_logging():
    return {"status": "ok"}
