#!/usr/bin/env python
"""
Apply organic scratch-like distortion to clean glyph contours.

Transforms the precise geometric outlines from build_glyph_library.py
into rough, hand-scratched-looking strokes suitable for the Tava font.

Distortion effects:
  1. Subdivide long segments for finer control
  2. Smooth perpendicular displacement using layered sine waves
  3. Corner softening to remove geometric precision
  4. Per-point micro-jitter for grain texture

Usage:
    python distort_strokes.py --input output/glyph_library_complete.json \
                              --output output/glyph_library_scratchy.json \
                              --seed 42 --roughness 1.0
"""

import json
import math
import random
from pathlib import Path
from typing import List, Tuple

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


Point = List[float]
Stroke = List[Point]


def subdivide_stroke(stroke: Stroke, max_seg_len: float = 0.015) -> Stroke:
    """Insert points along long segments so distortion is smooth."""
    if len(stroke) < 2:
        return stroke

    result = [stroke[0]]
    for i in range(1, len(stroke)):
        p0 = result[-1]
        p1 = stroke[i]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        seg_len = math.hypot(dx, dy)

        if seg_len > max_seg_len:
            n_sub = int(math.ceil(seg_len / max_seg_len))
            for j in range(1, n_sub):
                t = j / n_sub
                result.append([p0[0] + dx * t, p0[1] + dy * t])

        result.append(list(p1))

    return result


def smooth_noise(arc_pos: float, seed_offset: float) -> float:
    """Generate smooth organic noise from layered sine waves.

    Uses 4 sine waves at different frequencies/phases to create
    natural-looking displacement that varies smoothly along the contour.
    """
    val = 0.0
    # Layer 1: broad undulation
    val += 0.5 * math.sin(arc_pos * 7.3 + seed_offset * 1.1)
    # Layer 2: medium variation
    val += 0.3 * math.sin(arc_pos * 15.7 + seed_offset * 2.3)
    # Layer 3: fine detail
    val += 0.15 * math.sin(arc_pos * 31.1 + seed_offset * 3.7)
    # Layer 4: micro texture
    val += 0.05 * math.sin(arc_pos * 63.9 + seed_offset * 5.1)
    return val


def distort_stroke(stroke: Stroke, roughness: float, rng: random.Random,
                   seed_offset: float) -> Stroke:
    """Apply organic distortion to a single stroke/contour.

    Steps:
      1. Compute cumulative arc length for smooth noise parameterization
      2. At each point, compute perpendicular direction to local contour
      3. Displace point perpendicular to contour by smooth noise amount
      4. Add small random micro-jitter for grain
    """
    if len(stroke) < 3:
        return stroke

    # Compute cumulative arc lengths
    arc_lengths = [0.0]
    for i in range(1, len(stroke)):
        dx = stroke[i][0] - stroke[i - 1][0]
        dy = stroke[i][1] - stroke[i - 1][1]
        arc_lengths.append(arc_lengths[-1] + math.hypot(dx, dy))

    total_arc = arc_lengths[-1]
    if total_arc < 1e-6:
        return stroke

    # Displacement amplitude scales with roughness
    amplitude = 0.006 * roughness
    jitter_sigma = 0.0015 * roughness

    result = []
    for i, pt in enumerate(stroke):
        # Normalized position along contour [0, total_arc]
        arc_pos = arc_lengths[i]

        # Compute local tangent direction
        if i == 0:
            tx = stroke[1][0] - stroke[0][0]
            ty = stroke[1][1] - stroke[0][1]
        elif i == len(stroke) - 1:
            tx = stroke[-1][0] - stroke[-2][0]
            ty = stroke[-1][1] - stroke[-2][1]
        else:
            tx = stroke[i + 1][0] - stroke[i - 1][0]
            ty = stroke[i + 1][1] - stroke[i - 1][1]

        t_len = math.hypot(tx, ty)
        if t_len < 1e-8:
            result.append(list(pt))
            continue

        # Perpendicular direction (normal)
        nx = -ty / t_len
        ny = tx / t_len

        # Smooth displacement along perpendicular
        displacement = smooth_noise(arc_pos, seed_offset) * amplitude

        # Add micro-jitter for grain texture
        jx = rng.gauss(0, jitter_sigma)
        jy = rng.gauss(0, jitter_sigma)

        new_x = pt[0] + nx * displacement + jx
        new_y = pt[1] + ny * displacement + jy

        result.append([new_x, new_y])

    return result


def smooth_corners(stroke: Stroke, passes: int = 1) -> Stroke:
    """Soften sharp corners by averaging with neighbors."""
    if len(stroke) < 3:
        return stroke

    for _ in range(passes):
        smoothed = [stroke[0]]
        for i in range(1, len(stroke) - 1):
            sx = 0.25 * stroke[i - 1][0] + 0.5 * stroke[i][0] + 0.25 * stroke[i + 1][0]
            sy = 0.25 * stroke[i - 1][1] + 0.5 * stroke[i][1] + 0.25 * stroke[i + 1][1]
            smoothed.append([sx, sy])
        smoothed.append(stroke[-1])
        stroke = smoothed

    return stroke


def distort_glyph(strokes: List[Stroke], roughness: float,
                  rng: random.Random) -> List[Stroke]:
    """Apply full distortion pipeline to all strokes of a glyph."""
    result = []
    for i, stroke in enumerate(strokes):
        seed_offset = rng.random() * 100.0

        # 1. Subdivide for finer control
        s = subdivide_stroke(stroke, max_seg_len=0.012)

        # 2. Smooth corner averaging
        s = smooth_corners(s, passes=1)

        # 3. Organic displacement + micro-jitter
        s = distort_stroke(s, roughness, rng, seed_offset)

        if len(s) >= 2:
            result.append(s)

    return result


@click.command()
@click.option("--input", "input_path", required=True, type=click.Path(exists=True),
              help="Input glyph_library JSON")
@click.option("--output", "output_path", required=True, type=click.Path(),
              help="Output distorted glyph_library JSON")
@click.option("--seed", default=42, type=int, help="Random seed for reproducibility")
@click.option("--roughness", default=1.0, type=float,
              help="Distortion intensity (0=clean, 1=default, 2=very rough)")
def main(input_path: str, output_path: str, seed: int, roughness: float):
    """Apply organic scratch distortion to glyph library."""
    setup_logging()

    with open(input_path, "r", encoding="utf-8") as f:
        library = json.load(f)

    glyphs = library.get("glyphs", {})
    rng = random.Random(seed)
    distorted_count = 0

    for char, glyph_data in glyphs.items():
        strokes = glyph_data.get("strokes", [])
        if not strokes:
            continue

        glyph_data["strokes"] = distort_glyph(strokes, roughness, rng)
        glyph_data["source"] = "contour_extraction+distortion"
        distorted_count += 1

    library["metadata"]["generated_from"] = (
        f"contour extraction + organic distortion (roughness={roughness}, seed={seed})"
    )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

    logger.info(f"Distorted {distorted_count}/{len(glyphs)} glyphs (roughness={roughness})")
    logger.info(f"Saved to {out}")


if __name__ == "__main__":
    main()
