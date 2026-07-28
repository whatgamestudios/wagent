"""Score how obscure a word is.

Signal sources:
  - Word length: Worcadian's own rule of thumb — 9+ letter words are "WOW" regardless
    of how common they are, since building a 9+ letter chain off the seed is hard.
  - `wordfreq` (https://github.com/rspeer/wordfreq, MIT licensed): an open-source
    library giving Zipf frequency of a word across real-world English corpora
    (Wikipedia, subtitles, news, books, Reddit, Twitter). A word absent from all of
    those corpora is very likely an archaic or highly technical dictionary entry —
    exactly the kind of word Worcadian's lore describes ("some words are old...").

Standalone usage:
    python -m worcadian_agent.word_obscurity WORD1 WORD2 ...
    python -m worcadian_agent.word_obscurity --calibrate
"""

from __future__ import annotations

import argparse
import statistics
import urllib.request
from pathlib import Path

from wordfreq import zipf_frequency

GAME_WORDLIST_URL = (
    "https://raw.githubusercontent.com/whatgamestudios/crosswords/main/"
    "CrossWords/Assets/Resources/wordlists/game_words.txt"
)
GAME_WORDLIST_CACHE = Path(__file__).resolve().parent.parent / "data" / "game_words.txt"

WOW_MIN_LENGTH = 9
UNCOMMON_ZIPF_CEILING = 3.0


def score_word(word: str) -> dict:
    """Score a single word's obscurity.

    Returns {word, length, zipf, tier, obscurity_score}. tier is one of
    WOW / OBSCURE / UNCOMMON / COMMON. obscurity_score is 0-100, higher = more obscure.
    """
    upper = word.strip().upper()
    length = len(upper)
    zipf = zipf_frequency(upper.lower(), "en")

    if length >= WOW_MIN_LENGTH:
        tier = "WOW"
    elif zipf == 0:
        tier = "OBSCURE"
    elif zipf < UNCOMMON_ZIPF_CEILING:
        tier = "UNCOMMON"
    else:
        tier = "COMMON"

    base_score = max(0, min(100, round((7 - zipf) / 7 * 100)))
    obscurity_score = max(base_score, 85) if tier == "WOW" else base_score

    return {
        "word": upper,
        "length": length,
        "zipf": zipf,
        "tier": tier,
        "obscurity_score": obscurity_score,
    }


def score_words(words: list[str]) -> list[dict]:
    """Score a batch of words, sorted most-obscure first."""
    return sorted((score_word(w) for w in words), key=lambda d: d["obscurity_score"], reverse=True)


def download_game_wordlist(path: Path = GAME_WORDLIST_CACHE) -> Path:
    """Download and cache the full Worcadian game vocabulary (one word per line)."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(GAME_WORDLIST_URL, timeout=30) as resp:
            path.write_bytes(resp.read())
    return path


def _calibrate() -> None:
    """Print a zipf-frequency distribution over the full game word list.

    This is what justifies the UNCOMMON_ZIPF_CEILING threshold above — run during
    development, not on every scoring call.
    """
    path = download_game_wordlist()
    words = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    zipfs = [zipf_frequency(w.lower(), "en") for w in words]
    zero_count = sum(1 for z in zipfs if z == 0)

    print(f"game word list: {len(words)} words")
    print(f"zipf == 0 (absent from general corpora): {zero_count} ({zero_count / len(words):.1%})")
    print(f"mean zipf:   {statistics.mean(zipfs):.2f}")
    print(f"median zipf: {statistics.median(zipfs):.2f}")
    nonzero = [z for z in zipfs if z > 0]
    if nonzero:
        print(f"mean zipf (excluding zeros): {statistics.mean(nonzero):.2f}")


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("words", nargs="*", help="Words to score")
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Download the full game word list and print a zipf-frequency distribution",
    )
    args = parser.parse_args()

    if args.calibrate:
        _calibrate()
        return

    if not args.words:
        parser.error("provide one or more words, or use --calibrate")

    results = score_words(args.words)
    header = f"{'WORD':<15}{'LEN':>4}{'ZIPF':>7}{'TIER':>10}{'OBSCURITY':>11}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r['word']:<15}{r['length']:>4}{r['zipf']:>7.2f}{r['tier']:>10}{r['obscurity_score']:>11}")


if __name__ == "__main__":
    _main()
