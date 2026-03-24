#!/usr/bin/env python
"""
Render sample text using the generated TTF font and save as PNG.

Quick visual verification that glyphs look like organic scratches.

Usage:
    python preview_font.py --font output/ttf/TavaBeige-Regular.ttf
    python preview_font.py --font output/ttf/TavaBeige-Regular.ttf --text "TAVA" --size 120
"""

from pathlib import Path

import click
from PIL import Image, ImageDraw, ImageFont


SAMPLE_LINES = [
    "ABCÇDEFGĞ",
    "HIİJKLMNO",
    "ÖPRSŞTÜVYZ",
    "abcçdefgğhı",
    "ijklmnoöprs",
    "ştuüvyz",
    "0123456789",
    ".,;:!?'\"-",
]


@click.command()
@click.option("--font", "font_path", required=True, type=click.Path(exists=True),
              help="Path to TTF font file")
@click.option("--text", default=None, help="Custom text to render (overrides sample)")
@click.option("--size", default=72, type=int, help="Font size in points")
@click.option("--output", default="preview.png", help="Output PNG path")
def preview(font_path: str, text: str, size: int, output: str):
    """Render font preview as PNG image."""
    font = ImageFont.truetype(font_path, size)

    if text:
        lines = [text]
    else:
        lines = SAMPLE_LINES

    # Measure total dimensions
    line_height = int(size * 1.5)
    padding = 40
    max_width = 0

    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)

    for line in lines:
        bbox = dummy_draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        if w > max_width:
            max_width = w

    img_width = max_width + padding * 2
    img_height = line_height * len(lines) + padding * 2

    # Render
    img = Image.new("RGB", (img_width, img_height), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)

    y = padding
    for line in lines:
        draw.text((padding, y), line, fill=(220, 220, 210), font=font)
        y += line_height

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    click.echo(f"Preview saved to {out_path} ({img_width}x{img_height})")


if __name__ == "__main__":
    preview()
