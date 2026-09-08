# Worcadian Agent — v3 (Vercel FastAPI service)

A FastAPI app, deployed to [Vercel](https://vercel.com), that generates the daily
[Worcadian](https://whatgamestudios.com/worcadian/) press release two ways:

- **On a schedule** — a Vercel Cron Job hits `daily_tasks` once a day (default
  midnight UTC), which builds the press release and emails it via
  [Resend](https://resend.com) to a configured list of recipients.
- **On demand** — the logged-in dashboard page (`dashboard.html`) has an
  "Execute Daily Tasks" button that generates a press release for a chosen
  (or the current) game day and shows it in an output box, without sending
  any email.

The word-puzzle logic itself (`worcadian_agent/`) is carried over unchanged
from [v2](../v2/); see [v2/DESIGN.md](../v2/DESIGN.md) for how the pipeline
works. The changes in this version are: the app is served from Vercel/FastAPI
instead of run from the command line, LLM calls go through an ordered
**fallback chain of up to five optional providers**, and successful runs can
be emailed out automatically.

The site is two pages: a public landing page at `/` with a "Log in" button,
and a logged-in dashboard (the actual tool) behind Auth0 — see **Configuring
OAuth login** below.

## Project layout

```
v3/
  api/
    app.py                 the entire FastAPI app -- every route, one Vercel function
  worcadian_agent/         the press-release pipeline (fetch data, score words,
                            call the LLM, write the release; + daily_tasks/email;
                            + oauth.py/session.py/app_setup.py for login)
  index.html               public landing page, served at GET /
  dashboard.html           the actual tool, served at GET /dashboard once logged in
  vercel.json              function config, cron schedule
  requirements.txt
  .env.example
```

Everything lives in **one** FastAPI app in `api/app.py`. Earlier versions of
this project tried splitting concerns (login/callback/logout/home/landing)
into separate `api/*.py` files, on the assumption that each would become its
own Vercel serverless function. That assumption was wrong for this project:
Vercel's dashboard confirmed the deployment builds exactly **one** function
regardless of how many files exist, because it had detected "FastAPI" as the
project's framework and bundles the whole thing as a single consolidated
app — every other file was silently never actually deployed as anything,
and all traffic was always landing on whichever one file Vercel picked to
build (this one). See `api/app.py`'s module docstring for the full story.
The fix was the opposite of splitting things up: put every route in this one
file, using plain standard FastAPI paths (`/`, `/auth/login`,
`/auth/callback`, `/auth/logout`, `/dashboard`, `/api/press-release`,
`/api/cron/daily-tasks`) and let FastAPI's own router dispatch on the real
request path — no custom `vercel.json` rewrites needed at all.

## Configuring LLM providers

LLM calls go through [LangChain](https://python.langchain.com/), via its
[`init_chat_model()`](https://python.langchain.com/docs/how_to/chat_models_universal_init/)
universal constructor, which supports many providers (anthropic, openai,
google_genai, groq, ollama, and more). Up to five models are configured as
numbered slots:

```bash
# .env
MODEL_NAME_1=anthropic:claude-sonnet-5
MODEL_API_KEY_1=sk-ant-...

MODEL_NAME_2=openai:gpt-4o-mini
MODEL_API_KEY_2=sk-...

MODEL_NAME_3=google_genai:gemini-2.0-flash
MODEL_API_KEY_3=...

MODEL_NAME_4=groq:llama-3.3-70b-versatile
MODEL_API_KEY_4=...

# A local Ollama model needs no API key (rarely reachable from Vercel itself;
# mainly for local dev). It picks up OLLAMA_BASE_URL instead.
MODEL_NAME_5=ollama:llama3.1
OLLAMA_BASE_URL=http://localhost:11434
```

Slots are tried in order 1–5. The first slot with `MODEL_NAME_N` set is the
primary model; any further configured slots are attached as automatic
LangChain fallbacks (`with_fallbacks()`) — if a call to an earlier model
raises, LangChain retries it against the next configured one. Leave a slot's
`MODEL_NAME_N` blank to skip it; you don't need all five configured, just at
least one.

Each `MODEL_NAME_N` is a `"<provider>:<model>"` string — this prefix form is
recommended since it's unambiguous (a bare model id like `gpt-4o-mini` also
works for well-known families, with the provider inferred from the name, but
isn't as reliable). `MODEL_API_KEY_N` is passed to that model as its
`api_key`; leave it blank for a provider needing none (Ollama).

To force one specific model instead of the fallback chain, the CLI's
`--model` flag takes the same `"<provider>:<model>"` string directly (and an
optional `--provider` flag supplies the provider separately if `--model`
doesn't already have a prefix).

## Configuring email delivery

`daily_tasks` sends the generated press release through Resend:

- `RESEND_API_KEY` — your [Resend](https://resend.com) API key.
- `EMAIL_RECIPIENTS` — a **comma-separated list** of recipient addresses,
  e.g. `EMAIL_RECIPIENTS=alice@example.com,bob@example.com`.
- `EMAIL_FROM` — optional; defaults to Resend's shared `onboarding@resend.dev`
  sender. Set this to an address on a domain you've verified with Resend for
  production use.

## Configuring dictionary lookups

Both `daily_tasks` and the on-demand "Execute Daily Tasks" button look up the
seed word and every notable (WOW/OBSCURE-tier) word of the day in the
[Merriam-Webster Collegiate Dictionary API](https://dictionaryapi.com/products/api-collegiate-dictionary),
via `worcadian_agent/dictionary_client.py`. Get a free key at
https://dictionaryapi.com/register/index and set:

- `MERRIAM_WEBSTER_API_KEY` — required for lookups to run at all; if unset,
  lookups are silently skipped (the press release itself still generates).

For each word, the client extracts the first entry Merriam-Webster returns
and pulls three fields from it: `part_of_speech` (the entry's functional
label, e.g. "noun"), `definition` (the first full definition, with
Merriam-Webster's markup stripped), and `short_definition` (Merriam-Webster's
own condensed one-liner). A word Merriam-Webster doesn't recognize is simply
omitted rather than erroring out.

This information is shown as a separate text box per word on the website,
and as a separate section per word in the daily email (after the press
release text).

## Configuring OAuth login

`/` is a public landing page (just "Worcadian Agent" and a "Log in" button —
no session required to view it). The actual dashboard (`GET /dashboard`) and
the on-demand "Execute Daily Tasks" button (`POST /api/press-release`) both
require a logged-in, allowlisted account via [Auth0](https://auth0.com) —
see `worcadian_agent/oauth.py`. The Vercel Cron Job
(`GET /api/cron/daily-tasks`) is **not** OAuth-gated (it's protected by
`CRON_SECRET` instead), since it's a machine-to-machine call that can't go
through a browser login flow.

1. In the [Auth0 dashboard](https://manage.auth0.com/), go to **Applications
   → Create Application**, choose **Regular Web Applications**.
2. In that application's **Settings** tab, add to **Allowed Callback URLs**:
   `<PUBLIC_BASE_URL>/auth/callback`, e.g.
   `https://worcadian-agent.vercel.app/auth/callback`; and add
   `<PUBLIC_BASE_URL>` (no path) to **Allowed Logout URLs**. Both must match
   `PUBLIC_BASE_URL` below exactly (scheme included, no trailing slash).
3. Set these env vars:
   - `AUTH0_DOMAIN` — your tenant domain shown on that Settings page, e.g.
     `your-tenant.us.auth0.com` (no scheme, no trailing slash).
   - `AUTH0_CLIENT_ID` / `AUTH0_CLIENT_SECRET` — from the same Settings page.
   - `PUBLIC_BASE_URL` — your deployed site's base URL, no trailing slash.
   - `ALLOWED_EMAILS` — comma-separated list of email addresses allowed to
     log in. Anyone else who successfully authenticates via Auth0 is still
     denied (this is the only setting that actually restricts access, not
     just identity).
   - `SESSION_SECRET_KEY` — a random secret signing the session cookie:
     ```bash
     python -c "import secrets; print(secrets.token_urlsafe(32))"
     ```

The session is a signed cookie (via Starlette's `SessionMiddleware` /
`itsdangerous`, configured in `worcadian_agent/session.py`), not server-side
storage. The "Log out" link on the dashboard hits `/auth/logout`, which
clears the local session cookie *and* redirects through Auth0's own
`/v2/logout` endpoint (back to `/`, the public landing page) — that second
part matters because Auth0 keeps its own SSO session independent of our
cookie, so skipping it would let a user get silently re-authenticated
without re-entering credentials.

Auth0's free tier can itself delegate to Google, GitHub, email/password, etc.
as "social connections" if you want those sign-in options — that's
configured entirely on Auth0's side (Authentication → Social) and needs no
code changes here, since this app only ever talks to Auth0's own endpoints.

## Configuring the time of day `daily_tasks` runs

`daily_tasks` is triggered by the Vercel Cron Job defined in `vercel.json`:

```json
"crons": [
  { "path": "/api/cron/daily-tasks", "schedule": "0 0 * * *" }
]
```

The `schedule` field is a standard 5-field cron expression (`minute hour day
month weekday`), always evaluated in **UTC**. `0 0 * * *` is midnight UTC. To
run it at, say, 06:30 UTC instead, change it to `30 6 * * *`. After editing,
redeploy for the new schedule to take effect. Note that Vercel's Hobby plan
limits cron jobs to **one invocation per day** (any single hour/minute is
fine); Pro plans allow more frequent schedules.

Set `CRON_SECRET` (as a Vercel environment variable) to have the endpoint
require it as a bearer token — Vercel automatically sends
`Authorization: Bearer <CRON_SECRET>` on requests it makes to your cron path,
so this prevents anyone else from triggering (and emailing out) the job by
guessing the URL.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then fill in at least one LLM provider's API key,
                        # plus the OAuth vars (PUBLIC_BASE_URL=http://localhost:8000
                        # for local testing) with a callback URL of
                        # http://localhost:8000/auth/callback registered in
                        # the Auth0 dashboard

uvicorn api.app:app --reload
```

Then open `http://localhost:8000`. Since it's one plain FastAPI app, plain
`uvicorn` matches production routing exactly — no need for `vercel dev`
just to exercise the login flow.

## Deploying to Vercel

```bash
npm i -g vercel   # if you don't already have the CLI
cd v3
vercel link
vercel env add ANTHROPIC_API_KEY        # repeat for each env var you're using
vercel env add MERRIAM_WEBSTER_API_KEY
vercel env add RESEND_API_KEY
vercel env add EMAIL_RECIPIENTS
vercel env add CRON_SECRET
vercel env add AUTH0_DOMAIN
vercel env add AUTH0_CLIENT_ID
vercel env add AUTH0_CLIENT_SECRET
vercel env add PUBLIC_BASE_URL
vercel env add ALLOWED_EMAILS
vercel env add SESSION_SECRET_KEY
vercel deploy --prod
```

Environment variables can also be set from the Vercel dashboard under
Project Settings → Environment Variables.

## API endpoints

- `GET /` — the public landing page (`index.html`, no login needed):
  "Worcadian Agent" and a "Log in" button pointing at `/auth/login`.
- `GET /auth/login` — redirects to Auth0's login page.
- `GET /auth/callback` — Auth0 redirects back here with the auth code;
  exchanges it for the account's email, checks `ALLOWED_EMAILS`, and sets the
  session cookie (or shows an error/access-denied page), then redirects to
  `/dashboard`.
- `GET /dashboard` — the OAuth-gated dashboard (`dashboard.html`). Redirects
  to `/` if there's no valid, allowlisted session.
- `GET /auth/logout` — clears the session cookie and redirects through
  Auth0's own logout endpoint back to `/`.
- `POST /api/press-release` — requires a valid session (401 if not logged
  in). Body `{"day": 120}` (or `{"day": null}`/omitted for the current game
  day). Returns `{"game_day": ..., "seed_word": ..., "text": ..., "definitions": {...}}`,
  where `definitions` maps each looked-up word (seed word first, then
  notable words in most-to-least obscure order) to
  `{part_of_speech, definition, short_definition}`. Used by the dashboard's
  "Execute Daily Tasks" button; does not send email or generate any word card.
- `POST /api/word-card` — requires a valid session. Body
  `{"word": ..., "part_of_speech": ..., "definition": ..., "palette": ...}`
  (`palette` is optional, one of `worcadian_agent/image_card.py`'s `PALETTES`
  keys, default `"parchment"`; an unrecognized name silently falls back to
  the default rather than erroring); returns
  `{"card_image": "data:image/png;base64,..."}`, rendered on demand by
  `worcadian_agent/image_card.py`. Used by each "Generate Card" button and
  the palette swatch buttons on the dashboard — nothing is persisted to disk.
- `GET /api/cron/daily-tasks` — builds the press release for the current game
  day, looks up its words, and emails everything to `EMAIL_RECIPIENTS`. This
  is what the Vercel Cron Job calls; protected by the `CRON_SECRET` bearer
  token (not OAuth) if that env var is set.

## The website

**`/` (`index.html`)** is a public landing page needing no login: just the
title "Worcadian Agent" and a "Log in" button that sends the browser to
`/auth/login`.

**The dashboard (`dashboard.html`, served at `GET /dashboard`** once logged
in — see **Configuring OAuth login**) has a "Log out" link next to the
subtitle, a game-day number field (leave blank to use the current game day),
and an **Execute Daily Tasks** button that calls `POST /api/press-release`
and populates two sections: **Seed Word** (the day's seed word, its part of
speech, and a read-only definition box) and **Words Used** (every other
looked-up word, most-to-least obscure, each with its own definition box and
**Generate Card**/**Tweet** buttons), plus a **Free Entry** section (word,
type of word, and definition fields with its own **Generate Card**/**Tweet**
buttons, for any word not looked up automatically). Clicking a "Generate
Card" button calls `POST /api/word-card` for just that word and displays the
result in the **Word Card** section below, alongside a dozen color-swatch
buttons — one per palette in `worcadian_agent/image_card.py`'s `PALETTES` —
that regenerate the *currently shown* card in that palette (they act on
whatever word/definition produced the card last, not a fixed word). Clicking
a "Tweet" button fills the **Tweet** section at the bottom with
`Worcadian word of the day <WORD>: <definition>`, entirely client-side — no
request is made and nothing is actually posted to Twitter/X. If the session
has expired, any card-generating action redirects to `/auth/login` instead
of showing an error.

The favicon (both pages) is the Worcadian logo, loaded directly from
`https://whatgamestudios.com/worcadian/worcadian-logo.png`.
