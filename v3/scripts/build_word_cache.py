"""One-off maintenance script: rebuild worcadian_agent/word_zipf.tsv.gz.

This precomputes the `wordfreq` Zipf frequency for every word in Worcadian's
official game vocabulary and writes it as a small gzipped lookup table, so
the deployed app can look up a word's frequency without depending on the
`wordfreq` package at runtime. `wordfreq` bundles ~58MB of frequency data
across ~30 languages (its English-only data is ~1.5MB of that), which is a
meaningful chunk of Vercel's 250MB unzipped function-size limit for a
capability this app only ever uses in English -- see word_obscurity.py,
which reads the resulting file as a plain lookup table instead.

Run this again only when Worcadian's game word list changes meaningfully.
`wordfreq` is NOT a runtime dependency of the app -- install it separately to
run this script:

    pip install wordfreq
    python scripts/build_word_cache.py

Words not present in the output file are treated by word_obscurity.py as
ordinary COMMON words (no frequency signal available), not as an error.
"""

from __future__ import annotations

import gzip
import sys
import urllib.request
from pathlib import Path

try:
    from wordfreq import zipf_frequency
except ImportError:
    sys.exit("This script needs `wordfreq` installed: pip install wordfreq")

GAME_WORDLIST_URL = (
    "https://raw.githubusercontent.com/whatgamestudios/crosswords/main/"
    "CrossWords/Assets/Resources/wordlists/game_words.txt"
)
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "worcadian_agent" / "word_zipf.tsv.gz"


def main() -> None:
    print(f"Downloading game word list from {GAME_WORDLIST_URL} ...")
    with urllib.request.urlopen(GAME_WORDLIST_URL, timeout=30) as resp:
        raw = resp.read().decode()
    words = sorted({line.strip().upper() for line in raw.splitlines() if line.strip()})
    print(f"{len(words)} words. Scoring with wordfreq...")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUTPUT_PATH, "wt") as f:
        for word in words:
            zipf = zipf_frequency(word.lower(), "en")
            f.write(f"{word}\t{zipf}\n")

    print(f"Wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
