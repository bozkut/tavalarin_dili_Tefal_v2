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
import cv2
import numpy as np
from PIL import Image, ImageDraw

from generate_letter_scratches import letter_contours_to_strokes, load_font, StrokeConfig

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
    "punctuation": list(".,;:!?'\"-+<>"),
    "arrows": ["→", "←"],
}


def skeletonize(binary: np.ndarray) -> np.ndarray:
    """Zhang-Suen thinning via OpenCV morphology.

    Repeatedly erodes and subtracts until only the medial axis remains.
    """
    skeleton = np.zeros_like(binary)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    temp = binary.copy()
    while True:
        eroded = cv2.erode(temp, element)
        dilated = cv2.dilate(eroded, element)
        diff = cv2.subtract(temp, dilated)
        skeleton = cv2.bitwise_or(skeleton, diff)
        temp = eroded.copy()
        if cv2.countNonZero(temp) == 0:
            break
    return skeleton


def thin_letter_contours(letter: str, font_size: int = 200, erosion: int = 3):
    """Extract hairline scratch-like contours via skeleton + thin dilation.

    Simple and clean approach:
    1. Render letter as filled white on black
    2. Skeletonize to get 1-pixel-wide medial axis
    3. Dilate with small ellipse kernel for thin tube
    4. Extract contours preserving holes
    """
    temp_size = StrokeConfig.TEMP_IMG_SIZE
    temp_img = Image.new("L", (temp_size, temp_size), color=0)
    temp_draw = ImageDraw.Draw(temp_img)

    font = load_font(font_size)
    bbox = temp_draw.textbbox((0, 0), letter, font=font)
    lw = bbox[2] - bbox[0]
    lh = bbox[3] - bbox[1]
    lx = (temp_size - lw) // 2
    ly = (temp_size - lh) // 2
    temp_draw.text((lx, ly), letter, fill=255, font=font)

    gray = np.array(temp_img)
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

    # Skeletonize: reduce to 1-pixel-wide medial axis
    skeleton = skeletonize(binary)

    # Dilate skeleton to create thin tube — 2 iterations for visible strokes
    tube_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    thin_img = cv2.dilate(skeleton, tube_kernel, iterations=2)

    # Extract contours preserving holes (O, 8, etc.)
    contours, _ = cv2.findContours(thin_img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    strokes = []
    for contour in contours:
        epsilon = 0.012 * cv2.arcLength(contour, True)
        simplified = cv2.approxPolyDP(contour, epsilon, True)

        stroke = []
        for point in simplified:
            x, y = point[0]
            stroke.append((float(x) / temp_size, float(y) / temp_size))

        if len(stroke) > 1:
            strokes.append(stroke)

    return strokes


@click.command()
@click.option("--output", default="output/glyph_library_complete.json", help="Output path")
@click.option("--font-size", default=200, help="Font size for contour extraction")
@click.option("--thin", is_flag=True, default=False,
              help="Use thin scratch-like extraction (skeleton + erosion)")
@click.option("--erosion", default=3, type=int,
              help="Erosion iterations for --thin mode (higher = thinner)")
def build_library(output: str, font_size: int, thin: bool, erosion: int):
    """Build complete glyph library from font contour extraction."""
    all_chars = []
    for group in TURKISH_CHARS.values():
        all_chars.extend(group)

    mode = "thin skeleton" if thin else "standard contour"
    logger.info(f"Building glyph library for {len(all_chars)} characters ({mode})...")

    glyphs = {}
    failed = []

    for char in all_chars:
        if thin:
            strokes = thin_letter_contours(char, font_size, erosion)
        else:
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
