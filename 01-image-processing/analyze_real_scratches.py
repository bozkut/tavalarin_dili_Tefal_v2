#!/usr/bin/env python
"""
Analyze real pan scratch images to extract a distortion profile.

Processes photographs of scratched pans to measure real scratch
characteristics (direction, frequency, amplitude, density) and
outputs a scratch_profile.json that distort_strokes.py can use
to produce more authentic glyph distortion.

Pipeline:
  1. Claude Vision filters images for quality (single pan, close-up, visible scratches)
  2. OpenCV analyzes accepted images: edge detection, line detection, FFT
  3. Statistics are aggregated into a scratch profile JSON

Usage:
    python analyze_real_scratches.py \
        --input "../çizik tavalar-20260325T074554Z-3-001/çizik tavalar" \
        --output output/scratch_profile.json
"""

import base64
import json
import math
import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
import colorlog
import cv2
import numpy as np

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


# ---------------------------------------------------------------------------
# Step 1: Claude Vision quality filter
# ---------------------------------------------------------------------------

def filter_images_with_vision(image_paths: List[Path], min_score: int = 6) -> List[Tuple[Path, int]]:
    """Use Claude Vision to score each image for scratch analysis suitability.

    Returns list of (path, score) for images scoring >= min_score.
    Falls back to accepting all images if API key is unavailable.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Vision filter, using all images")
        return [(p, 7) for p in image_paths]

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        logger.warning("anthropic package not installed — skipping Vision filter")
        return [(p, 7) for p in image_paths]

    accepted = []
    for img_path in image_paths:
        try:
            with open(img_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")

            suffix = img_path.suffix.lower()
            media_type = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".bmp": "image/bmp",
            }.get(suffix, "image/png")

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": img_data},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Rate this image for pan scratch analysis on a 1-10 scale. "
                                "Criteria: (a) shows a SINGLE pan surface, (b) close-up view, "
                                "(c) scratches are clearly visible, (d) good focus/lighting. "
                                "Reply with ONLY a JSON object: {\"score\": N, \"reason\": \"...\"}"
                            ),
                        },
                    ],
                }],
            )

            text = response.content[0].text.strip()
            # Parse JSON from response
            if "{" in text:
                json_str = text[text.index("{"):text.rindex("}") + 1]
                result = json.loads(json_str)
                score = int(result.get("score", 0))
            else:
                score = 0

            if score >= min_score:
                accepted.append((img_path, score))
                logger.info(f"  ACCEPTED ({score}/10): {img_path.name}")
            else:
                reason = result.get("reason", "low score")
                logger.info(f"  REJECTED ({score}/10): {img_path.name} — {reason}")

        except Exception as e:
            logger.warning(f"  Vision error for {img_path.name}: {e} — accepting anyway")
            accepted.append((img_path, 5))

    return accepted


# ---------------------------------------------------------------------------
# Step 2: OpenCV scratch analysis
# ---------------------------------------------------------------------------

def analyze_single_image(img_path: Path) -> Optional[Dict]:
    """Extract scratch characteristics from a single pan image.

    Returns dict with: angles, lengths, edge_density, fft_dominant_freqs
    """
    # Use np.fromfile + imdecode to handle Unicode paths on Windows
    try:
        buf = np.fromfile(str(img_path), dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        img = None
    if img is None:
        logger.warning(f"Could not read {img_path.name}")
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # CLAHE for contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)

    # Canny edge detection
    median_val = int(np.median(blurred))
    lower = max(0, int(median_val * 0.5))
    upper = min(255, int(median_val * 1.5))
    edges = cv2.Canny(blurred, lower, upper)

    # Edge density: ratio of edge pixels to total pixels
    edge_density = float(np.count_nonzero(edges)) / (h * w)

    # Hough Line Transform — detect line segments
    min_line_length = int(min(h, w) * 0.05)
    max_line_gap = int(min(h, w) * 0.02)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=30,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )

    angles = []
    lengths = []

    if lines is not None:
        diag = math.hypot(h, w)
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx, dy = x2 - x1, y2 - y1
            angle = math.degrees(math.atan2(dy, dx)) % 180  # 0-180 range
            length = math.hypot(dx, dy) / diag  # normalized by image diagonal
            angles.append(angle)
            lengths.append(length)

    # FFT analysis on edge image for dominant spatial frequencies
    fft_freqs = extract_fft_frequencies(edges)

    return {
        "angles": angles,
        "lengths": lengths,
        "edge_density": edge_density,
        "fft_dominant_freqs": fft_freqs,
        "num_lines": len(angles),
        "image_size": (w, h),
    }


def extract_fft_frequencies(edges: np.ndarray) -> List[float]:
    """Extract dominant spatial frequencies from edge image using FFT.

    Returns top-4 normalized frequencies that characterize the scratch pattern.
    """
    # Resize to standard size for comparable frequency analysis
    target_size = 256
    resized = cv2.resize(edges, (target_size, target_size))

    # 2D FFT
    f_transform = np.fft.fft2(resized.astype(np.float32))
    f_shift = np.fft.fftshift(f_transform)
    magnitude = np.abs(f_shift)

    # Radial average of magnitude spectrum
    center = target_size // 2
    radial_profile = []
    max_radius = center
    for r in range(1, max_radius):
        # Create ring mask
        y, x = np.ogrid[-center:target_size - center, -center:target_size - center]
        ring = (x * x + y * y >= (r - 1) ** 2) & (x * x + y * y < r ** 2)
        ring_mean = float(np.mean(magnitude[ring])) if np.any(ring) else 0.0
        radial_profile.append(ring_mean)

    if not radial_profile:
        return [7.0, 16.0, 31.0, 64.0]

    profile = np.array(radial_profile)
    # Smooth the profile
    kernel_size = 5
    if len(profile) > kernel_size:
        kernel = np.ones(kernel_size) / kernel_size
        profile = np.convolve(profile, kernel, mode="same")

    # Find peaks (local maxima)
    peaks = []
    for i in range(1, len(profile) - 1):
        if profile[i] > profile[i - 1] and profile[i] > profile[i + 1]:
            peaks.append((profile[i], i))

    # Sort by magnitude, take top 4
    peaks.sort(reverse=True)
    top_freqs = [float(p[1]) for p in peaks[:4]]

    # Pad to 4 if fewer peaks found
    defaults = [7.0, 16.0, 31.0, 64.0]
    while len(top_freqs) < 4:
        top_freqs.append(defaults[len(top_freqs)])

    # Scale frequencies to match distort_strokes.py range (roughly 5-70)
    scale = 70.0 / max_radius
    return [round(f * scale, 1) for f in top_freqs]


# ---------------------------------------------------------------------------
# Step 3: Aggregate statistics into profile
# ---------------------------------------------------------------------------

def aggregate_profile(analyses: List[Dict]) -> Dict:
    """Combine per-image analyses into a single scratch profile."""
    all_angles = []
    all_lengths = []
    all_densities = []
    all_fft_freqs = []  # list of 4-element lists
    total_lines = 0

    for a in analyses:
        all_angles.extend(a["angles"])
        all_lengths.extend(a["lengths"])
        all_densities.append(a["edge_density"])
        all_fft_freqs.append(a["fft_dominant_freqs"])
        total_lines += a["num_lines"]

    # --- Angle analysis ---
    if all_angles:
        # Circular mean for angles (0-180 range)
        rads = [math.radians(2 * a) for a in all_angles]  # double to handle 0-180
        mean_sin = sum(math.sin(r) for r in rads) / len(rads)
        mean_cos = sum(math.cos(r) for r in rads) / len(rads)
        angle_bias = math.degrees(math.atan2(mean_sin, mean_cos)) / 2
        if angle_bias < 0:
            angle_bias += 180

        # Circular spread (angular standard deviation)
        R = math.hypot(mean_sin, mean_cos)
        angle_spread = math.degrees(math.sqrt(-2 * math.log(max(R, 1e-6)))) / 2
        angle_spread = min(angle_spread, 90.0)  # cap at 90 (uniform)
    else:
        angle_bias = 45.0
        angle_spread = 45.0

    # --- Length analysis ---
    if all_lengths:
        mean_length = float(np.mean(all_lengths))
    else:
        mean_length = 0.1

    # --- Density analysis ---
    mean_density = float(np.mean(all_densities)) if all_densities else 0.05

    # --- FFT frequencies: average across images ---
    if all_fft_freqs:
        avg_freqs = [
            round(float(np.mean([f[i] for f in all_fft_freqs])), 1)
            for i in range(4)
        ]
        # Compute weights from the frequency magnitudes (normalize to sum=1)
        # Higher frequencies get less weight naturally
        raw_weights = [1.0 / (1.0 + 0.03 * f) for f in avg_freqs]
        total_w = sum(raw_weights)
        freq_weights = [round(w / total_w, 3) for w in raw_weights]
    else:
        avg_freqs = [7.0, 16.0, 31.0, 64.0]
        freq_weights = [0.5, 0.3, 0.15, 0.05]

    # --- Map density to distortion parameters ---
    # Low density = subtle scratches, high density = rough surface
    # Map edge_density (typically 0.02-0.15) to roughness (0.5-2.5)
    roughness = np.clip(mean_density * 15.0, 0.5, 2.5)
    roughness = round(float(roughness), 2)

    # Amplitude: scales with density but capped for subtlety
    amplitude = np.clip(mean_density * 0.08, 0.002, 0.008)
    amplitude = round(float(amplitude), 4)

    # Jitter: proportional to amplitude
    jitter_sigma = round(amplitude * 0.25, 5)

    # Segment length: finer for denser scratches
    max_seg = np.clip(0.02 - mean_density * 0.05, 0.008, 0.018)
    max_seg = round(float(max_seg), 4)

    # Corner smoothing: more passes for subtler result
    corner_passes = 2 if roughness < 1.5 else 1

    return {
        "metadata": {
            "source_images": len(analyses),
            "total_lines_detected": total_lines,
            "mean_edge_density": round(mean_density, 4),
            "mean_scratch_length": round(mean_length, 4),
            "analysis_date": str(date.today()),
        },
        "profile": {
            "roughness": roughness,
            "amplitude": amplitude,
            "jitter_sigma": jitter_sigma,
            "dominant_frequencies": avg_freqs,
            "frequency_weights": freq_weights,
            "angle_bias": round(angle_bias, 1),
            "angle_spread": round(angle_spread, 1),
            "max_segment_length": max_seg,
            "corner_smoothing_passes": corner_passes,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--input", "input_dir", required=True, type=click.Path(exists=True),
              help="Directory of pan scratch images")
@click.option("--output", "output_path", required=True, type=click.Path(),
              help="Output scratch_profile.json path")
@click.option("--min-score", default=6, type=int,
              help="Minimum Vision quality score (1-10) to accept an image")
@click.option("--skip-vision", is_flag=True, default=False,
              help="Skip Claude Vision filtering, use all images")
def main(input_dir: str, output_path: str, min_score: int, skip_vision: bool):
    """Analyze real pan scratch images and produce a distortion profile."""
    setup_logging()

    input_path = Path(input_dir)
    extensions = {".png", ".jpg", ".jpeg", ".bmp"}
    image_paths = sorted([
        p for p in input_path.iterdir()
        if p.suffix.lower() in extensions
    ])

    if not image_paths:
        logger.error(f"No images found in {input_path}")
        raise SystemExit(1)

    logger.info(f"Found {len(image_paths)} images in {input_path}")

    # Step 1: Filter with Claude Vision
    if skip_vision:
        accepted = [(p, 7) for p in image_paths]
        logger.info("Skipping Vision filter — using all images")
    else:
        logger.info("Filtering images with Claude Vision...")
        accepted = filter_images_with_vision(image_paths, min_score=min_score)

    logger.info(f"Accepted {len(accepted)}/{len(image_paths)} images for analysis")

    if not accepted:
        logger.error("No images passed quality filter")
        raise SystemExit(1)

    # Step 2: OpenCV analysis
    logger.info("Analyzing scratch patterns with OpenCV...")
    analyses = []
    for img_path, score in accepted:
        result = analyze_single_image(img_path)
        if result:
            result["quality_score"] = score
            analyses.append(result)
            logger.info(
                f"  {img_path.name}: {result['num_lines']} lines, "
                f"density={result['edge_density']:.3f}"
            )

    if not analyses:
        logger.error("No images could be analyzed")
        raise SystemExit(1)

    # Step 3: Aggregate into profile
    logger.info("Aggregating scratch profile...")
    profile = aggregate_profile(analyses)

    # Add filtering metadata
    profile["metadata"]["total_source_images"] = len(image_paths)
    profile["metadata"]["accepted_images"] = len(accepted)

    # Save
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    logger.info(f"Scratch profile saved to {out}")
    logger.info(f"  roughness={profile['profile']['roughness']}")
    logger.info(f"  amplitude={profile['profile']['amplitude']}")
    logger.info(f"  frequencies={profile['profile']['dominant_frequencies']}")
    logger.info(f"  angle_bias={profile['profile']['angle_bias']}°")


if __name__ == "__main__":
    main()
