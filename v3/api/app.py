"""The entire FastAPI app, deployed as ONE Vercel serverless function.

Root-caused after a long detour: Vercel's dashboard confirmed this project's
deployment builds exactly ONE serverless function ("/fastapi"), regardless of
how many api/*.py files existed. Vercel had detected "FastAPI" as the
project's framework and builds the whole thing as a single consolidated app
-- it does NOT give each api/*.py file its own separate function the way
plain zero-config Python projects do. Every previous attempt to split
concerns (login/callback/logout/home/landing) into separate files was
silently never actually deployed as anything; all traffic was always being
handled by whichever single file Vercel picked to build as "the" app (this
one -- api/app.py happened to be it), with that file's own router 404ing on
paths it didn't define.

The fix: put EVERY route for the whole site in this one file, using plain,
standard FastAPI paths. No rewrite gymnastics needed -- FastAPI's own router
correctly dispatches on the real, undisturbed request path once there's
only one app and it actually owns every route.

Routes:
    GET  /                      public landing page (index.html), no login needed
    GET  /auth/login            starts the Auth0 login flow
    GET  /auth/callback         Auth0 redirects back here with the auth code
    GET  /auth/logout           clears the session + Auth0 logout
    GET  /dashboard             the OAuth-gated dashboard (dashboard.html)
    POST /api/press-release     build a press release on demand; requires a session
    POST /api/word-card         render a word card for one word on demand; requires a session
    POST /api/tweet             post a tweet to X via its API; requires a session
    GET  /api/x/authorize       one-time: starts X's OAuth2 authorization flow; requires a session
    GET  /api/x/callback        X redirects back here with the auth code; requires a session
    POST /api/instagram-post    post the current word card image to Instagram; requires a session
    GET  /api/instagram/authorize  one-time: starts Instagram's OAuth flow; requires a session
    GET  /api/instagram/callback   Instagram redirects back here; requires a session
    GET  /api/instagram/webhook    Meta's webhook verification handshake; PUBLIC,
                                 no session -- required to save a Webhooks
                                 config in the Meta console, even though this
                                 app doesn't act on any events
    POST /api/instagram/webhook    acknowledges webhook event deliveries (ignored); PUBLIC
    GET  /api/images/{image_id}    serves a temporarily-hosted image; PUBLIC,
                                 no session -- Instagram's own servers fetch it
    GET  /api/cron/daily-tasks  the scheduled daily_tasks job; protected by
                                 CRON_SECRET (not OAuth -- it's machine-triggered)

Logging: configured (via app_setup.configure_app) so every logger.info()/
logger.exception() call in this module and in worcadian_agent.* reaches
stderr, which Vercel captures as Function Logs.
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
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel

load_dotenv()

from worcadian_agent.agent import build_press_release, gather_facts  # noqa: E402
from worcadian_agent.app_setup import configure_app  # noqa: E402
from worcadian_agent.daily_tasks import daily_tasks  # noqa: E402
from worcadian_agent.dictionary_client import lookup_words  # noqa: E402
from worcadian_agent.image_card import generate_word_card_bytes  # noqa: E402
from worcadian_agent.image_store import load_image, save_image  # noqa: E402
from worcadian_agent.instagram import (  # noqa: E402
    build_authorize_url as build_instagram_authorize_url,
    exchange_code_for_tokens as exchange_instagram_code_for_tokens,
    new_state as new_instagram_state,
    post_image as post_instagram_image,
)
from worcadian_agent.oauth import (  # noqa: E402
    build_authorize_url,
    build_logout_url,
    exchange_code_for_email,
    is_email_allowed,
    new_state,
)
from worcadian_agent.twitter import (  # noqa: E402
    build_authorize_url as build_x_authorize_url,
    exchange_code_for_tokens as exchange_x_code_for_tokens,
    generate_pkce_pair,
    new_state as new_x_state,
    post_tweet,
)

app = FastAPI()
configure_app(app, logger)

OUTPUT_DIR = "/tmp/output"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML_PATH = PROJECT_ROOT / "index.html"
DASHBOARD_HTML_PATH = PROJECT_ROOT / "dashboard.html"


# --- Public landing page ---------------------------------------------------


@app.get("/")
def landing():
    return HTMLResponse(INDEX_HTML_PATH.read_text())


# --- Auth0 login / callback / logout ---------------------------------------


@app.get("/auth/login")
def login(request: Request):
    state = new_state()
    request.session["oauth_state"] = state
    return RedirectResponse(url=build_authorize_url(state))


@app.get("/auth/callback")
def callback(request: Request):
    error = request.query_params.get("error")
    if error:
        logger.warning("oauth callback error=%s", error)
        return HTMLResponse(f"<p>Login failed: {error}</p>", status_code=400)

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    expected_state = request.session.pop("oauth_state", None)
    if not code or not state or not expected_state or state != expected_state:
        logger.warning("oauth callback: missing or mismatched state (possible CSRF or expired attempt)")
        return HTMLResponse("<p>Login failed: invalid or expired login attempt. Please try again.</p>", status_code=400)

    try:
        email = exchange_code_for_email(code)
    except Exception:
        logger.exception("oauth callback: token exchange failed")
        return HTMLResponse("<p>Login failed.</p>", status_code=400)

    if not is_email_allowed(email):
        logger.warning("oauth callback: email=%s is not in ALLOWED_EMAILS", email)
        return HTMLResponse("<p>Access denied: this account is not authorized to use this app.</p>", status_code=403)

    request.session["user_email"] = email
    logger.info("oauth callback: login succeeded email=%s", email)
    return RedirectResponse(url="/dashboard")


@app.get("/auth/logout")
def logout(request: Request):
    email = request.session.get("user_email")
    request.session.clear()
    logger.info("logout: cleared local session for email=%s; redirecting to Auth0 logout", email)
    return RedirectResponse(url=build_logout_url())


# --- OAuth-gated dashboard ---------------------------------------------------


@app.get("/dashboard")
def dashboard(request: Request):
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        logger.info("dashboard: no valid session (email=%s); redirecting to the public landing page", email)
        return RedirectResponse(url="/")
    return HTMLResponse(DASHBOARD_HTML_PATH.read_text())


# --- Press release (button) + daily_tasks (cron) ----------------------------


# TEMPORARY: the "Execute Daily Tasks" button skips the LLM press-release
# generation step (gather_facts/dictionary lookups/word card still run) while
# that's being worked on separately. Set back to False to re-enable it.
SKIP_PRESS_RELEASE_ON_BUTTON = True


class PressReleaseRequest(BaseModel):
    day: int | None = None


@app.post("/api/press-release")
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
        "seed_word": facts_bundle["seed_word"],
        "text": text,
        "definitions": definitions,
    }


class WordCardRequest(BaseModel):
    word: str
    part_of_speech: str | None = None
    definition: str | None = None
    palette: str | None = None


@app.post("/api/word-card")
def generate_word_card_endpoint(payload: WordCardRequest, request: Request) -> dict:
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        logger.warning("word-card rejected: no valid OAuth session")
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    if not payload.definition:
        raise HTTPException(status_code=400, detail="No definition available for this word.")

    logger.info("word-card requested word=%s palette=%s by=%s", payload.word, payload.palette, email)
    try:
        png_bytes = generate_word_card_bytes(
            payload.word, payload.definition, part_of_speech=payload.part_of_speech, palette=payload.palette
        )
    except Exception as exc:
        logger.exception("word card generation failed word=%s", payload.word)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    data_url = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
    return {"card_image": data_url}


class TweetRequest(BaseModel):
    text: str


@app.post("/api/tweet")
def submit_tweet(payload: TweetRequest, request: Request) -> dict:
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        logger.warning("tweet rejected: no valid OAuth session")
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Tweet text is empty.")

    logger.info("tweet submit requested by=%s length=%d", email, len(text))
    try:
        tweet = post_tweet(text)
    except Exception as exc:
        logger.exception("tweet submission failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("tweet posted id=%s", tweet.get("id"))
    return {"status": "ok", "tweet": tweet}


@app.get("/api/x/authorize")
def x_authorize(request: Request):
    """One-time setup: start X's OAuth2 flow to connect the posting account.
    See worcadian_agent/twitter.py's module docstring."""
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    state = new_x_state()
    code_verifier, code_challenge = generate_pkce_pair()
    request.session["x_oauth_state"] = state
    request.session["x_oauth_code_verifier"] = code_verifier
    logger.info("x-authorize started by=%s", email)
    return RedirectResponse(url=build_x_authorize_url(state, code_challenge))


