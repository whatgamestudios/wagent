"""FastAPI app deployed as a Vercel serverless function.

Deliberately not named index.py: "index" is a special filename in Vercel's
filesystem routing (it collapses to the parent path, the same way
index.html does for static hosting), which made the rewrite destination
genuinely ambiguous between "/api" and "/api/index" and cost real debugging
time. "app.py" has no special meaning, so it can only ever route to exactly
/api/app -- see vercel.json's "rewrites" entry, which must point there.

IMPORTANT, confirmed empirically (not just from docs): Vercel's rewrite
preserves the original HTTP method and body but does NOT preserve the
original request path -- every request under /api/* arrives here with
request.url.path literally equal to "/api/app" (the rewrite's destination),
regardless of whether the browser called /api/press-release or
/api/cron/daily-tasks. Only the method still distinguishes them. That's why
every route below is registered at BOTH its real/friendly path (so direct
curl, `uvicorn`, and `vercel dev` testing all still work without going
through a rewrite) AND "/api/app" (what production traffic actually looks
like once Vercel's rewrite has run) -- do not remove the "/api/app"
decorator thinking it's a leftover duplicate.

Routes (see vercel.json for how /api/* is rewritten to this file):
    POST /api/press-release     build a press release on demand (used by the
                                 site's "Execute Daily Tasks" button); requires
                                 an OAuth session (see worcadian_agent/oauth.py)
    GET  /api/cron/daily-tasks  the scheduled daily_tasks job Vercel Cron hits;
                                 protected by CRON_SECRET, not OAuth, since it's
                                 machine-triggered

The OAuth-gated home page itself (GET /) lives in api/home.py, not here --
see that file's docstring for why each concern gets its own dedicated
function file rather than being folded into this one.

Logging: configured (via app_setup.configure_app) so every logger.info()/
logger.exception() call in this module and in worcadian_agent.* reaches
stderr, which Vercel captures as Function Logs. A request-logging middleware
logs every request that actually reaches this app (method, path, status,
duration) -- if a request doesn't show up there at all, it never reached the
Python function (a routing/rewrite problem, not an app-code problem).
"""

from __future__ import annotations

import base64
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("worcadian_agent.api")

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

load_dotenv()

from worcadian_agent.agent import build_press_release, gather_facts  # noqa: E402
from worcadian_agent.app_setup import configure_app  # noqa: E402
from worcadian_agent.daily_tasks import daily_tasks  # noqa: E402
from worcadian_agent.dictionary_client import lookup_words  # noqa: E402
from worcadian_agent.image_card import generate_word_card_bytes  # noqa: E402
from worcadian_agent.oauth import is_email_allowed  # noqa: E402

app = FastAPI()
configure_app(app, logger)

OUTPUT_DIR = "/tmp/output"


def _build_word_card_data_url(definitions: dict[str, dict]) -> str | None:
    """Render a word card for the last word in `definitions` (in lookup order) and
    return it as a data: URI ready for an <img src>, or None if there's nothing to render."""
    if not definitions:
        return None
    word = next(reversed(definitions))
    entry = definitions[word]
    meaning = entry.get("definition") or entry.get("short_definition")
    if not meaning:
        return None
    try:
        png_bytes = generate_word_card_bytes(word, meaning, part_of_speech=entry.get("part_of_speech"))
    except Exception:
        logger.exception("word card generation failed word=%s", word)
        return None
    return f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"


# TEMPORARY: the "Execute Daily Tasks" button skips the LLM press-release
# generation step (gather_facts/dictionary lookups/word card still run) while
# that's being worked on separately. Set back to False to re-enable it.
SKIP_PRESS_RELEASE_ON_BUTTON = True


class PressReleaseRequest(BaseModel):
    day: int | None = None


@app.post("/api/press-release")
@app.post("/api/app")  # see module docstring: production traffic arrives at this path, not the one above
def generate_press_release(payload: PressReleaseRequest, request: Request) -> dict:
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        logger.warning("press-release rejected: no valid OAuth session")
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    logger.info("press-release requested day=%s by=%s", payload.day, email)
    try:
        facts_bundle = gather_facts(payload.day)
        words_to_look_up = [facts_bundle["seed_word"]] + [w["word"] for w in facts_bundle["notable_words"]]
        definitions = lookup_words(words_to_look_up)
        card_image = _build_word_card_data_url(definitions)
        if SKIP_PRESS_RELEASE_ON_BUTTON:
            logger.info("press-release generation temporarily disabled; skipping build_press_release")
            text = "(press release generation is temporarily disabled)"
        else:
            path = build_press_release(facts_bundle, output_dir=OUTPUT_DIR)
            text = Path(path).read_text()
    except Exception as exc:
        logger.exception("press-release generation failed day=%s", payload.day)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("press-release step done game_day=%s", facts_bundle["game_day"])
    return {
        "game_day": facts_bundle["game_day"],
        "text": text,
        "definitions": definitions,
        "card_image": card_image,
    }


@app.get("/api/cron/daily-tasks")
@app.get("/api/app")  # see module docstring: production traffic arrives at this path, not the one above
def run_daily_tasks(authorization: str | None = Header(default=None)) -> dict:
    logger.info("daily-tasks cron invoked")
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret and authorization != f"Bearer {cron_secret}":
        logger.warning("daily-tasks rejected: missing or invalid CRON_SECRET bearer token")
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        result = daily_tasks()
    except Exception as exc:
        logger.exception("daily-tasks failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("daily-tasks completed result=%s", result)
    return {"status": "ok", **result}
