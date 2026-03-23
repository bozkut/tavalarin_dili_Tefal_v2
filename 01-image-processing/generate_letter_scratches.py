#!/usr/bin/env python
"""
Generate synthetic pan images with letter-shaped scratches.

For each target character, creates a realistic-looking scratched pan
where the scratches form that character's shape.

IMPROVEMENT (v2.0): Replaces direct font text rendering with hand-drawn stroke simulation.
Previous approach (v1.0) used ImageFont.text() which produced printed letters that Claude's
vision model couldn't recognize as organic scratches (only 1/78 successful detections).

New approach:
  1. Extract letter contours from rendered glyphs using OpenCV
  2. Convert contours to stroke paths (list of connected points)
  3. Draw strokes with simulated hand-drawn imperfections:
     - Variable thickness via multiple overlapping passes with jitter
     - Organic feel mimicking real scratches on pan surface
  4. Improved background scratches:
     - Clustered patterns (3-6 clusters) instead of scattered random lines
     - Each cluster has 2-4 scratches at varied angles
     - Avoids accidentally forming letter-like V/N/X patterns
     - Subtle gray levels (50-100) to not interfere with character detection

This preserves realistic pan background while making character scratches more recognizable
as organic patterns rather than printed text.
"""

import random
import math
from pathlib import Path
from typing import List, Tuple

import click
import colorlog
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from tqdm import tqdm

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class PanConfig:
    """Configuration constants for pan rendering."""
    WIDTH = HEIGHT = 800
    RADIUS = 380
    CENTER_OFFSET = 15
    VIGNETTE_STEP = 20


class StrokeConfig:
    """Configuration constants for stroke rendering."""
    TEMP_IMG_SIZE = 400
    FONT_SIZE = 200
    DEFAULT_THICKNESS = 2
    BLUR_RADIUS = 0.5
    BLUR_RADIUS_SOFT = 0.3


class ColorConfig:
    """Configuration constants for colors."""
    PAN_BACKGROUND = (15, 15, 15)
    PAN_VIGNETTE = (5, 5, 5)
    LETTER_STROKE = (200, 200, 200)
    BG_SCRATCH_MIN = 50
    BG_SCRATCH_MAX = 100


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


# Initialize logger at module load
setup_logging()


