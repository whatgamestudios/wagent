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

## Project layout

```
v3/
  api/app.py              FastAPI app (Vercel serverless function)
  worcadian_agent/         the press-release pipeline (fetch data, score words,
                            call the LLM, write the release; + daily_tasks/email)
  index.html               static root page ("Execute Daily Tasks" UI)
  vercel.json               routing, cron schedule, function config
  requirements.txt
  .env.example
```

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

cp .env.example .env   # then fill in at least one LLM provider's API key

uvicorn api.app:app --reload
```

Then open `http://localhost:8000` — the app also serves `index.html`
directly when run this way, purely for local convenience (in production,
Vercel serves `index.html` as a static file and only routes `/api/*` to this
app). `vercel dev` from this directory also works and matches production
routing exactly.

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
vercel deploy --prod
```

Environment variables can also be set from the Vercel dashboard under
Project Settings → Environment Variables.

## API endpoints

- `POST /api/press-release` — body `{"day": 120}` (or `{"day": null}`/omitted
  for the current game day). Returns `{"game_day": ..., "text": ..., "definitions": {...}}`,
  where `definitions` maps each looked-up word to
  `{part_of_speech, definition, short_definition}`. Used by the root page's
  "Execute Daily Tasks" button; does not send email.
- `GET /api/cron/daily-tasks` — builds the press release for the current game
  day, looks up its words, and emails everything to `EMAIL_RECIPIENTS`. This
  is what the Vercel Cron Job calls; requires the `CRON_SECRET` bearer token
  if that env var is set.

## The website

The root page (`index.html`) is titled **Worcadian Agent**. It has a game-day
number field (leave blank to use the current game day) and an **Execute Daily
Tasks** button that calls `POST /api/press-release` and displays the
generated press release in the output text box, followed by one read-only
text box per looked-up word showing its part of speech, definition, and
short definition. Below that, a word card image is shown for the *last*
looked-up word — rendered on demand by `worcadian_agent/image_card.py`
(word, part of speech, and definition in, PNG bytes out) and returned inline
as a base64 `data:` URI in the API response, with no file persisted anywhere.
The favicon is the Worcadian logo, loaded directly from
`https://whatgamestudios.com/worcadian/worcadian-logo.png`.
