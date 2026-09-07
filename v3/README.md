# Worcadian Agent — v3 (Vercel FastAPI service)

A FastAPI app, deployed to [Vercel](https://vercel.com), that generates the daily
[Worcadian](https://whatgamestudios.com/worcadian/) press release two ways:

- **On a schedule** — a Vercel Cron Job hits `daily_tasks` once a day (default
  midnight UTC), which builds the press release and emails it via
  [Resend](https://resend.com) to a configured list of recipients.
- **On demand** — the root page (`index.html`) has an "Execute Daily Tasks"
  button that generates a press release for a chosen (or the current) game
  day and shows it in an output box, without sending any email.

The word-puzzle logic itself (`worcadian_agent/`) is carried over unchanged
from [v2](../v2/); see [v2/DESIGN.md](../v2/DESIGN.md) for how the pipeline
works. The changes in this version are: the app is served from Vercel/FastAPI
instead of run from the command line, LLM calls go through an ordered
**fallback chain of up to five optional providers**, and successful runs can
be emailed out automatically.

The whole site requires Auth0 sign-in — see **Configuring OAuth login**
below.

## Project layout

```
v3/
  api/
    app.py                 press-release + cron endpoints (Vercel function)
    home.py                serves index.html, gated by OAuth session (Vercel function)
    login.py               starts the Auth0 login flow (Vercel function)
    callback.py            handles Auth0's OAuth redirect (Vercel function)
    logout.py              clears the session (Vercel function)
  worcadian_agent/         the press-release pipeline (fetch data, score words,
                            call the LLM, write the release; + daily_tasks/email;
                            + oauth.py/session.py/app_setup.py for login)
  index.html               the page itself (served by api/home.py, not statically)
  vercel.json              routing, cron schedule, function config
  requirements.txt
  .env.example
```

Each `api/*.py` file is deployed as its own separate Vercel serverless
function — see `api/home.py`'s module docstring for why (in short: sharing
one function across multiple distinct GET endpoints via a rewrite ran into a
real gotcha where the rewrite collapses the request path, so each concern
gets its own dedicated function+route instead).

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

The website (`GET /`) and the on-demand "Execute Daily Tasks" button
(`POST /api/press-release`) both require a logged-in, allowlisted account via
[Auth0](https://auth0.com) — see `worcadian_agent/oauth.py`. The Vercel Cron
Job (`GET /api/cron/daily-tasks`) is **not** OAuth-gated (it's protected by
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
`itsdangerous`), not server-side storage, so it works fine across the
separate `api/home.py`/`api/login.py`/`api/callback.py`/`api/logout.py`
functions as long as they all share the same `SESSION_SECRET_KEY` (they do,
via `worcadian_agent/session.py`). The "Log out" link on the page hits
`/auth/logout`, which clears the local session cookie *and* redirects
through Auth0's own `/v2/logout` endpoint — that second part matters because
Auth0 keeps its own SSO session independent of our cookie, so skipping it
would let a user get silently re-authenticated without re-entering
credentials.

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
                        # for local testing) with a redirect URI of
                        # http://localhost:8000/auth/callback registered in
                        # Auth0 dashboard

vercel dev
```

Since the site is now split across five separate functions (`api/app.py`,
`home.py`, `login.py`, `callback.py`, `logout.py`) tied together by
`vercel.json`'s rewrites, `vercel dev` (which applies those same rewrites
locally) is the only way to exercise the full logged-in flow with one
command; open `http://localhost:3000` (its default port). Running a single
function directly with `uvicorn api.home:app --reload`, etc. still works for
poking at one endpoint in isolation via its friendly path (e.g. `/` on
`api.home`, `/auth/login` on `api.login`), since each file registers its
route at both its friendly path and its Vercel-assigned one.

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

- `GET /` — the OAuth-gated home page. Redirects to `/auth/login` if there's
  no valid, allowlisted session.
- `GET /auth/login` — redirects to Auth0's login page.
- `GET /auth/callback` — Auth0 redirects back here with the auth code;
  exchanges it for the account's email, checks `ALLOWED_EMAILS`, and sets the
  session cookie (or shows an error/access-denied page).
- `GET /auth/logout` — clears the session cookie and redirects to `/`.
- `POST /api/press-release` — requires a valid session (401 if not logged
  in). Body `{"day": 120}` (or `{"day": null}`/omitted for the current game
  day). Returns `{"game_day": ..., "text": ..., "definitions": {...}, "card_image": ...}`,
  where `definitions` maps each looked-up word to
  `{part_of_speech, definition, short_definition}` and `card_image` is a
  base64 `data:image/png;...` URI (or `null`). Used by the page's "Execute
  Daily Tasks" button; does not send email.
- `GET /api/cron/daily-tasks` — builds the press release for the current game
  day, looks up its words, and emails everything to `EMAIL_RECIPIENTS`. This
  is what the Vercel Cron Job calls; protected by the `CRON_SECRET` bearer
  token (not OAuth) if that env var is set.

## The website

The page (`index.html`, served by `api/home.py` — see **Configuring OAuth
login**) is titled **Worcadian Agent**, with a "Log out" link next to the
subtitle. It has a game-day number field (leave blank to use the current game
day) and an **Execute Daily Tasks** button that calls `POST /api/press-release`
and displays the generated press release in the output text box, followed by
one read-only text box per looked-up word showing its part of speech,
definition, and short definition. Below that, a word card image is shown for
the *last* looked-up word — rendered on demand by
`worcadian_agent/image_card.py` (word, part of speech, and definition in,
PNG bytes out) and returned inline as a base64 `data:` URI in the API
response, with no file persisted anywhere. If the session has expired, the
button redirects to `/auth/login` instead of showing an error. The favicon is
the Worcadian logo, loaded directly from
`https://whatgamestudios.com/worcadian/worcadian-logo.png`.
