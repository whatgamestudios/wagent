"""Email the daily press release using Resend (https://resend.com).

Env vars:
    RESEND_API_KEY      required
    EMAIL_RECIPIENTS    required — comma-separated list of recipient addresses
    EMAIL_FROM          optional — defaults to Resend's shared test sender
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_FROM = "Worcadian Agent <onboarding@resend.dev>"


def _format_definitions_sections(definitions: dict[str, dict]) -> str:
    """Render each word's dictionary lookup as its own section of the email body."""
    sections = []
    for word, entry in definitions.items():
        lines = [f"--- {word} ---"]
        if entry.get("part_of_speech"):
            lines.append(f"Part of speech: {entry['part_of_speech']}")
        if entry.get("definition"):
            lines.append(f"Definition: {entry['definition']}")
        if entry.get("short_definition"):
            lines.append(f"Short definition: {entry['short_definition']}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def send_press_release_email(
    body: str,
    definitions: dict[str, dict] | None = None,
    subject: str | None = None,
) -> list[str]:
    """Send `body` as plain text to the recipients in EMAIL_RECIPIENTS, followed by
    one section per word in `definitions` (as returned by dictionary_client.lookup_words).
    Returns the recipient list."""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        logger.error("send_press_release_email: RESEND_API_KEY is not set")
        raise RuntimeError("RESEND_API_KEY is not set.")

    recipients_raw = os.getenv("EMAIL_RECIPIENTS")
    if not recipients_raw:
        logger.error("send_press_release_email: EMAIL_RECIPIENTS is not set")
        raise RuntimeError("EMAIL_RECIPIENTS is not set (comma-separated list of email addresses).")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    if not recipients:
        logger.error("send_press_release_email: EMAIL_RECIPIENTS had no valid addresses: %r", recipients_raw)
        raise RuntimeError("EMAIL_RECIPIENTS did not contain any valid addresses.")

    email_body = body
    if definitions:
        email_body = f"{body}\n\n\nWORD DEFINITIONS\n\n{_format_definitions_sections(definitions)}"

    import resend

    resend.api_key = api_key
    logger.info("sending press release email to %d recipient(s), %d word definition(s)", len(recipients), len(definitions or {}))
    try:
        resend.Emails.send(
            {
                "from": os.getenv("EMAIL_FROM", DEFAULT_FROM),
                "to": recipients,
                "subject": subject or "Worcadian Daily Press Release",
                "text": email_body,
            }
        )
    except Exception:
        logger.exception("resend.Emails.send failed")
        raise
    logger.info("email sent to %s", recipients)
    return recipients
