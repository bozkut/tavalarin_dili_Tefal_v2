#!/usr/bin/env python
"""
Pan Image Letter Detection via Claude Vision API

Analyzes pan scratch patterns and identifies letter shapes (A-Z, a-z) formed by the scratches.
Combines multiple scratches to form letters. Returns annotated images with colored stroke overlays
and JSON detection data.
"""

import json
import sys
from pathlib import Path
from base64 import b64encode

import click
import colorlog
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm
import anthropic

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


def encode_image_to_base64(image_path: str) -> str:
    """Encode image to base64 for Claude API."""
    with open(image_path, "rb") as f:
        return b64encode(f.read()).decode("utf-8")


def detect_letters_in_image(
    image_path: str, client: anthropic.Anthropic, model: str
) -> dict | None:
    """
    Send image to Claude Vision API and detect letters in scratch patterns.
    Returns parsed JSON response with letters and stroke coordinates.
    """
    try:
        image_data = encode_image_to_base64(image_path)

        prompt = """You are looking at a scratched non-stick pan. Your job is to find scratch patterns that resemble letters of the alphabet.

Rules:
1. Find up to 3 scratches that most resemble a letter (A–Z or a–z). You do NOT need to find all — quality over quantity.
2. Only include letters you are reasonably confident about.
3. For each match, provide the bounding box of the scratch area, and draw the letter as clean handwritten strokes POSITIONED within that bounding box. Do NOT trace the scratch exactly — write the letter cleanly as a human would, placed over the scratch location.

Respond ONLY with JSON:
{
  "letters": [
    {
      "letter": "r",
      "confidence": "high",
      "bbox": [x1, y1, x2, y2],
      "strokes": [
        [[x1,y1], [x2,y2], [x3,y3]],
        [[x4,y4], [x5,y5]]
      ]
    }
  ]
}

All coordinates are normalized 0.0–1.0 (relative to image width/height).
bbox is [left, top, right, bottom].
strokes are clean letter paths inside the bbox. Each stroke should have 2–6 points max.
If no letter-like scratches found, return: {"letters": []}"""

        message = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        response_text = message.content[0].text

        # Markdown code fence'i sil (```json ... ```)
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        response_json = json.loads(response_text)
        return response_json

    except anthropic.APIError as e:
        logger.error(f"API error processing {Path(image_path).name}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse response as JSON from {Path(image_path).name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error processing {Path(image_path).name}: {e}")
        return None


def hex_to_rgb(color_name: str) -> tuple:
    """Convert color name to RGB tuple."""
    colors = {
        "cyan": (0, 255, 255),
        "red": (255, 50, 50),
        "green": (50, 255, 50),
        "yellow": (255, 255, 0),
        "blue": (50, 150, 255),
        "magenta": (255, 0, 255),
        "white": (255, 255, 255),
    }
    return colors.get(color_name.lower(), (0, 255, 255))


def annotate_image(
    image_path: str,
    detection_data: dict,
    output_image_path: str,
    color: str = "cyan",
) -> bool:
    """
    Draw annotation strokes on the image and save.
    Returns True if successful, False otherwise.
    """
    try:
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        width, height = img.size
        rgb_color = hex_to_rgb(color)

        letters = detection_data.get("letters", [])
        if not letters:
            logger.info(f"  No letters found in {Path(image_path).name}")
            img.save(output_image_path)
            return True

        # Draw strokes
        for letter_data in letters:
            letter_char = letter_data.get("letter", "?")
            strokes = letter_data.get("strokes", [])
            bbox = letter_data.get("bbox", None)

            # Draw all strokes for this letter with THICKER lines
            all_points = []
            for stroke in strokes:
                # Convert normalized (0-1) to pixel coordinates
                pixel_points = [
                    (int(x * width), int(y * height)) for x, y in stroke
                ]
                all_points.extend(pixel_points)

                # Draw the stroke as a thick line (6px instead of 3px)
                if len(pixel_points) > 1:
                    draw.line(pixel_points, fill=rgb_color, width=6)

            # Draw letter label at the center of bounding box (or centroid if no bbox)
            label_x, label_y = None, None

            if bbox:
                # bbox = [left, top, right, bottom] in normalized coords
                bbox_pixel = [
                    int(bbox[0] * width),
                    int(bbox[1] * height),
                    int(bbox[2] * width),
                    int(bbox[3] * height),
                ]
                label_x = (bbox_pixel[0] + bbox_pixel[2]) // 2
                label_y = (bbox_pixel[1] + bbox_pixel[3]) // 2
            elif all_points:
                label_x = sum(p[0] for p in all_points) // len(all_points)
                label_y = sum(p[1] for p in all_points) // len(all_points)

            if label_x is not None and label_y is not None:
                # Try to use a larger font; fall back to default if not available
                try:
                    font = ImageFont.truetype(
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36
                    )
                except (OSError, AttributeError):
                    try:
                        # Windows path
                        font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 36)
                    except (OSError, AttributeError):
                        font = ImageFont.load_default()

                # Draw the letter character with white shadow for readability
                shadow_offset = 2
                draw.text(
                    (label_x - shadow_offset, label_y - shadow_offset),
                    letter_char,
                    fill=(0, 0, 0),
                    font=font,
                    anchor="mm",
                )
                # Draw the letter in the chosen color on top
                draw.text(
                    (label_x, label_y),
                    letter_char,
                    fill=rgb_color,
                    font=font,
                    anchor="mm",
                )

        img.save(output_image_path)
        logger.info(f"  Annotated image saved to {Path(output_image_path).name}")
        return True

    except Exception as e:
        logger.error(f"Failed to annotate {Path(image_path).name}: {e}")
        return False


