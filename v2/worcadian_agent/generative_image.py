"""Generate a representative AI illustration for a word using Gemini's image model.

Unlike image_card.py (a templated parchment/newspaper card), this calls Google
AI Studio's Gemini image-generation model via the Gemini API to generate a
genuine illustrative image from the word and its meaning. Requires a Google AI
Studio API key (free tier available at https://aistudio.google.com/apikey).

Env vars:
    GOOGLE_API_KEY      Google AI Studio API key (required)
    GOOGLE_IMAGE_MODEL  overrides the default image-generation model

Standalone usage:
    python -m worcadian_agent.generative_image GROWTH "the process of increasing in size"
    python -m worcadian_agent.generative_image ZYTHUM "an ancient Egyptian fermented beverage" --aspect-ratio 3:4
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "gemini-3.1-flash-image"
DEFAULT_STYLE = "warm, painterly editorial illustration with a rich color palette"

# Matches google.genai.types.ImageConfig.aspect_ratio's supported values.
VALID_ASPECT_RATIOS = {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"}


def _build_prompt(word: str, meaning: str, style: str) -> str:
    return (
        f'A single striking illustration representing the concept behind the word "{word.strip()}", '
        f"whose meaning is: {meaning.strip()}. Symbolic and evocative rather than literal, suitable "
        f"as an artistic Instagram post. Style: {style}. "
        "Do not include any text, letters, numbers, or watermarks anywhere in the image."
    )


def generate_ai_image(
    word: str,
    meaning: str,
    output_path: str | Path,
    model: str | None = None,
    aspect_ratio: str = "1:1",
    style: str = DEFAULT_STYLE,
    api_key: str | None = None,
) -> Path:
    """Call Google's Imagen model to generate a representative image and save it as a PNG."""
    if aspect_ratio not in VALID_ASPECT_RATIOS:
        raise ValueError(f"aspect_ratio must be one of {sorted(VALID_ASPECT_RATIOS)}, got {aspect_ratio!r}")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "The 'google-genai' package is required for AI image generation. Install it with:\n"
            "    pip install google-genai"
        ) from exc

    api_key = api_key or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Get a Google AI Studio API key from "
            "https://aistudio.google.com/apikey and add it to your .env file."
        )

    model = model or os.getenv("GOOGLE_IMAGE_MODEL") or DEFAULT_MODEL
    prompt = _build_prompt(word, meaning, style)

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        ),
    )

    image_bytes = next(
        (part.inline_data.data for part in response.parts if part.inline_data),
        None,
    )
    if image_bytes is None:
        raise RuntimeError("Imagen returned no image (the prompt may have been filtered/blocked).")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    return output_path


def _main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("word", help="The word to illustrate")
    parser.add_argument("meaning", help="A short definition/meaning of the word")
    parser.add_argument("--output-dir", default="output", help="Where to write the PNG (default: output)")
    parser.add_argument("--output", default=None, help="Explicit output file path (overrides --output-dir)")
    parser.add_argument("--model", default=None, help=f"Imagen model id (default: {DEFAULT_MODEL})")
    parser.add_argument("--aspect-ratio", default="1:1", choices=sorted(VALID_ASPECT_RATIOS))
    parser.add_argument("--style", default=DEFAULT_STYLE, help="Art-direction hint appended to the prompt")
    args = parser.parse_args()

    if args.output:
        out_path = Path(args.output)
    else:
        filename = f"{args.word.strip().upper()}-{date.today().isoformat()}-ai.png"
        out_path = Path(args.output_dir) / filename

    path = generate_ai_image(
        args.word,
        args.meaning,
        out_path,
        model=args.model,
        aspect_ratio=args.aspect_ratio,
        style=args.style,
    )
    print(f"Wrote {path}")


if __name__ == "__main__":
    _main()