def load_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load font with fallback chain (Windows → Linux → default)."""
    font_paths = [
        "C:\\Windows\\Fonts\\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, font_size)
        except (OSError, AttributeError):
            continue
    return ImageFont.load_default()


def create_pan_background(width: int = PanConfig.WIDTH, height: int = PanConfig.HEIGHT) -> Image.Image:
    """Create a realistic pan background with vignette."""
    # Create base image (black)
    img = Image.new("RGB", (width, height), color=ColorConfig.PAN_BACKGROUND)
    draw = ImageDraw.Draw(img)

    # Draw pan circle (dark gray/metallic)
    center_x, center_y = width // 2, height // 2
    pan_radius = PanConfig.RADIUS

    # Pan surface gradient effect: draw concentric circles
    for r in range(pan_radius, 0, -5):
        gray_level = 40 + (r // pan_radius) * 20
        draw.ellipse(
            [(center_x - r, center_y - r), (center_x + r, center_y + r)],
            fill=(gray_level, gray_level, gray_level),
        )

    # Add vignette (darker edges)
    vignette = Image.new("L", (width, height), 255)
    vignette_draw = ImageDraw.Draw(vignette)
    for r in range(pan_radius, min(width, height) // 2, PanConfig.VIGNETTE_STEP):
        alpha = max(0, 255 - (r - pan_radius) // 2)
        vignette_draw.ellipse(
            [(center_x - r, center_y - r), (center_x + r, center_y + r)],
            fill=alpha,
        )
    img = Image.composite(img, Image.new("RGB", (width, height), ColorConfig.PAN_VIGNETTE), vignette)

    return img


def letter_contours_to_strokes(letter: str, font_size: int = StrokeConfig.FONT_SIZE) -> List[List[Tuple[float, float]]]:
    """
    Extract contours from a rendered letter and convert to stroke paths.

    Returns a list of strokes, where each stroke is a list of (x, y) points
    normalized to [0, 1] range for later scaling.

    Falls back to empty list if CV2 is unavailable or extraction fails.
    """
    if not HAS_CV2:
        return []

    try:
        # Create temporary image to render letter
        temp_width, temp_height = StrokeConfig.TEMP_IMG_SIZE, StrokeConfig.TEMP_IMG_SIZE
        temp_img = Image.new("L", (temp_width, temp_height), color=0)
        temp_draw = ImageDraw.Draw(temp_img)

        # Load font with fallback chain
        font = load_font(font_size)

        # Render letter in white on black background
        bbox = temp_draw.textbbox((0, 0), letter, font=font)
        letter_width = bbox[2] - bbox[0]
        letter_height = bbox[3] - bbox[1]

        # Position letter centered
        letter_x = (temp_width - letter_width) // 2
        letter_y = (temp_height - letter_height) // 2

        temp_draw.text((letter_x, letter_y), letter, fill=255, font=font)

        # Convert PIL to OpenCV format
        cv_img = cv2.cvtColor(np.array(temp_img), cv2.COLOR_GRAY2BGR)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

        # Find contours
        contours, _ = cv2.findContours(gray, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        # Convert contours to stroke paths, normalized to [0, 1]
        strokes = []
        for contour in contours:
            # Simplify contour using Douglas-Peucker
            epsilon = 0.02 * cv2.arcLength(contour, True)
            simplified = cv2.approxPolyDP(contour, epsilon, True)

            # Convert to normalized points
            stroke = []
            for point in simplified:
                x, y = point[0]
                norm_x = float(x) / temp_width
                norm_y = float(y) / temp_height
                stroke.append((norm_x, norm_y))

            if len(stroke) > 1:
                strokes.append(stroke)

        return strokes

    except Exception as e:
        logger.warning(f"Could not extract contours for '{letter}': {e}")
        return []


def draw_strokes_with_imperfections(
    draw: ImageDraw.ImageDraw,
    strokes: List[List[Tuple[float, float]]],
    img_width: int,
    img_height: int,
    center_x: int,
    center_y: int,
    scale: float = 200,
    color: Tuple[int, int, int] = ColorConfig.LETTER_STROKE,
    thickness: int = StrokeConfig.DEFAULT_THICKNESS,
) -> None:
    """
    Draw strokes with hand-drawn imperfections to mimic organic scratches.

    Parameters:
    - draw: PIL ImageDraw object
    - strokes: list of strokes (each stroke is list of (x, y) normalized points)
    - img_width/img_height: image dimensions
    - center_x/center_y: center position for rendering
    - scale: scaling factor for normalized coordinates
    - color: RGB color for strokes
    - thickness: line thickness
    """
    if not strokes:
        return

    # Draw each stroke with variable thickness (multiple passes with jitter)
    for stroke in strokes:
        if len(stroke) < 2:
            continue

        # Convert normalized points to image coordinates
        points = []
        for norm_x, norm_y in stroke:
            x = center_x + (norm_x - 0.5) * scale
            y = center_y + (norm_y - 0.5) * scale
            points.append((x, y))

        # Draw multiple passes with slight jitter for hand-drawn effect
        for pass_num in range(2):
            jitter_x = random.uniform(-0.5, 0.5)
            jitter_y = random.uniform(-0.5, 0.5)

            # Vary thickness slightly
            line_thickness = max(1, thickness - pass_num)

            # Draw line with slight jitter
            jittered_points = [
                (p[0] + jitter_x, p[1] + jitter_y) for p in points
            ]

            for i in range(len(jittered_points) - 1):
                draw.line(
                    [jittered_points[i], jittered_points[i + 1]],
                    fill=color,
                    width=line_thickness,
                )


def add_background_scratches(img: Image.Image, count: int = 15) -> Image.Image:
    """
    Add clustered background scratches that avoid forming letter-like patterns.

    Instead of scattered random lines that might accidentally form V/N/X patterns,
    this creates 3-6 clusters of scratches with varying angles and positions.
    Each cluster has 2-4 scratches that branch naturally without forming obvious letters.

    Parameters:
    - img: image to modify
    - count: target number of scratches (distributed across clusters)
    """
    draw = ImageDraw.Draw(img)
    width, height = img.size
    center_x, center_y = width // 2, height // 2
    pan_radius = PanConfig.RADIUS

    # Create 3-6 clusters instead of random scattered scratches
    num_clusters = random.randint(3, 6)
    scratches_per_cluster = max(2, count // num_clusters)

    for cluster_idx in range(num_clusters):
        # Cluster center at random location within pan
        cluster_angle = random.uniform(0, 360)
        cluster_radius = random.uniform(50, pan_radius - 100)

        cluster_x = center_x + cluster_radius * math.cos(math.radians(cluster_angle))
        cluster_y = center_y + cluster_radius * math.sin(math.radians(cluster_angle))

        # Each cluster has 2-4 scratches branching from the center
        actual_scratches = random.randint(2, 4)

        for scratch_in_cluster in range(actual_scratches):
            # Angle varies significantly within cluster to avoid forming letters
            angle_offset = random.uniform(0, 360)

            # Scratch length varies
            scratch_length = random.uniform(30, 150)

            # End point from cluster center
            end_angle = cluster_angle + angle_offset
            end_x = cluster_x + scratch_length * math.cos(math.radians(end_angle))
            end_y = cluster_y + scratch_length * math.sin(math.radians(end_angle))

            # Keep scratches within pan bounds
            end_x = max(center_x - pan_radius, min(center_x + pan_radius, end_x))
            end_y = max(center_y - pan_radius, min(center_y + pan_radius, end_y))

            # Subtle gray levels to avoid interfering with character detection
            gray = random.randint(ColorConfig.BG_SCRATCH_MIN, ColorConfig.BG_SCRATCH_MAX)
            # Thin lines (1-2 pixels)
            line_width = random.randint(1, 2)

            draw.line([(cluster_x, cluster_y), (end_x, end_y)], fill=(gray, gray, gray), width=line_width)

    # Slight blur for soft, organic effect
    img = img.filter(ImageFilter.GaussianBlur(radius=StrokeConfig.BLUR_RADIUS_SOFT))
    return img


def draw_letter_scratches(img: Image.Image, letter: str) -> Image.Image:
    """
    Draw a letter as hand-drawn stroke scratches on the pan surface.

    Uses one of two strategies:
    1. (Preferred) Extract contours from rendered letter and draw with hand-drawn
       imperfections (requires OpenCV)
    2. (Fallback) Render letter using PIL font with slight opacity and softening
       to mimic scratches

    The goal is to create organic-looking scratches that Claude's vision model
    recognizes as natural pan surface patterns, not printed text.
    """
    draw = ImageDraw.Draw(img)
    width, height = img.size
    center_x, center_y = width // 2, height // 2

    # Try stroke-based rendering first (if OpenCV available)
    if HAS_CV2:
        try:
            strokes = letter_contours_to_strokes(letter, font_size=StrokeConfig.FONT_SIZE)

            if strokes:
                # Draw with hand-drawn imperfections
                # Use light gray - slightly brighter than background but not as stark as before
                draw_strokes_with_imperfections(
                    draw,
                    strokes,
                    width,
                    height,
                    center_x,
                    center_y,
                    scale=200,
                    color=ColorConfig.LETTER_STROKE,
                    thickness=StrokeConfig.DEFAULT_THICKNESS,
                )
                return img
        except Exception as e:
            logger.debug(f"Stroke rendering failed for '{letter}': {e}, falling back to font")

    # Fallback: render using PIL font with soft effect
    font_size = 280
    font = load_font(font_size)

    # Get letter bounding box
    bbox = draw.textbbox((0, 0), letter, font=font)
    letter_width = bbox[2] - bbox[0]
    letter_height = bbox[3] - bbox[1]

    # Position letter at center
    letter_x = center_x - letter_width // 2
    letter_y = center_y - letter_height // 2

    # Use light gray instead of bright white - looks more like organic scratches than printed text
    letter_color = ColorConfig.LETTER_STROKE

    # Draw with single pass (not multiple overlays) for softer appearance
    draw.text(
        (letter_x, letter_y),
        letter,
        fill=letter_color,
        font=font,
    )

    # Apply slight blur to soften hard edges and make it look more like a scratch
    img = img.filter(ImageFilter.GaussianBlur(radius=StrokeConfig.BLUR_RADIUS))

    return img


def char_to_filename(char: str) -> str:
    """Convert a character to a safe filename."""
    if char.isalnum():
        return char
    special_map = {
        "ç": "ccedil",
        "Ç": "Ccedil",
        "ğ": "gbreve",
        "Ğ": "Gbreve",
        "ı": "idotless",
        "İ": "Idotabove",
        "ö": "odiaeresis",
        "Ö": "Odiaeresis",
        "ş": "scedil",
        "Ş": "Scedil",
        "ü": "udiaeresis",
        "Ü": "Udiaeresis",
        ".": "dot",
        ",": "comma",
        ":": "colon",
        ";": "semicolon",
        "!": "exclaim",
        "?": "question",
        "'": "apostrophe",
        '"': "quotedbl",
        "-": "hyphen",
    }
    return special_map.get(char, f"char_{ord(char)}")


def generate_letter_image(char: str, output_dir: Path) -> bool:
    """Generate a single letter's synthetic pan image."""
    try:
        # Create pan background
        img = create_pan_background(800, 800)

        # Add clustered background scratches (3-6 clusters, 2-4 scratches per cluster)
        img = add_background_scratches(img, count=random.randint(10, 20))

        # Draw the letter as scratches
        img = draw_letter_scratches(img, char)

        # Save directly to output_dir (not in subdirectories)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"pan_{char_to_filename(char)}.jpg"
        img.save(output_path, quality=85)

        return True
    except Exception as e:
        logger.error(f"Failed to generate image for '{char}': {e}")
        return False


