#!/usr/bin/env python
"""Generate TTF font from SVG glyph files.

Reads SVG glyph files (from generate_svg.py) and creates a complete TTF font
using fontTools. Each SVG file represents one character with normalized stroke data
in UPM 1000 coordinates.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import click
import colorlog
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
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


def svg_path_to_contours(path_data: str) -> list[list[tuple[int, int]]]:
    """Convert SVG path data string to contour lists.

    Parses SVG path commands (M = moveto, L = lineto) and returns a list of contours.
    Each contour is a list of (x, y) integer coordinate tuples.

    Args:
        path_data: SVG path string (e.g., "M 100 200 L 150 250 M 300 400")

    Returns:
        List of contours, where each contour is a list of (x, y) tuples.
        Example: [[(100, 200), (150, 250)], [(300, 400)]]
    """
    if not path_data or not path_data.strip():
        return []

    contours = []
    current_contour = []

    # Parse path data using regex
    # Match both M/L commands with floating-point or integer coordinates
    pattern = r'([ML])\s+([\d.]+)\s+([\d.]+)'
    matches = re.findall(pattern, path_data)

    if not matches:
        return []

    for command, x_str, y_str in matches:
        x = int(float(x_str))
        y = int(float(y_str))

        if command == 'M':
            # Start new contour on moveto
            if current_contour:
                contours.append(current_contour)
            current_contour = [(x, y)]
        elif command == 'L':
            # Add point to current contour
            current_contour.append((x, y))

    # Add final contour
    if current_contour:
        contours.append(current_contour)

    return contours


def load_svg_glyph(svg_path: Path) -> list[list[tuple[int, int]]]:
    """Parse SVG file and extract glyph contours.

    Reads an SVG file and extracts the path data from the first <path> element.
    Returns the contours converted to (x, y) coordinate tuples.

    Args:
        svg_path: Path to SVG file

    Returns:
        List of contours (each contour is a list of (x, y) tuples)
    """
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()

        # Handle XML namespace
        ns = {'svg': 'http://www.w3.org/2000/svg'}

        # Find first path element
        path_elem = root.find('.//svg:path', ns)
        if path_elem is None:
            # Try without namespace
            path_elem = root.find('.//path')

        if path_elem is None:
            logger.warning(f"No path element found in {svg_path.name}")
            return []

        path_data = path_elem.get('d', '')
        if not path_data:
            logger.warning(f"No path data in {svg_path.name}")
            return []

        contours = svg_path_to_contours(path_data)
        return contours

    except Exception as e:
        logger.error(f"Error loading {svg_path.name}: {e}")
        return []


def create_glyph_set(glyphs_dir: Path) -> dict[str, list[list[tuple[int, int]]]]:
    """Load all SVG files from directory and create glyph set.

    Scans directory for SVG files matching pattern U+XXXX.svg (where XXXX is Unicode hex).
    Returns a dictionary mapping character strings to their contour data.

    Args:
        glyphs_dir: Path to directory containing SVG files

    Returns:
        Dictionary: {character_string: contour_list}
        Example: {"C": [[(100, 200), (150, 250)]], "P": [...]}
    """
    glyph_set = {}
    svg_files = sorted(glyphs_dir.glob("U+*.svg"))

    if not svg_files:
        logger.warning(f"No SVG files found in {glyphs_dir}")
        return {}

    for svg_path in tqdm(svg_files, desc="Loading glyphs"):
        # Extract Unicode from filename (U+XXXX.svg)
        filename = svg_path.stem  # "U+0043"
        unicode_hex = filename.replace("U+", "")

        try:
            unicode_val = int(unicode_hex, 16)
            char = chr(unicode_val)

            contours = load_svg_glyph(svg_path)
            if contours:
                glyph_set[char] = contours
                logger.debug(f"Loaded {filename} ({char})")
            else:
                logger.warning(f"No contours found in {filename}")

        except (ValueError, OverflowError) as e:
            logger.error(f"Invalid Unicode in {filename}: {e}")
            continue

    logger.info(f"✓ Loaded {len(glyph_set)} glyphs")
    return glyph_set


def build_font(glyph_set: dict[str, list[list[tuple[int, int]]]]) -> TTFont:
    """Build TTF font from glyph set using fontTools.

    Creates a complete font with metrics, character map, glyph outlines, and name table.

    Args:
        glyph_set: Dictionary mapping character strings to contour lists

    Returns:
        fontTools TTFont object
    """
    # Prepare glyph order (always start with .notdef)
    glyph_order = [".notdef"] + sorted(glyph_set.keys())

    # Create fontBuilder
    fb = FontBuilder(unitsPerEm=1000, isTTF=True)
    fb.setupGlyphOrder(glyph_order)

    # Convert contours to Glyph objects using TTGlyphPen
    glyphs_dict = {}

    # .notdef is empty glyph
    pen = TTGlyphPen(None)
    glyphs_dict[".notdef"] = pen.glyph()

    # Convert each glyph's contours to Glyph objects
    for char, contours in glyph_set.items():
        pen = TTGlyphPen(None)

        # Draw each contour
        for contour in contours:
            if not contour:
                continue

            # Start contour at first point
            pen.moveTo(contour[0])

            # Draw lines to remaining points
            for point in contour[1:]:
                pen.lineTo(point)

            # Close contour
            pen.closePath()

        glyphs_dict[char] = pen.glyph()

    # Setup glyphs with outlines
    fb.setupGlyf(glyphs_dict)

    # Setup character map (cmap)
    # Map Unicode values to glyph names
    cmap_dict = {ord(char): char for char in glyph_set.keys()}
    fb.setupCharacterMap(cmap_dict)

    # Setup horizontal metrics
    metrics_dict = {}
    for glyph_name in glyph_order:
        # Set advance width to 1000 (full width of UPM)
        # and left-side bearing to 0
        metrics_dict[glyph_name] = (1000, 0)
    fb.setupHorizontalMetrics(metrics_dict)

    # Setup horizontal header
    fb.setupHorizontalHeader(ascender=800, descender=-200)

    # Setup head table
    fb.setupHead(unitsPerEm=1000)

    # Setup name table
    name_strings = {
        "familyName": "Tava Beige",
        "styleName": "Regular",
        "uniqueFontIdentifier": "TavaBeige-Regular-1.0",
        "fullName": "Tava Beige Regular",
        "psName": "TavaBeige-Regular",
        "copyright": "Generated from Tefal pan scratch patterns",
        "version": "Version 1.0",
    }
    fb.setupNameTable(name_strings)

    # Setup OS/2 table
    fb.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
        sxHeight=500,
        sCapHeight=700,
        fsType=0  # Installable font
    )

    # Setup post table
    fb.setupPost()

    logger.info(f"✓ Font created with {len(glyph_set)} glyphs")

    return fb.font


def save_font(font: TTFont, output_path: Path) -> None:
    """Save TTFont to TTF file.

    Creates parent directories if needed and saves the font to disk.

    Args:
        font: fontTools TTFont object
        output_path: Path where TTF should be saved
    """
    output_path = Path(output_path)

    # Create parent directories
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save font
    try:
        font.save(output_path)
        logger.info(f"✓ Font saved to {output_path}")
    except Exception as e:
        logger.error(f"Error saving font: {e}")
        raise


@click.command()
@click.option(
    "--glyphs",
    required=True,
    type=click.Path(exists=True),
    help="Path to directory containing SVG glyph files"
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Path to output TTF file"
)
def create_font(glyphs, output):
    """Generate TTF font from SVG glyph files.

    Reads SVG files from GLYPHS directory and creates a TTF font at OUTPUT.
    """
    setup_logging()

    glyphs_dir = Path(glyphs)
    output_path = Path(output)

    logger.info(f"Loading glyphs from: {glyphs_dir.resolve()}")

    # Load glyphs from SVG files
    glyph_set = create_glyph_set(glyphs_dir)

    if not glyph_set:
        logger.error("No glyphs loaded, aborting")
        return

    # Build font
    font = build_font(glyph_set)

    # Save font
    save_font(font, output_path)

    logger.info("✓ Font generation complete")


if __name__ == "__main__":
    create_font()
