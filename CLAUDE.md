# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tavaların Dili** ("Language of Pans") — a creative font system built from Tefal pan surface scratch patterns. The project is a 4-stage pipeline that generates a full TTF/WOFF2 font supporting the Turkish alphabet (77 glyphs total).

## Development Setup

**Python environment:**
```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

## Pipeline Stages & Commands

Each stage feeds into the next. Run in order:

**Stage 0 — Data Collection:**
```bash
cd 00-data-collection
python scrape_pan_images.py --queries "tefal pan scratches" --limit 100 --output ./images
```

**Stage 1 — Image Processing & Glyph Library:**
```bash
cd 01-image-processing
# Generate synthetic pan images with letter-shaped scratches
python generate_letter_scratches.py --output ./output/synthetic_improved --count 77

# Build glyph library from font contour extraction (no API needed)
python build_glyph_library.py --output output/glyph_library_complete.json

# Apply organic scratch distortion to make glyphs look hand-scratched
python distort_strokes.py --input output/glyph_library_complete.json \
                          --output output/glyph_library_scratchy.json \
                          --seed 42 --roughness 2.5
```

Optional (requires ANTHROPIC_API_KEY):
```bash
# AI-based letter detection in pan images (Claude Vision API)
python find_letters_ai.py --input ./output/synthetic_improved --output ./output/synthetic_detections
python collect_glyphs.py --detections output/synthetic_detections --output output/glyph_library_ai.json
python merge_glyph_libraries.py --libraries output/glyph_library_ai.json output/glyph_library_complete.json \
                                --output output/glyph_library_merged.json
```

**Stage 2 — Font Generation:**
```bash
cd 03-font-generation
python generate_svg.py --library ../01-image-processing/output/glyph_library_scratchy.json \
                       --output ./input/glyphs
python create_font.py --glyphs ./input/glyphs --output ./output/ttf/TavaBeige-Regular.ttf
python export_webfont.py --input ./output/ttf/TavaBeige-Regular.ttf \
                         --output ./output/woff/TavaBeige-Regular.woff2
python preview_font.py --font output/ttf/TavaBeige-Regular.ttf --output preview.png
```

## Architecture

### Data Flow
```
Font Rendering → build_glyph_library.py → distort_strokes.py
    → generate_svg.py → create_font.py → export_webfont.py → TTF/WOFF2
```

### Key Data Formats
- **`glyph_library_complete.json`** — clean contour data for all 77 characters (from build_glyph_library.py)
- **`glyph_library_scratchy.json`** — organically distorted strokes (from distort_strokes.py)
- Each stage reads from and writes to sibling `output/` subdirectories

### Python Scripts (Stages 0, 1, 2)
All scripts use the Click CLI framework with tqdm progress bars and colorlog logging.

**Stage 0:** `scrape_pan_images.py` — Bing Image Search scraper with retry logic and magic byte validation.

**Stage 1:**
- `generate_letter_scratches.py` — generates synthetic pan images with hand-drawn stroke simulation (OpenCV contour extraction + Douglas-Peucker simplification + PIL rendering with jitter)
- `build_glyph_library.py` — extracts letter contours from font rendering, normalizes to 0-1 coordinates
- `distort_strokes.py` — applies organic scratch distortion (subdivide → smooth noise displacement → corner softening → micro-jitter)
- `find_letters_ai.py` — (optional) Claude Vision API letter detection
- `collect_glyphs.py` — aggregates AI detections into glyph library
- `merge_glyph_libraries.py` — merges multiple glyph libraries

**Stage 2:**
- `generate_svg.py` — converts normalized strokes to SVG paths in UPM 1000 coordinates
- `create_font.py` — builds TTF from SVG glyphs using fontTools/FontBuilder
- `export_webfont.py` — compresses TTF to WOFF2 via Brotli
- `preview_font.py` — renders sample text as PNG for visual verification

### Font Specifications
Built with fontTools/fontBuilder:
- UPM: 1000, Ascent: 800, Descent: -200, Cap height: 700, X-height: 500
- Character set: Turkish 29-letter alphabet (uppercase + lowercase) + digits 0–9 + 9 punctuation marks = 77 glyphs
- Output formats: TTF, WOFF2 (Brotli-compressed)
- PostScript glyph names for Turkish chars (e.g., Ğ → Gbreve, ş → scedilla)
