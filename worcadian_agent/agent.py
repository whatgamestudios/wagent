"""Worcadian daily press release agent.

Pipeline: fetch today's game data -> score word obscurity -> detect shared
discoveries across players -> one LangChain prompt/LLM/parser call writes a
~500-word newspaper-style summary -> write it to <game_day>-<date>.txt.

Usage:
    python -m worcadian_agent.agent [--day N] [--provider ollama|anthropic] [--model NAME]
"""

from __future__ import annotations

import argparse
import json
import textwrap
from collections import defaultdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from worcadian_agent.fetch_today import fetch_today_data
from worcadian_agent.llm_factory import get_llm
from worcadian_agent.word_obscurity import score_words

LORE_PATH = Path(__file__).resolve().parent / "skills" / "worcadian_lore.md"

REPORTER_INSTRUCTIONS = """\
You are a newspaper reporter covering the daily Worcadian word puzzle. Using the
game facts provided (as JSON) and your background knowledge of the game above,
write a press release of approximately 500 words (strictly between 450 and 550
words), suitable for a newspaper.

Cover: the seed word and game day, how many players reached the best score and
what that score was, and any standout obscure or "WOW" (9+ letter) words that
were played. If no "WOW" words were used, don't mention this. If no obscure words
were used, don't mention this. 

From the "notable_words" list, choose exactly one OBSCURE-tier word (pick the
one you are most confident you know the real meaning of) and give it its own
short paragraph: state the word, and briefly describe its definition in plain
English. If you are not confident of a word's real meaning, say so plainly 
instead of guessing, or pick a different obscure word you are more confident about.

The "shared_words" field is the authoritative list of words used by more than
one player — it may be empty. Only mention a word as being independently
discovered by multiple players if it literally appears as a key in
shared_words. Never infer or invent an overlap from words merely looking
similar (e.g. a word and its plural, like GROWTH and GROWTHS, are NOT the same
word and must not be described as shared). If shared_words is empty, do not
mention convergence at all.

Do not invent facts, definitions you are unsure of, or details absent from the
JSON. Write in a factual, engaging journalistic style. Do not list raw stats or
JSON — turn them into prose. Output only the press release text, no title or
preamble.

Do not mention the names of players. Just used words such as "one player", and 
"another player".

Use the term "game day", and not just "day".
"""


def wrap_text(text: str, width: int = 80) -> str:
    """Word-wrap text at `width` columns, preserving paragraph breaks."""
    paragraphs = text.strip().split("\n\n")
    return "\n\n".join(textwrap.fill(p.strip(), width=width) for p in paragraphs if p.strip())


def find_shared_words(players: list[dict], seed_word: str) -> dict[str, list[str]]:
    """Words (excluding the seed word) that more than one player used."""
    word_to_players: dict[str, list[str]] = defaultdict(list)
    for p in players:
        for word, in_dict in zip(p["words"], p["in_dictionary"]):
            if in_dict and word.upper() != seed_word.upper():
                word_to_players[word].append(p["player"])
    return {word: ps for word, ps in word_to_players.items() if len(ps) > 1}


def build_press_release(
    day: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    output_dir: str | Path = "output",
) -> Path:
    data = fetch_today_data(day)
    players = data["players"]
    seed = data["seed_word"]

    dictionary_words = sorted(
        {word for p in players for word, ok in zip(p["words"], p["in_dictionary"]) if ok}
    )
    scores_by_word = {s["word"]: s for s in score_words(dictionary_words)}

    for p in players:
        p["word_scores"] = [
            scores_by_word[word]
            for word, ok in zip(p["words"], p["in_dictionary"])
            if ok
        ]

    shared_words = find_shared_words(players, seed)
    notable_words = sorted(
        (s for s in scores_by_word.values() if s["tier"] in ("WOW", "OBSCURE")),
        key=lambda s: s["obscurity_score"],
        reverse=True,
    )

    facts = {
        "game_day": data["game_day"],
        "seed_word": seed,
        "num_submissions": data["num_submissions"],
        "best_score": data["best_score"],
        "players": [
            {"score": p["score"], "words": p["word_scores"]}
            for p in players
        ],
        "shared_words": shared_words,
        "notable_words": notable_words,
    }

    if shared_words:
        shared_note = "Words independently discovered by more than one player today: " + "; ".join(
            f"{word} (used by {', '.join(ps)})" for word, ps in shared_words.items()
        )
    else:
        shared_note = (
            "No word was independently discovered by more than one player today — "
            "do not claim any convergence happened."
        )

    lore = LORE_PATH.read_text()
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", lore + "\n\n" + REPORTER_INSTRUCTIONS),
            ("human", "Today's game facts:\n{facts}\n\n{shared_note}"),
        ]
    )

    llm = get_llm(provider, model)
    chain = prompt | llm | StrOutputParser()
    summary = chain.invoke(
        {"facts": json.dumps(facts, indent=2), "shared_note": shared_note}
    ).strip()
    summary = wrap_text(summary)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{data['game_day']}-{date.today().isoformat()}.txt"
    out_path = output_dir / filename
    out_path.write_text(summary + "\n")

    return out_path


def _main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", type=int, default=None, help="Game day to report on (default: current max_day)")
    parser.add_argument("--provider", choices=["ollama", "anthropic"], default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    path = build_press_release(
        day=args.day,
        provider=args.provider,
        model=args.model,
        output_dir=args.output_dir,
    )
    print(f"Wrote {path}")


if __name__ == "__main__":
    _main()
