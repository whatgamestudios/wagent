"""The service's daily scheduled job: build today's press release and email it out.

Invoked once a day (default: midnight UTC) by the Vercel Cron Job configured
in vercel.json — see the project README for how to change the time of day.
"""

from __future__ import annotations

import logging
from pathlib import Path

from worcadian_agent.agent import build_press_release
from worcadian_agent.email_sender import send_press_release_email

logger = logging.getLogger(__name__)

OUTPUT_DIR = "/tmp/output"


def daily_tasks(day: int | None = None) -> dict:
    """Build the press release for `day` (default: current game day) and email it."""
    logger.info("daily_tasks start day=%s", day)
    path = build_press_release(day=day, output_dir=OUTPUT_DIR)
    text = Path(path).read_text()
    recipients = send_press_release_email(text)
    logger.info("daily_tasks done day=%s path=%s recipients=%d", day, path, len(recipients))
    return {"game_day": day, "output_path": str(path), "recipients": recipients}
