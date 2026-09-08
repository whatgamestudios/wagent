"""One-off manual test: post a single tweet using the configured X credentials.

Since the app now uses OAuth 2.0 (see worcadian_agent/twitter.py), the
account must already be connected once via /api/x/authorize (through the
real deployed app, logged in) before this will work -- this script only
posts using whatever token pair is already stored in DATABASE_URL, it
doesn't do the browser authorization step itself. So point DATABASE_URL (in
your local .env) at the SAME Postgres database the deployment uses.

Run locally (with your real credentials in .env, never committed) to verify
things work independent of the Vercel deployment:

    python scripts/test_tweet.py "test tweet, please ignore"

This calls the exact same worcadian_agent.twitter.post_tweet() the deployed
app uses. If it fails here too, the problem is the stored token / X App
configuration itself, not anything Vercel- or deployment-specific -- see the
"Configuring X (Twitter) posting" section of the README. If it works here
but still fails on Vercel, check how the env vars (especially DATABASE_URL)
were entered there -- stray whitespace is the most common cause.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from worcadian_agent.twitter import post_tweet  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Usage: python scripts/test_tweet.py "tweet text"')
    result = post_tweet(sys.argv[1])
    print("Posted:", result)


if __name__ == "__main__":
    main()