def get_character_list(chars: str) -> List[str]:
    """Convert character string to list of unique characters."""
    return list(dict.fromkeys(chars))  # Remove duplicates while preserving order


@click.command()
@click.option(
    "--chars",
    default="ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZabcçdefgğhıijklmnoöprsştuüvyz0123456789.,;:!?'\"-",
    help="Characters to generate (Turkish alphabet + digits + punctuation)",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Output directory for synthetic images",
)
@click.option(
    "--count",
    default=1,
    type=int,
    help="Number of variations per character (1-3 recommended)",
)
def generate_scratches(chars: str, output: str, count: int):
    """
    Generate synthetic pan images with letter-shaped scratches.

    For each character, creates a realistic-looking pan image where
    the scratches form that character's shape. Useful for generating
    training data when real pan photos don't cover all characters.
    """
    setup_logging()

    char_list = get_character_list(chars)
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating {len(char_list)} characters × {count} variation(s)...")

    success = 0
    total = len(char_list) * count

    for char in tqdm(char_list, desc="Generating characters"):
        for variation in range(count):
            if generate_letter_image(char, output_dir):
                success += 1

    logger.info(f"✓ Generated {success}/{total} images successfully")

    if success < total:
        exit(1)


if __name__ == "__main__":
    generate_scratches()
