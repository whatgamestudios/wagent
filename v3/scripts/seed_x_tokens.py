"""One-off setup: seed the X (Twitter) OAuth2 token pair from a refresh token
generated directly in console.x.com, skipping the /api/x/authorize browser
flow entirely.

Some console.x.com app configurations let you generate an Access Token +
Refresh Token pair directly in the portal, alongside the Client ID/Secret.
If you already have one, there's no need to visit /api/x/authorize -- just
seed the database with it here. This immediately exchanges the refresh token
for a fresh access token (X's refresh tokens rotate on every use, so this
also proves the refresh token actually works) and stores the result via
worcadian_agent.token_store, exactly like a real refresh would.

Run locally, with DATABASE_URL (in .env) pointed at the SAME Postgres
database the deployment uses:

    python scripts/seed_x_tokens.py "<refresh token from console.x.com>"

Afterwards, verify posting works with:

    python scripts/test_tweet.py "test tweet, please ignore"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from worcadian_agent.twitter import refresh_access_token  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Usage: python scripts/seed_x_tokens.py "<refresh token>"')
    refresh_access_token(sys.argv[1])
    print("Seeded a fresh token pair into DATABASE_URL. Try scripts/test_tweet.py next.")


if __name__ == "__main__":
    main()
