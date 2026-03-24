#!/usr/bin/env python
"""
Build a complete glyph library for all 77 Turkish characters.

Uses OpenCV contour extraction from rendered glyphs (same method as
generate_letter_scratches.py) to produce normalized stroke data.
No API calls needed.
"""

import json
from pathlib import Path

import click
import colorlog

from generate_letter_scratches import letter_contours_to_strokes

logger = colorlog.getLogger(__name__)
logger.setLevel("INFO")
handler = colorlog.StreamHandler()
handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s[%(levelname)s]%(reset)s %(message)s",
        log_colors={"DEBUG": "cyan", "INFO": "green", "WARNING": "yellow", "ERROR": "red"},
    )
)
logger.addHandler(handler)

# Full Turkish character set (77 glyphs)
TURKISH_CHARS = {
    "uppercase": list("ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"),
    "lowercase": list("abcçdefgğhıijklmnoöprsştuüvyz"),
    "digits": list("0123456789"),
    "punctuation": list(".,;:!?'\"-"),
}


@click.command()
@click.option("--output", default="output/glyph_library_complete.json", help="Output path")
@click.option("--font-size", default=200, help="Font size for contour extraction")
def build_library(output: str, font_size: int):
    """Build complete glyph library from font contour extraction."""
    all_chars = []
    for group in TURKISH_CHARS.values():
        all_chars.extend(group)

    logger.info(f"Building glyph library for {len(all_chars)} characters...")

    glyphs = {}
    failed = []

    for char in all_chars:
        strokes = letter_contours_to_strokes(char, font_size)
        if strokes:
            # Convert tuples to lists for JSON serialization
            json_strokes = [[list(pt) for pt in stroke] for stroke in strokes]
            glyphs[char] = {
                "letter": char,
                "unicode": ord(char),
                "source": "contour_extraction",
                "confidence": "high",
                "strokes": json_strokes,
            }
            logger.info(f"✓ '{char}' — {len(strokes)} strokes, {sum(len(s) for s in strokes)} points")
        else:
            failed.append(char)
            logger.warning(f"✗ '{char}' — no strokes extracted")

    library = {
        "metadata": {
            "upm": 1000,
            "ascent": 800,
            "descent": -200,
            "cap_height": 700,
            "x_height": 500,
            "total_glyphs": len(glyphs),
            "generated_from": "contour extraction (OpenCV + font rendering)",
        },
        "glyphs": glyphs,
    }

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

    logger.info(f"✓ Saved {len(glyphs)}/{len(all_chars)} glyphs to {output_path}")
    if failed:
        logger.warning(f"Failed: {failed}")


if __name__ == "__main__":
    build_library()
