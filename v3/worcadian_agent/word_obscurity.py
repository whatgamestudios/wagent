"""Score how obscure a word is.

Signal sources:
  - Word length: Worcadian's own rule of thumb — 9+ letter words are "WOW"
    regardless of how common they are, since building a 9+ letter chain off
    the seed is hard.
  - A precomputed Zipf-frequency lookup table (word_zipf.tsv.gz), covering
    every word in Worcadian's own game vocabulary, built offline from
    `wordfreq` (https://github.com/rspeer/wordfreq, MIT licensed) by
    scripts/build_word_cache.py. A word with zipf == 0 in the table is
    absent from all of wordfreq's real-world English corpora and is very
    likely an archaic or highly technical dictionary entry — exactly the
    kind of word Worcadian's lore describes ("some words are old...").

    Shipping this small precomputed table instead of the `wordfreq` package
    itself avoids ~58MB of frequency data for ~30 languages this game never
    uses (wordfreq's own English-only data is ~1.5MB of that) — a
    significant chunk of Vercel's 250MB unzipped function-size limit for a
    capability only ever used in English here.

  - A word absent from the lookup table entirely (not part of Worcadian's
    own game vocabulary, so no frequency signal is available for it) is
    treated as an ordinary COMMON word rather than as an error.

Standalone usage:
    python -m worcadian_agent.word_obscurity WORD1 WORD2 ...

To rebuild the lookup table after Worcadian's game word list changes, see
scripts/build_word_cache.py.
"""

from __future__ import annotations

import argparse
import gzip
from functools import lru_cache
from pathlib import Path

WORD_ZIPF_CACHE_PATH = Path(__file__).resolve().parent / "word_zipf.tsv.gz"

WOW_MIN_LENGTH = 9
IGNORE_MAX_LENGTH = 2
UNCOMMON_ZIPF_CEILING = 3.0


@lru_cache(maxsize=1)
def _word_zipf_cache() -> dict[str, float]:
    """Load the precomputed word -> Zipf-frequency lookup table (once per process)."""
    cache: dict[str, float] = {}
    with gzip.open(WORD_ZIPF_CACHE_PATH, "rt") as f:
        for line in f:
            word, _, zipf = line.rstrip("\n").partition("\t")
            if word:
                cache[word] = float(zipf)
    return cache


def score_word(word: str) -> dict:
    """Score a single word's obscurity.

    Returns {word, length, zipf, tier, obscurity_score}. tier is one of
    WOW / OBSCURE / UNCOMMON / COMMON / IGNORE. obscurity_score is 0-100,
    higher = more obscure. zipf is None when the word isn't in the
    precomputed lookup table, in which case it's treated as COMMON.
    """
    upper = word.strip().upper()
    length = len(upper)
    zipf = _word_zipf_cache().get(upper)

    if length >= WOW_MIN_LENGTH:
        tier = "WOW"
    elif length <= IGNORE_MAX_LENGTH:
        tier = "IGNORE"
    elif zipf is None:
        tier = "COMMON"
    elif zipf == 0:
        tier = "OBSCURE"
    elif zipf < UNCOMMON_ZIPF_CEILING:
        tier = "UNCOMMON"
    else:
        tier = "COMMON"

    base_score = max(0, min(100, round((7 - zipf) / 7 * 100))) if zipf is not None else 0
    obscurity_score = max(base_score, 85) if tier == "WOW" else base_score
    obscurity_score = obscurity_score if tier != "IGNORE" else 0

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


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("words", nargs="+", help="Words to score")
    args = parser.parse_args()

    results = score_words(args.words)
    header = f"{'WORD':<15}{'LEN':>4}{'ZIPF':>7}{'TIER':>10}{'OBSCURITY':>11}"
    print(header)
    print("-" * len(header))
    for r in results:
        zipf_display = f"{r['zipf']:.2f}" if r["zipf"] is not None else "?"
        print(f"{r['word']:<15}{r['length']:>4}{zipf_display:>7}{r['tier']:>10}{r['obscurity_score']:>11}")


if __name__ == "__main__":
    _main()
