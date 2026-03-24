#!/usr/bin/env python
"""
Collect detected letter strokes from pan images into a glyph library.

Reads all *_detections.json files from find_letters_ai.py output,
validates that each detection matches its intended character,
and aggregates into a single glyph_library.json file ready for font generation.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any

import click
import colorlog

logger = colorlog.getLogger(__name__)
logger.setLevel("INFO")


def setup_logging():
    """Configure colored logging."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s[%(levelname)s]%(reset)s %(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
            },
        )
    )
    logger.addHandler(handler)


def filename_to_char(filename_stem: str) -> str:
    """Reverse mapping from filename back to original character."""
    special_map = {
        "ccedil": "ç",
        "Ccedil": "Ç",
        "gbreve": "ğ",
        "Gbreve": "Ğ",
        "idotless": "ı",
        "Idotabove": "İ",
        "odiaeresis": "ö",
        "Odiaeresis": "Ö",
        "scedil": "ş",
        "Scedil": "Ş",
        "udiaeresis": "ü",
        "Udiaeresis": "Ü",
        "dot": ".",
        "comma": ",",
        "colon": ":",
        "semicolon": ";",
        "exclaim": "!",
        "question": "?",
        "apostrophe": "'",
        "quotedbl": '"',
        "hyphen": "-",
    }

    # Remove "pan_" prefix and "_detections" suffix if present
    if filename_stem.startswith("pan_"):
        filename_stem = filename_stem[4:]

    if filename_stem in special_map:
        return special_map[filename_stem]
    elif len(filename_stem) == 1 and filename_stem.isalnum():
        return filename_stem
    else:
        logger.warning(f"Could not map filename '{filename_stem}' to character")
        return "?"


def char_to_unicode(char: str) -> int:
    """Get Unicode codepoint for a character."""
    return ord(char)


def collect_detections(
    detections_dir: Path, confidence_threshold: str = "low"
) -> Dict[str, Dict[str, Any]]:
    """
    Read all detection JSON files and aggregate into glyph library.

    Args:
        detections_dir: Directory containing *_detections.json files
        confidence_threshold: Minimum confidence level ("high", "medium", or "low")

    Returns:
        Dictionary mapping characters to glyph data
    """
    glyph_library = {}
    confidence_levels = {"low": 0, "medium": 1, "high": 2}
    min_confidence = confidence_levels.get(confidence_threshold, 0)

    json_files = sorted(detections_dir.glob("*_detections.json"))
    if not json_files:
        logger.warning(f"No detection files found in {detections_dir}")
        return glyph_library

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Expected target character from filename
            stem = json_file.stem.replace("_detections", "")
            target_char = filename_to_char(stem)

            letters = data.get("letters", [])
            if not letters:
                logger.warning(f"No letters detected in {json_file.name}")
                continue

            # Find the best matching detection (case-insensitive)
            best_match = None
            for letter_data in letters:
                detected_char = letter_data.get("letter", "?")
                confidence = letter_data.get("confidence", "low")
                confidence_value = confidence_levels.get(confidence, 0)

                # Case-insensitive match: pan_A detecting "a" should count
                if detected_char.lower() == target_char.lower() and confidence_value >= min_confidence:
                    if best_match is None or confidence_value > confidence_levels.get(
                        best_match.get("confidence", "low"), 0
                    ):
                        best_match = letter_data

            if best_match:
                char = target_char  # Use target char (from filename), not detected case
                glyph_library[char] = {
                    "letter": char,
                    "unicode": char_to_unicode(char),
                    "source_image": json_file.stem.replace("_detections", ".jpg"),
                    "confidence": best_match.get("confidence", "medium"),
                    "strokes": best_match.get("strokes", []),
                    "bbox": best_match.get("bbox", None),
                }
                logger.info(f"✓ Collected '{char}' (confidence: {best_match.get('confidence')})")
            else:
                logger.warning(
                    f"No match for target '{target_char}' in {json_file.name} (confidence threshold: {confidence_threshold})"
                )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse {json_file.name}: {e}")
        except Exception as e:
            logger.error(f"Error processing {json_file.name}: {e}")

    return glyph_library


def create_glyph_library_json(glyphs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Create the final glyph library JSON structure."""
    return {
        "metadata": {
            "upm": 1000,
            "ascent": 800,
            "descent": -200,
            "cap_height": 700,
            "x_height": 500,
            "total_glyphs": len(glyphs),
            "generated_from": "synthetic pan images + Claude Vision API",
        },
        "glyphs": glyphs,
    }


@click.command()
@click.option(
    "--detections",
    required=True,
    type=click.Path(exists=True),
    help="Directory containing detection JSON files from find_letters_ai.py",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Output path for glyph_library.json",
)
@click.option(
    "--confidence",
    default="low",
    type=click.Choice(["low", "medium", "high"]),
    help="Minimum confidence level to include",
)
def collect_glyphs(detections: str, output: str, confidence: str):
    """
    Collect detected letter strokes into a glyph library.

    Reads all *_detections.json files from find_letters_ai.py output,
    aggregates detections by character, and produces glyph_library.json
    with normalized stroke coordinates ready for font generation.
    """
    setup_logging()

    detections_dir = Path(detections)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Collecting detections from {detections_dir}...")
    glyphs = collect_detections(detections_dir, confidence)

    if not glyphs:
        logger.error("No glyphs collected. Exiting.")
        sys.exit(1)

    # Create final library structure
    library = create_glyph_library_json(glyphs)

    # Save
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(library, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Glyph library saved to {output_path}")
        logger.info(f"  Total glyphs: {library['metadata']['total_glyphs']}")
    except Exception as e:
        logger.error(f"Failed to save glyph library: {e}")
        sys.exit(1)


if __name__ == "__main__":
    collect_glyphs()
