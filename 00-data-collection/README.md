# Stage 0: Data Collection - Web Scraper

This directory contains the web scraper for downloading real pan images from Bing Image Search to complement synthetic glyph generation.

## Files

- **scrape_pan_images.py** - Main scraper script using Click CLI
- **requirements.txt** - Python dependencies

## Usage

### Installation

```bash
pip install -r requirements.txt
```

### Basic Usage

```bash
python scrape_pan_images.py \
  --queries "tefal pan scratches,scratched non-stick pan" \
  --limit 30 \
  --output ./images
```

### Options

- `--queries TEXT` - Comma-separated search queries (default: "tefal pan scratches,scratched non-stick pan,pan surface damage,tefal cookware wear")
- `--limit INT` - Images per query (default: 30)
- `--output PATH` - Output directory for images (required)

## Features

- **Multiple Queries**: Search with 4 different queries to capture diverse scratch patterns
- **Robust URL Extraction**: Parses Bing's HTML response with fallback patterns
- **Download Validation**: 
  - Magic byte validation (JPEG/PNG) to filter corrupted files
  - GIF support
  - Retry logic with exponential backoff (3 attempts)
- **Rate Limiting**: 0.5s delay between requests to be respectful to servers
- **Progress Tracking**: 
  - tqdm progress bars for downloads
  - Colored logging (colorlog) for status and debugging
- **Filename Convention**: `{query_slug}_{index:04d}.jpg`
  - Example: `tefal_pan_scratches_0000.jpg`

## Performance

Downloaded 85 images from real sources:
- tefal_pan_scratches: 20 images
- scratched_non-stick_pan: 24 images  
- pan_surface_damage: 18 images
- tefal_cookware_wear: 23 images

Total size: ~25 MB of valid JPEG images

## Design Decisions

1. **Bing over Google**: Bing Image Search is more suitable for this use case as it returns actual image URLs (vs Google's base64 encoded thumbnails)

2. **HTML Parsing instead of API**: Bing doesn't have a public image search API. HTML parsing is more reliable than Selenium since images are embedded in the HTML response.

3. **Permissive URL Filtering**: Extracts all potential image URLs and filters by:
   - Domain whitelist (common image CDNs)
   - File extension (.jpg, .jpeg, .png, .gif, .webp)
   - URL length validation
   - Excludes analytics and tracking parameters

4. **Magic Byte Validation**: Validates at least 3 bytes (for JPEG) or 8 bytes (for PNG/GIF) before saving, avoiding corrupted files

5. **Exponential Backoff**: 1s, 2s, 4s delays between retries to handle temporary network issues

## Next Steps

These downloaded images should be combined with synthetic glyph images from Stage 1 to provide better training data for the letter detection model. The real-world scratch patterns will help the model generalize better than synthetic-only training.

## Troubleshooting

- **No images downloading**: Bing's HTML structure may have changed. Check if the regex patterns in `get_image_urls_from_bing()` still work
- **Rate limiting issues**: Increase the `time.sleep(0.5)` value in `scrape_query()`
- **Redirect or auth errors**: Some image sources may have CSRF protection. Try increasing the timeout or user-agent rotation
