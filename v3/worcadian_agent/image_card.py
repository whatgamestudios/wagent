"""Render a word + meaning as an Instagram-ready graphic card.

No AI image generation involved: this composites the word and its meaning onto
a templated parchment/newspaper-style card using Pillow, matching the game's
press-release aesthetic. Defaults to a 1080x1080 square (Instagram feed); pass
--width/--height for other formats (e.g. 1080x1350 portrait).

Standalone usage:
    python -m worcadian_agent.image_card GROWTH "the process of increasing in size"
    python -m worcadian_agent.image_card ZYTHUM "an ancient Egyptian fermented beer" --output-dir output
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BACKGROUND = (242, 233, 216)  # parchment
INK = (43, 36, 32)  # near-black brown
ACCENT = (150, 104, 45)  # aged gold, used for rules/kicker/footer

# fonts/ ships DejaVu Serif regular/bold/italic (bundled in the repo -- see
# fonts/LICENSE) as the guaranteed final fallback: a serverless deployment
# (e.g. Vercel's Python runtime) has NO system fonts at all, so relying only
# on macOS's Georgia or a Linux distro's DejaVu package silently degraded to
# PIL's tiny fixed-size bitmap font in production, with every piece of text
# on the card collapsing to the same tiny size regardless of the sizing logic
# below -- this bundled copy means that can't happen regardless of host OS.
BUNDLED_FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Checked in order: an explicit --font-dir, then Georgia (macOS) or a Linux
# distro's DejaVu Serif package if either happens to be present, then the
# bundled copy above, which always exists.
_FONT_CANDIDATES = {
    "regular": [
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        str(BUNDLED_FONT_DIR / "regular.ttf"),
    ],
    "bold": [
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        str(BUNDLED_FONT_DIR / "bold.ttf"),
    ],
    "italic": [
        "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        str(BUNDLED_FONT_DIR / "italic.ttf"),
    ],
}

_warned_missing_font = False


def _find_font(style: str, font_dir: str | Path | None) -> str | None:
    if font_dir is not None:
        for name in (f"{style}.ttf", f"{style}.otf"):
            candidate = Path(font_dir) / name
            if candidate.exists():
                return str(candidate)
    for path in _FONT_CANDIDATES[style]:
        if Path(path).exists():
            return path
    return None


def _load_font(style: str, size: int, font_dir: str | Path | None) -> ImageFont.FreeTypeFont:
    path = _find_font(style, font_dir)
    if path is None:
        global _warned_missing_font
        if not _warned_missing_font:
            print(
                f"warning: no {style} TrueType font found; falling back to PIL's tiny "
                "built-in bitmap font. Pass --font-dir with regular.ttf/bold.ttf/italic.ttf "
                "for a legible card.",
                file=sys.stderr,
            )
            _warned_missing_font = True
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    style: str,
    max_width: int,
    font_dir: str | Path | None,
    start_size: int,
    min_size: int,
) -> ImageFont.FreeTypeFont:
    """Shrink font size (in steps of 4px) until `text` fits within `max_width`."""
    size = start_size
    font = _load_font(style, size, font_dir)
    while size > min_size and _text_width(draw, text, font) > max_width:
        size -= 4
        font = _load_font(style, size, font_dir)
    return font


def _wrap_to_width(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> list[str]:
    """Greedy word-wrap measured in rendered pixel width, not character count."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or _text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    style: str,
    max_width: int,
    max_height: float,
    font_dir: str | Path | None,
    max_size: int,
    min_size: int,
) -> tuple[ImageFont.FreeTypeFont, list[str], float]:
    """Find the largest font size (starting from `max_size`, shrinking as needed)
    whose wrapped block of `text` fits within max_height.

    `max_size` should be generous relative to the available box -- this only
    ever shrinks, never grows, so a `max_size` that's small relative to
    max_height leaves short text tiny with empty space below it rather than
    filling the space.
    """
    size = max_size
    while True:
        font = _load_font(style, size, font_dir)
        lines = _wrap_to_width(draw, text, font, max_width)
        line_height = draw.textbbox((0, 0), "Ag", font=font)[3] * 1.4
        if line_height * len(lines) <= max_height or size <= min_size:
            return font, lines, line_height
        size -= 2


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    canvas_width: int,
    tracking: int = 0,
) -> None:
    """Draw `text` horizontally centered at height `y`; `tracking` adds letter-spacing."""
    if tracking:
        widths = [_text_width(draw, ch, font) for ch in text]
        total_width = sum(widths) + tracking * (len(text) - 1)
        x = (canvas_width - total_width) / 2
        for ch, w in zip(text, widths):
            draw.text((x, y), ch, font=font, fill=fill)
            x += w + tracking
    else:
        width = _text_width(draw, text, font)
        draw.text(((canvas_width - width) / 2, y), text, font=font, fill=fill)


