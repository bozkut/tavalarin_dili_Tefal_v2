#!/usr/bin/env python
"""Generate SVG glyphs from normalized stroke data.

Reads glyph_library_final.json (with normalized 0-1 stroke coordinates)
and converts each glyph's strokes to SVG paths, scaled to UPM 1000.
"""

import json
from pathlib import Path
import click
import colorlog
from tqdm import tqdm

logger = colorlog.getLogger(__name__)
logger.setLevel("INFO")


def setup_logging():
    """Configure colorlog logging."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s[%(levelname)s]%(reset)s %(message)s",
            log_colors={"DEBUG": "cyan", "INFO": "green", "WARNING": "yellow", "ERROR": "red"},
        )
    )
    logger.addHandler(handler)


def normalize_to_upm(norm_point, upm=1000):
    """Convert normalized 0-1 coordinates to UPM units.

    Input: normalized 0-1 (0,0=top-left, 1,1=bottom-right)
    Output: UPM 1000 (0,700=top, 1000,0=bottom, centered at x=500)

    Formula:
    - upm_x = norm_x * 200 + 400 (maps 0-1 to 400-600, centered at 500)
    - upm_y = (1.0 - norm_y) * 900 + (-200) (inverts Y, scales to ascent/descent)
    """
    norm_x, norm_y = norm_point

    # Map x from 0-1 to 400-600 (centered at 500 in a 1000-unit glyph width)
    upm_x = norm_x * 200 + 400

    # Invert Y (flip vertically) and map from 0-1 to -200 to 700 (ascent to descent)
    # -200 is descent, 700 is cap_height
    upm_y = (1.0 - norm_y) * 900 + (-200)

    return [upm_x, upm_y]


def strokes_to_svg_path(strokes):
    """Convert list of strokes to SVG path data.

    Each stroke is a list of normalized points [norm_x, norm_y].
    Returns SVG path string with M (move) and L (line) commands.
    """
    if not strokes:
        return ""

    path_parts = []

    for stroke in strokes:
        if not stroke:
            continue

        # Start new subpath with Move command
        first_point = normalize_to_upm(stroke[0])
        path_parts.append(f"M {first_point[0]:.2f} {first_point[1]:.2f}")

        # Add line segments for remaining points
        for point in stroke[1:]:
            upm_point = normalize_to_upm(point)
            path_parts.append(f"L {upm_point[0]:.2f} {upm_point[1]:.2f}")

    return " ".join(path_parts)


def create_svg_glyph(char, unicode_hex, strokes):
    """Build complete SVG XML for a single glyph.

    Args:
        char: Character (e.g., 'A', '1')
        unicode_hex: Unicode value as hex string (e.g., '0041')
        strokes: List of strokes, each a list of [norm_x, norm_y] points

    Returns:
        SVG XML string
    """
    path_data = strokes_to_svg_path(strokes)

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 1000 1000"
     width="1000" height="1000">
  <defs>
    <style type="text/css">
      path {{ fill: none; stroke: black; stroke-width: 10; stroke-linecap: round; stroke-linejoin: round; }}
    </style>
  </defs>
  <!-- Glyph: U+{unicode_hex} ({char}) -->
  <path d="{path_data}" />
</svg>'''

    return svg


def generate_svg_from_library(library_path, output_dir):
    """Read glyph_library_final.json and generate SVG files.

    Args:
        library_path: Path to glyph_library_final.json
        output_dir: Directory to write SVG files (named U+XXXX.svg)
    """
    # Load library
    with open(library_path, 'r', encoding='utf-8') as f:
        library = json.load(f)

    metadata = library.get('metadata', {})
    glyphs = library.get('glyphs', {})

    logger.info(f"Loaded library: {metadata.get('total_glyphs', 0)} glyphs")
    logger.info(f"UPM: {metadata.get('upm', 1000)}")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_path.resolve()}")

    # Generate SVG for each glyph
    for char, glyph_data in tqdm(glyphs.items(), desc="Generating SVGs"):
        unicode_val = glyph_data.get('unicode')
        strokes = glyph_data.get('strokes', [])

        if unicode_val is None:
            logger.warning(f"Skipping '{char}': no unicode value")
            continue

        # Format unicode as hex (e.g., 65 -> "0041")
        unicode_hex = f"{unicode_val:04X}"
        svg_filename = f"U+{unicode_hex}.svg"
        svg_path = output_path / svg_filename

        # Create SVG content
        svg_content = create_svg_glyph(char, unicode_hex, strokes)

        # Write to file
        with open(svg_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)

        logger.debug(f"Generated {svg_filename} for '{char}'")

    logger.info(f"✓ Generated {len(glyphs)} SVG files")


@click.command()
@click.option(
    "--library",
    required=True,
    type=click.Path(exists=True),
    help="Path to glyph_library_final.json"
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Output directory for SVG files"
)
def generate_svg(library, output):
    """Convert normalized strokes to SVG glyphs."""
    setup_logging()
    generate_svg_from_library(library, output)
    logger.info("✓ SVG generation complete")


if __name__ == "__main__":
    generate_svg()
