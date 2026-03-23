#!/usr/bin/env python
"""Merge synthetic + real glyph libraries, preferring real."""

import json
from pathlib import Path
import click
import colorlog

logger = colorlog.getLogger(__name__)
logger.setLevel("INFO")

def setup_logging():
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s[%(levelname)s]%(reset)s %(message)s",
            log_colors={"DEBUG": "cyan", "INFO": "green", "WARNING": "yellow", "ERROR": "red"},
        )
    )
    logger.addHandler(handler)

@click.command()
@click.option("--real", required=True, type=click.Path(exists=True))
@click.option("--synthetic", required=True, type=click.Path(exists=True))
@click.option("--output", required=True, type=click.Path())
def merge_libraries(real: str, synthetic: str, output: str):
    """Merge real and synthetic libraries, preferring real."""
    setup_logging()

    with open(real) as f:
        real_lib = json.load(f)
    with open(synthetic) as f:
        synth_lib = json.load(f)

    # Start with synthetic
    merged = synth_lib.copy()
    merged["glyphs"] = synth_lib.get("glyphs", {}).copy()

    # Overlay real (takes precedence)
    for char, glyph_data in real_lib.get("glyphs", {}).items():
        merged["glyphs"][char] = glyph_data
        logger.info(f"✓ Using real detection for '{char}'")

    # Update metadata
    merged["metadata"]["total_glyphs"] = len(merged["glyphs"])
    merged["metadata"]["source"] = "real (preferred) + synthetic (fallback)"

    with open(output, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    logger.info(f"✓ Merged library: {merged['metadata']['total_glyphs']} glyphs")

if __name__ == "__main__":
    merge_libraries()
