#!/usr/bin/env python
"""Export TTF font to WOFF2 web font format.

Reads an existing TTF file and converts it to WOFF2 using fontTools'
built-in Brotli compression support. Logs compression statistics
(original size, compressed size, and reduction percentage).
"""

import sys
from pathlib import Path

import click
import colorlog

# Import compress here so tests can patch 'export_webfont.compress'
try:
    from fontTools.ttLib.woff2 import compress
except ImportError:
    compress = None  # Handled at runtime in export_woff2

logger = colorlog.getLogger(__name__)
logger.setLevel("INFO")


def setup_logging() -> None:
    """Configure colorlog logging."""
    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return
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


def get_file_size_kb(path: Path) -> float:
    """Return the size of a file in kilobytes.

    Args:
        path: Path to the file.

    Returns:
        File size in KB as a float.
    """
    return Path(path).stat().st_size / 1024.0


def export_woff2(input_path: Path, output_path: Path) -> None:
    """Convert a TTF font file to WOFF2 format.

    Reads the TTF at *input_path*, compresses it with Brotli via
    fontTools, and writes the WOFF2 to *output_path*.  Logs the
    original and compressed file sizes plus the reduction percentage.

    Args:
        input_path: Path to the source TTF file.
        output_path: Destination path for the WOFF2 file.

    Exits:
        sys.exit(1) on missing input file, missing brotli package, or
        any compression error.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    # --- guard: input must exist ---
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    # --- guard: brotli / compress must be available ---
    if compress is None:
        logger.error(
            "fontTools WOFF2 support is unavailable. "
            "Run: pip install brotli"
        )
        sys.exit(1)

    # Log input info
    input_size_kb = get_file_size_kb(input_path)
    logger.info(f"Input:  {input_path.name}  ({input_size_kb:.1f} KB)")

    # Create output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # --- compress ---
    try:
        compress(str(input_path), str(output_path))
    except Exception as exc:
        logger.error(f"Conversion failed: {exc}")
        sys.exit(1)

    # Log output info and compression ratio
    output_size_kb = get_file_size_kb(output_path)
    if input_size_kb > 0:
        reduction_pct = (1.0 - output_size_kb / input_size_kb) * 100.0
    else:
        reduction_pct = 0.0

    logger.info(f"Output: {output_path.name}  ({output_size_kb:.1f} KB)")
    logger.info(
        f"Compression: {input_size_kb:.1f} KB → {output_size_kb:.1f} KB "
        f"({reduction_pct:.1f}% reduction)"
    )


@click.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(),
    help="Path to input TTF file",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(),
    help="Path to output WOFF2 file",
)
def main(input_path: str, output_path: str) -> None:
    """Convert a TTF font to WOFF2 (Brotli-compressed web font)."""
    setup_logging()
    export_woff2(Path(input_path), Path(output_path))
    logger.info("Done.")


if __name__ == "__main__":
    main()