@app.get("/api/x/callback")
def x_callback(request: Request):
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    error = request.query_params.get("error")
    if error:
        logger.warning("x-callback error=%s", error)
        return HTMLResponse(f"<p>X authorization failed: {error}</p>", status_code=400)

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    expected_state = request.session.pop("x_oauth_state", None)
    code_verifier = request.session.pop("x_oauth_code_verifier", None)
    if not code or not state or not expected_state or state != expected_state or not code_verifier:
        logger.warning("x-callback: missing or mismatched state (possible CSRF or expired attempt)")
        return HTMLResponse(
            "<p>X authorization failed: invalid or expired attempt. Please try again.</p>", status_code=400
        )

    try:
        exchange_x_code_for_tokens(code, code_verifier)
    except Exception:
        logger.exception("x-callback: token exchange failed")
        return HTMLResponse("<p>X authorization failed during token exchange.</p>", status_code=400)

    logger.info("x-callback: authorization succeeded by=%s", email)
    return HTMLResponse("<p>X account connected. You can close this tab and return to the dashboard.</p>")


class InstagramPostRequest(BaseModel):
    image_data_url: str
    caption: str = ""


@app.post("/api/instagram-post")
def submit_instagram_post(payload: InstagramPostRequest, request: Request) -> dict:
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        logger.warning("instagram-post rejected: no valid OAuth session")
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    try:
        _, encoded = payload.image_data_url.split(",", 1)
        image_bytes = base64.b64decode(encoded)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image data.")

    logger.info("instagram-post requested by=%s caption_len=%d", email, len(payload.caption))
    try:
        image_id = save_image(image_bytes, "image/png")
        base_url = os.environ["PUBLIC_BASE_URL"].rstrip("/")
        image_url = f"{base_url}/api/images/{image_id}"
        post = post_instagram_image(image_url, payload.caption)
    except Exception as exc:
        logger.exception("instagram post failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("instagram post published id=%s", post.get("id"))
    return {"status": "ok", "post": post}


@app.get("/api/instagram/authorize")
def instagram_authorize(request: Request):
    """One-time setup: start Instagram's OAuth flow to connect the posting account.
    See worcadian_agent/instagram.py's module docstring."""
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    state = new_instagram_state()
    request.session["instagram_oauth_state"] = state
    authorize_url = build_instagram_authorize_url(state)
    logger.info("instagram-authorize started by=%s url=%s", email, authorize_url)
    return RedirectResponse(url=authorize_url)


@app.get("/api/instagram/callback")
def instagram_callback(request: Request):
    email = request.session.get("user_email")
    if not email or not is_email_allowed(email):
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    error = request.query_params.get("error")
    if error:
        logger.warning("instagram-callback error=%s", error)
        return HTMLResponse(f"<p>Instagram authorization failed: {error}</p>", status_code=400)

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    expected_state = request.session.pop("instagram_oauth_state", None)
    if not code or not state or not expected_state or state != expected_state:
        logger.warning("instagram-callback: missing or mismatched state (possible CSRF or expired attempt)")
        return HTMLResponse(
            "<p>Instagram authorization failed: invalid or expired attempt. Please try again.</p>", status_code=400
        )

    try:
        exchange_instagram_code_for_tokens(code)
    except Exception:
        logger.exception("instagram-callback: token exchange failed")
        return HTMLResponse("<p>Instagram authorization failed during token exchange.</p>", status_code=400)

    logger.info("instagram-callback: authorization succeeded by=%s", email)
    return HTMLResponse("<p>Instagram account connected. You can close this tab and return to the dashboard.</p>")


@app.get("/api/instagram/webhook")
def instagram_webhook_verify(request: Request):
    """Meta's webhook verification handshake. Deliberately PUBLIC (no session
    check) -- Meta calls this directly, server-to-server, with no browser or
    session involved. This app doesn't process any webhook events (it only
    posts content); Meta's console still requires a working verification
    endpoint before it'll let you save a Webhooks configuration at all, so
    this exists purely to satisfy that, echoing back hub.challenge once
    hub.verify_token matches INSTAGRAM_WEBHOOK_VERIFY_TOKEN."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    expected_token = os.getenv("INSTAGRAM_WEBHOOK_VERIFY_TOKEN")

    if mode == "subscribe" and expected_token and token == expected_token:
        logger.info("instagram webhook verification succeeded")
        return PlainTextResponse(challenge or "")

    logger.warning("instagram webhook verification failed mode=%s token_match=%s", mode, token == expected_token)
    raise HTTPException(status_code=403, detail="Verification failed.")


@app.post("/api/instagram/webhook")
def instagram_webhook_event() -> dict:
    """Acknowledges webhook event deliveries. This app doesn't act on any of
    them (no comment/message handling) -- it just needs to return 200 so
    Meta doesn't disable the subscription after repeated failures."""
    logger.info("instagram webhook event received (ignored)")
    return {"status": "ok"}


@app.get("/api/images/{image_id}")
def serve_hosted_image(image_id: str):
    """Serves a temporarily-hosted image. Deliberately PUBLIC (no session
    check) -- Instagram's own servers fetch this URL directly and can't send
    our session cookie. Malformed/unknown ids are treated alike as 404,
    without leaking whether the id was invalid or simply not found."""
    try:
        result = load_image(image_id)
    except Exception:
        logger.exception("serve_hosted_image: lookup failed for image_id=%s", image_id)
        result = None
    if result is None:
        raise HTTPException(status_code=404, detail="Image not found.")
    content, content_type = result
    return Response(content=content, media_type=content_type)


@app.get("/api/cron/daily-tasks")
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