def process_image(
    image_path: str,
    output_dir: Path,
    client: anthropic.Anthropic,
    model: str,
    color: str,
) -> bool:
    """Process a single image and save outputs."""
    stem = Path(image_path).stem

    logger.info(f"Processing {Path(image_path).name}...")

    # Call Claude Vision API
    detection_data = detect_letters_in_image(image_path, client, model)
    if detection_data is None:
        return False

    # Save detection JSON
    json_output = output_dir / f"{stem}_detections.json"
    try:
        with open(json_output, "w") as f:
            json.dump(detection_data, f, indent=2)
        logger.info(f"  Detection data saved to {json_output.name}")
    except Exception as e:
        logger.error(f"Failed to save detection JSON for {stem}: {e}")
        return False

    # Annotate image
    img_output = output_dir / f"{stem}_letters.jpg"
    if not annotate_image(image_path, detection_data, str(img_output), color):
        return False

    # Log found letters
    letters = detection_data.get("letters", [])
    if letters:
        letter_chars = [l.get("letter", "?") for l in letters]
        logger.info(f"  Found letters: {', '.join(letter_chars)}")

    return True


def get_image_files(path: str) -> list:
    """Get list of image files from a file or directory."""
    p = Path(path)

    if p.is_file():
        if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp"]:
            return [str(p)]
        else:
            raise click.BadParameter(f"File {p} is not a supported image format")

    elif p.is_dir():
        images = list(p.glob("*.jpg")) + list(p.glob("*.jpeg")) + list(p.glob("*.png"))
        if not images:
            raise click.BadParameter(f"No images found in directory {p}")
        return [str(img) for img in sorted(images)]

    else:
        raise click.BadParameter(f"Path {p} does not exist")


@click.command()
@click.option(
    "--input",
    required=True,
    type=click.Path(exists=True),
    help="Input image file or directory of images",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Output directory for annotated images and JSON files",
)
@click.option(
    "--model",
    default="claude-opus-4-6",
    help="Claude model to use for vision analysis",
)
@click.option(
    "--color",
    default="cyan",
    type=click.Choice(["cyan", "red", "green", "yellow", "blue", "magenta", "white"]),
    help="Color for annotation strokes",
)
@click.option(
    "--workers",
    default=1,
    type=int,
    help="Number of parallel workers (caution: API rate limits)",
)
def find_letters(input: str, output: str, model: str, color: str, workers: int):
    """
    Detect letter shapes in pan scratch patterns using Claude Vision API.

    Analyzes pan images to find letter shapes (A-Z, a-z) formed by scratches.
    Combines multiple scratches to form letters. Returns annotated images with
    colored stroke overlays and JSON detection data.
    """
    setup_logging()

    # Get image files
    try:
        image_files = get_image_files(input)
    except click.BadParameter as e:
        logger.error(str(e))
        sys.exit(1)

    # Create output directory
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")

    # Initialize Anthropic client
    try:
        client = anthropic.Anthropic()
    except anthropic.APIConnectionError:
        logger.error("Failed to connect to Anthropic API. Check ANTHROPIC_API_KEY.")
        sys.exit(1)

    # Process images
    logger.info(f"Processing {len(image_files)} image(s) with {model}...")
    success_count = 0

    for image_path in tqdm(image_files, desc="Processing images"):
        if process_image(image_path, output_dir, client, model, color):
            success_count += 1

    logger.info(f"✓ Completed: {success_count}/{len(image_files)} images processed successfully")

    if success_count < len(image_files):
        sys.exit(1)


if __name__ == "__main__":
    find_letters()
