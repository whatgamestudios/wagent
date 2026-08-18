"""JSON-RPC client for the Worcadian game server.

API reference: https://github.com/whatgamestudios/gameserver/blob/main/API.md
"""

from __future__ import annotations

import itertools
from typing import Any

import requests

RPC_URL = "https://worcadian.vercel.app/rpc"

_id_counter = itertools.count(1)


def rpc(method: str, params: dict[str, Any] | None = None, timeout: float = 15.0) -> Any:
    """Call a JSON-RPC 2.0 method on the Worcadian game server and return its result."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": next(_id_counter),
    }
    resp = requests.post(RPC_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"{method} failed: {data['error']}")
    return data["result"]


def gameday_current() -> dict[str, int]:
    """Return {'min_day': int, 'max_day': int} — the currently valid game day range."""
    return rpc("gameday.current")


def seed_word(day: int) -> str | None:
    """Return the seed word for a single game day, or None if unconfigured."""
    result = rpc("seedwords.check", {"days": [day]})
    return result[str(day)]


def board_results(day: int) -> dict[str, Any]:
    """Return {num_submissions, best_score, submissions:[{player, board}]} for a game day."""
    return rpc("board.results", {"game_day": day})


def board_analyse(board: str) -> dict[str, Any]:
    """Return {score, words, in_dictionary} for a 121-character board string."""
    return rpc("board.analyse", {"board": board})
