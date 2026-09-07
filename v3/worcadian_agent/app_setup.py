"""Shared FastAPI setup (session cookie support + request logging) used by
each of the small per-route Vercel functions under api/."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request

from worcadian_agent.session import add_session_middleware


def configure_app(app: FastAPI, logger: logging.Logger) -> None:
    """Add session-cookie support and request logging to `app`.

    The logging middleware logs every request that actually reaches this
    app (method, path, status, duration) -- if a request doesn't show up
    here at all, it never reached the Python function (a routing/rewrite
    problem, not an app-code problem).
    """
    add_session_middleware(app)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.monotonic()
        # Deliberately log the RAW ASGI scope fields (not just request.url.path,
        # which reconstructs root_path + path and can look identical to the
        # native address even when the router is matching on a different, bare
        # "path" -- exactly the kind of mismatch that produced a same-looking
        # log line but a 404 from Starlette's own router in production once).
        logger.info(
            "request start method=%s url_path=%s scope_path=%r scope_root_path=%r scope_raw_path=%r",
            request.method,
            request.url.path,
            request.scope.get("path"),
            request.scope.get("root_path"),
            request.scope.get("raw_path"),
        )
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request raised an unhandled exception method=%s path=%s", request.method, request.url.path
            )
            raise
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "request end method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
