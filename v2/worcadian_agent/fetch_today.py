"""Fetch today's Worcadian seed word, winning boards, and the words each player used.

Standalone usage:
    python -m worcadian_agent.fetch_today [--day N]

Prints the assembled game-day data as JSON to stdout.
"""

from __future__ import annotations

import argparse
import json

from worcadian_agent.game_client import board_analyse, board_results, gameday_current, seed_word


def fetch_today_data(day: int | None = None) -> dict:
    """Assemble seed word, best score, and per-player words for a game day.

    Defaults to the server's current max_day (the most recently opened day)
    when no day is given.
    """
    if day is None:
        day = gameday_current()["max_day"]

    seed = seed_word(day)
    results = board_results(day)

    players = []
    for submission in results["submissions"]:
        analysis = board_analyse(submission["board"])
        players.append(
            {
                "player": submission["player"],
                "words": analysis["words"],
                "in_dictionary": analysis["in_dictionary"],
                "score": analysis["score"],
            }
        )

    return {
        "game_day": day,
        "seed_word": seed,
        "num_submissions": results["num_submissions"],
        "best_score": results["best_score"],
        "players": players,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", type=int, default=None, help="Game day to fetch (default: current max_day)")
    args = parser.parse_args()

    data = fetch_today_data(args.day)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    _main()
