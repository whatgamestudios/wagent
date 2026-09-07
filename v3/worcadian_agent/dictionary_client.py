"""Merriam-Webster Collegiate Dictionary API client.

https://dictionaryapi.com/products/api-collegiate-dictionary

Get a free API key at https://dictionaryapi.com/register/index, then set it
as MERRIAM_WEBSTER_API_KEY.

The API returns a JSON array of entry objects for a recognized word, or an
array of plain spelling-suggestion strings when it isn't recognized. This
client always uses the *first* entry Merriam-Webster returns (their own
primary/most relevant sense) and extracts three fields from it:

  - part_of_speech: the entry's "fl" (functional label), e.g. "noun", "verb".
  - definition: the first full definition text under that entry's first
    sense, with Merriam-Webster's run-in markup tokens (e.g. "{bc}", "{it}")
    stripped out.
  - short_definition: entries[0]["shortdef"][0] -- Merriam-Webster's own
    pre-condensed one-line definition, provided for exactly this kind of
    space-constrained display.
"""

from __future__ import annotations

import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

API_URL = "https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}"

_MARKUP_RE = re.compile(r"\{[^}]*\}")


def _clean_definition_text(text: str) -> str:
    """Extract just the first sense's text from a raw `dt` definition string.

    "{bc}" (bold colon) separates distinct sub-senses grouped under the same
    numbered definition -- truncate there rather than deleting it, since
    simply stripping it would run unrelated definition fragments together.
    Other run-in markup tokens (e.g. "{it}...{/it}") are stripped outright.
    """
    text = text.split("{bc}", 1)[0]
    text = _MARKUP_RE.sub("", text)
    text = text.strip()
    if text.startswith(":"):
        text = text[1:].strip()
    return text


def _first_definition(entry: dict) -> str | None:
    """Pull the first sense's defining text out of an entry's "def" structure, if present."""
    try:
        dt = entry["def"][0]["sseq"][0][0][1]["dt"]
        text = next(value for kind, value in dt if kind == "text")
    except (KeyError, IndexError, StopIteration, TypeError):
        return None
    return _clean_definition_text(text)


def lookup_word(word: str, api_key: str | None = None) -> dict | None:
    """Look up `word` in the Merriam-Webster Collegiate Dictionary.

    Returns {"word", "part_of_speech", "definition", "short_definition"} for
    the first entry Merriam-Webster returns, or None if the word wasn't
    recognized (the API returned spelling suggestions instead of an entry).
    """
    api_key = (api_key or os.getenv("MERRIAM_WEBSTER_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("MERRIAM_WEBSTER_API_KEY is not set.")

    url = API_URL.format(word=word.strip().lower())
    logger.info("dictionary lookup word=%s", word)
    try:
        resp = requests.get(url, params={"key": api_key}, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception("dictionary lookup failed word=%s", word)
        raise

    if not resp.text.strip():
        # Merriam-Webster's API often returns HTTP 200 with an EMPTY body for an
        # invalid/inactive key, or a key registered for a different product
        # (Thesaurus, Medical, Spanish, Learner's, ...) rather than the
        # Collegiate Dictionary specifically -- surface that clearly instead of
        # letting resp.json() fail deep in a JSONDecodeError.
        logger.error(
            "dictionary lookup word=%s: empty response body (http status=%s) -- "
            "MERRIAM_WEBSTER_API_KEY is likely invalid, not yet active, or is a key "
            "for a different Merriam-Webster product (must be the Collegiate "
            "Dictionary API specifically)",
            word, resp.status_code,
        )
        raise RuntimeError(
            "Merriam-Webster API returned an empty response body. Check that "
            "MERRIAM_WEBSTER_API_KEY is a valid, active key for the Collegiate "
            "Dictionary API (not Thesaurus/Medical/Spanish/Learner's)."
        )

    try:
        entries = resp.json()
    except ValueError:
        logger.error("dictionary lookup word=%s: non-JSON response body: %r", word, resp.text[:300])
        raise RuntimeError(f"Merriam-Webster API returned a non-JSON response for {word!r}: {resp.text[:300]!r}")

    if not entries or not isinstance(entries[0], dict):
        logger.info("dictionary lookup: %s not recognized (no entry returned)", word)
        return None

    entry = entries[0]
    short_defs = entry.get("shortdef") or []

    result = {
        "word": word.strip().upper(),
        "part_of_speech": entry.get("fl"),
        "definition": _first_definition(entry),
        "short_definition": short_defs[0] if short_defs else None,
    }
    logger.info("dictionary lookup ok word=%s part_of_speech=%s", word, result["part_of_speech"])
    return result


def lookup_words(words: list[str], api_key: str | None = None) -> dict[str, dict]:
    """Look up multiple words. Returns {WORD: entry} for each word found; words that
    error out or aren't recognized are logged and simply omitted, not raised."""
    results: dict[str, dict] = {}
    if not (api_key or os.getenv("MERRIAM_WEBSTER_API_KEY") or "").strip():
        logger.warning("dictionary lookups skipped: MERRIAM_WEBSTER_API_KEY is not set")
        return results

    for word in words:
        try:
            entry = lookup_word(word, api_key=api_key)
        except Exception:
            logger.exception("dictionary lookup errored for word=%s; skipping", word)
            continue
        if entry:
            results[entry["word"]] = entry
        else:
            logger.warning("dictionary lookup: %s not recognized, skipping", word)
    return results