def _render_card_image(
    word: str,
    meaning: str,
    part_of_speech: str | None = None,
    width: int = 1080,
    height: int = 1080,
    font_dir: str | Path | None = None,
    kicker: str = "WORCADIAN · WORD OF THE DAY",
    footer: str | None = None,
) -> Image.Image:
    """Render `word` (and optional `part_of_speech`) and `meaning` onto a parchment card."""
    img = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(img)

    margin = round(width * 0.09)
    inner_margin = margin + round(width * 0.02)
    content_width = width - 2 * inner_margin

    draw.rectangle([margin, margin, width - margin, height - margin], outline=ACCENT, width=3)
    draw.rectangle(
        [margin + 10, margin + 10, width - margin - 10, height - margin - 10],
        outline=ACCENT,
        width=1,
    )

    y = margin + round(height * 0.07)

    kicker_font = _load_font("regular", round(width * 0.024), font_dir)
    _draw_centered(draw, y, kicker, kicker_font, ACCENT, width, tracking=round(width * 0.006))
    y += round(height * 0.05)

    draw.line([(width / 2 - 60, y), (width / 2 + 60, y)], fill=ACCENT, width=2)
    y += round(height * 0.055)

    word_text = word.strip().upper()
#    word_font = _fit_font(
#        draw, word_text, "bold", content_width, font_dir,
#        start_size=round(width * 0.5), min_size=round(width * 0.2),
#    )
    word_font = _fit_font(
        draw, word_text, "bold", content_width, font_dir,
        start_size=round(width * 0.16), min_size=round(width * 0.05),
    )
    word_height = draw.textbbox((0, 0), word_text, font=word_font)[3]
    _draw_centered(draw, y, word_text, word_font, INK, width)
    y += word_height + round(height * 0.025)

    if part_of_speech:
        pos_text = part_of_speech.strip().lower()
        pos_font = _load_font("italic", round(width * 0.028), font_dir)
        pos_height = draw.textbbox((0, 0), pos_text, font=pos_font)[3]
        _draw_centered(draw, y, pos_text, pos_font, ACCENT, width)
        y += pos_height + round(height * 0.03)
    else:
        y += round(height * 0.025)

    draw.line([(width / 2 - 40, y), (width / 2 + 40, y)], fill=ACCENT, width=2)
    y += round(height * 0.055)

    footer_text = footer or f"worcadian · {date.today():%B %d, %Y}"
    footer_font = _load_font("regular", round(width * 0.02), font_dir)
    footer_y = height - margin - round(height * 0.06)

    available_height = footer_y - round(height * 0.03) - y
    meaning_font, meaning_lines, line_height = _fit_wrapped_text(
        draw, meaning.strip(), "italic", content_width, available_height, font_dir,
        max_size=round(width * 0.075), min_size=round(width * 0.022),
    )
    # Center the wrapped block within the available space rather than pinning it
    # to the top -- otherwise short definitions leave all the leftover room as
    # dead space below the text instead of it being distributed evenly.
    block_height = line_height * len(meaning_lines)
    text_y = y + max(0, (available_height - block_height) / 2)
    for line in meaning_lines:
        _draw_centered(draw, text_y, line, meaning_font, INK, width)
        text_y += line_height

    _draw_centered(draw, footer_y, footer_text, footer_font, ACCENT, width, tracking=round(width * 0.003))

    return img


def generate_word_card(
    word: str,
    meaning: str,
    output_path: str | Path,
    part_of_speech: str | None = None,
    width: int = 1080,
    height: int = 1080,
    font_dir: str | Path | None = None,
    kicker: str = "WORCADIAN · WORD OF THE DAY",
    footer: str | None = None,
) -> Path:
    """Render `word` and `meaning` onto a parchment card and save it as a PNG file."""
    img = _render_card_image(
        word, meaning, part_of_speech=part_of_speech, width=width, height=height,
        font_dir=font_dir, kicker=kicker, footer=footer,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def generate_word_card_bytes(
    word: str,
    meaning: str,
    part_of_speech: str | None = None,
    width: int = 1080,
    height: int = 1080,
    font_dir: str | Path | None = None,
    kicker: str = "WORCADIAN · WORD OF THE DAY",
    footer: str | None = None,
) -> bytes:
    """Render `word` and `meaning` onto a parchment card and return it as PNG bytes,
    without touching disk -- for serverless callers that embed the image directly
    in an API response (e.g. as a data: URI) rather than persisting a file."""
    img = _render_card_image(
        word, meaning, part_of_speech=part_of_speech, width=width, height=height,
        font_dir=font_dir, kicker=kicker, footer=footer,
    )
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("word", help="The word to feature")
    parser.add_argument("meaning", help="A short definition/meaning of the word")
    parser.add_argument("--part-of-speech", default=None, help="e.g. noun, verb -- shown under the word")
    parser.add_argument("--output-dir", default="output", help="Where to write the PNG (default: output)")
    parser.add_argument("--output", default=None, help="Explicit output file path (overrides --output-dir)")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument(
        "--font-dir", default=None,
        help="Directory with regular.ttf/bold.ttf/italic.ttf to use instead of system fonts",
    )
    parser.add_argument("--kicker", default="WORCADIAN · WORD OF THE DAY")
    parser.add_argument("--footer", default=None, help="Override the footer text (default: today's date)")
    args = parser.parse_args()

    if args.output:
        out_path = Path(args.output)
    else:
        filename = f"{args.word.strip().upper()}-{date.today().isoformat()}.png"
        out_path = Path(args.output_dir) / filename

    path = generate_word_card(
        args.word,
        args.meaning,
        out_path,
        part_of_speech=args.part_of_speech,
        width=args.width,
        height=args.height,
        font_dir=args.font_dir,
        kicker=args.kicker,
        footer=args.footer,
    )
    print(f"Wrote {path}")


if __name__ == "__main__":
    _main()
