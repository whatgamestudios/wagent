"""The service's daily scheduled job: build today's press release and email it out.

Invoked once a day (default: midnight UTC) by the Vercel Cron Job configured
in vercel.json — see the project README for how to change the time of day.
"""

from __future__ import annotations

import logging
from pathlib import Path

from worcadian_agent.agent import build_press_release, gather_facts
from worcadian_agent.dictionary_client import lookup_words
from worcadian_agent.email_sender import send_press_release_email

logger = logging.getLogger(__name__)

OUTPUT_DIR = "/tmp/output"


def daily_tasks(day: int | None = None) -> dict:
    """Gather today's facts, look up the seed word and notable words in the
    dictionary, build the press release, and email everything out."""
    logger.info("daily_tasks start day=%s", day)

    facts_bundle = gather_facts(day)
    words_to_look_up = [facts_bundle["seed_word"]] + [w["word"] for w in facts_bundle["notable_words"]]
    definitions = lookup_words(words_to_look_up)
    logger.info("looked up %d/%d word(s) in the dictionary", len(definitions), len(words_to_look_up))

    path = build_press_release(facts_bundle, output_dir=OUTPUT_DIR)
    text = Path(path).read_text()
    recipients = send_press_release_email(text, definitions=definitions)

    logger.info("daily_tasks done day=%s path=%s recipients=%d", day, path, len(recipients))
    return {
        "game_day": facts_bundle["game_day"],
        "output_path": str(path),
        "recipients": recipients,
        "definitions": definitions,
    }
