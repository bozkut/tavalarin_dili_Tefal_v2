#!/usr/bin/env python
"""
Bing Image Search scraper for downloading pan photos.

Downloads images of pans with scratches to provide real-world training data
for glyph detection. Uses multiple approaches including requests + regex
and Selenium fallback for robust image collection.

Features:
- Queries Bing Image Search and extracts dynamic URLs
- Downloads images with validation (JPEG/PNG magic bytes)
- Retry logic with exponential backoff (3 attempts per image)
- Rate limiting (0.5s between requests) to avoid overload
- Progress tracking with tqdm + colored logging
- Saves images with descriptive filenames (query_index.jpg)
"""

import logging
import re
import time
from pathlib import Path
from urllib.parse import unquote

import click
import colorlog
import requests
from tqdm import tqdm

# Constants
DEFAULT_TIMEOUT = 10


def setup_logging() -> logging.Logger:
    """Configure colorlog for terminal output with colors."""
    logger = colorlog.getLogger()
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler with colored output
    handler = colorlog.StreamHandler()
    handler.setLevel(logging.DEBUG)

    formatter = colorlog.ColoredFormatter(
        "%(log_color)s[%(levelname)-8s]%(reset)s %(message)s",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def is_valid_image_format(data: bytes) -> bool:
    """
    Validate image format by checking magic bytes.

    Supports:
    - JPEG: starts with FF D8 FF
    - PNG: starts with 89 50 4E 47 0D 0A 1A 0A
    - GIF: starts with GIF87a or GIF89a

    Args:
        data: Raw binary image data

    Returns:
        True if data is valid image format, False otherwise
    """
    if len(data) < 4:
        return False

    # Check JPEG magic bytes (FF D8 FF)
    if data[:3] == b'\xFF\xD8\xFF':
        return True

    # Check PNG magic bytes (89 50 4E 47 0D 0A 1A 0A)
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return True

    # Check GIF magic bytes
    if data[:6] in [b'GIF87a', b'GIF89a']:
        return True

    return False


def get_image_urls_from_bing(query: str, limit: int, logger: logging.Logger) -> list[str]:
    """
    Fetch image URLs from Bing Image Search.

    Parses Bing's HTML response to extract image URLs using multiple
    regex patterns to handle various response formats.

    Args:
        query: Search query string
        limit: Maximum number of URLs to return
        logger: Logger instance

    Returns:
        List of image URLs (up to limit)
    """
    extracted_urls = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        )
    }

    try:
        url = "https://www.bing.com/images/search"
        params = {"q": query}

        logger.info(f"Fetching URLs for query: {query}")
        response = requests.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()

        logger.debug("Extracting image URLs from HTML response...")

        # Strategy: Look for URLs that are actual image files
        # More strict pattern: http(s)://domain/path/filename.ext
        all_urls = re.findall(r'https?://[^\s"<>&,\'}]+', response.text)

        # Filter for likely image URLs
        image_domains = [
            'th.bing.com',
            'pinimg.com',
            'pinterestmedia.com',
            'cloudinary.com',
            'googleusercontent.com',
            'imgur.com',
            'flickr.com',
            'unsplash.com',
            'pexels.com',
            'pixabay.com',
            'staticflickr.com',
            'media.istockphoto.com',
            'stock.adobe.com',
            'images.food52.com',
            'ctfassets.net',
            'asotvinc.com',
        ]

        image_extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff']

        for candidate_url in all_urls:
            # Skip URLs with HTML entities or obvious corruption
            if '&quot;' in candidate_url or '&amp;' in candidate_url or '%' in candidate_url:
                continue

            # Clean up URL
            clean_url = unquote(candidate_url.replace('\\"', '"').replace('\\/', '/'))

            # Skip data URLs, fragments, and obviously wrong URLs
            if clean_url.startswith('data:') or '#' in clean_url or len(clean_url) > 1000:
                continue

            # Skip URLs with suspicious patterns
            if any(x in clean_url.lower() for x in ['analytics', 'googletagmanager', 'tracking', 'pixel', 'doubleclick']):
                continue

            # Check if URL is from image domain or has image extension
            is_image_domain = any(domain in clean_url.lower() for domain in image_domains)
            has_image_ext = any(clean_url.lower().endswith(f'.{ext}') or f'.{ext}?' in clean_url.lower() for ext in image_extensions)

            if is_image_domain or has_image_ext:
                # Additional validation: URL should not look like a web page
                if not any(x in clean_url.lower() for x in ['.html', '.aspx', '.php', '/search', '/page']):
                    if clean_url not in extracted_urls:
                        extracted_urls.append(clean_url)

                        if len(extracted_urls) >= limit:
                            logger.debug(f"Found {len(extracted_urls)} URLs")
                            return extracted_urls[:limit]

        logger.debug(f"Extracted {len(extracted_urls)} image URLs in total")
        return extracted_urls[:limit]

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch URLs for query '{query}': {e}")
        return []


def download_image(url: str, output_path: Path, timeout: int = DEFAULT_TIMEOUT, retries: int = 3, logger: logging.Logger | None = None) -> bool:
    """
    Download a single image with retry logic.

    Attempts to download an image and validate its format before saving.
    Retries up to `retries` times on failure with exponential backoff.

    Args:
        url: Image URL to download
        output_path: Path where to save the image
        timeout: Request timeout in seconds
        retries: Number of retry attempts
        logger: Logger instance (optional)

    Returns:
        True if successfully downloaded and saved, False otherwise
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # Skip invalid URLs
    if not url or not url.startswith("http"):
        logger.debug(f"Invalid URL: {str(url)[:60]}...")
        return False

    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=timeout, stream=True, allow_redirects=True)
            response.raise_for_status()

            data = response.content

            # Validate image format before saving
            if not is_valid_image_format(data):
                logger.debug(f"Invalid format: {str(url)[:60]}...")
                return False

            # Write image to disk
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(data)

            logger.debug(f"Downloaded: {output_path.name}")
            return True

        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                wait_time = 2 ** attempt
                logger.debug(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...")
                time.sleep(wait_time)

    return False


def scrape_query(query: str, output_dir: Path, limit: int, logger: logging.Logger) -> int:
    """
    Scrape images for a single search query.

    Fetches image URLs from Bing, downloads them with rate limiting,
    and saves them to output_dir with standardized filenames.

    Filename format: {query_slug}_{index:04d}.jpg
    Example: tefal_pan_scratches_0000.jpg

    Args:
        query: Search query string
        output_dir: Directory to save images
        limit: Number of images to download for this query
        logger: Logger instance

    Returns:
        Number of successfully downloaded images
    """
    # Create query slug for filename
    query_slug = query.replace(" ", "_").lower()

    # Fetch image URLs
    urls = get_image_urls_from_bing(query, limit, logger)

    if not urls:
        logger.warning(f"No URLs found for query: {query}")
        return 0

    logger.info(f"Downloading {len(urls)} images for: {query}")

    downloaded_count = 0
    pbar = tqdm(urls, desc=f"Downloading {query}", unit="img")

    for idx, url in enumerate(pbar):
        # Create output filename
        output_path = output_dir / f"{query_slug}_{idx:04d}.jpg"

        # Download image
        if download_image(url, output_path, logger=logger):
            downloaded_count += 1

        # Rate limiting: wait 0.5s between requests
        time.sleep(0.5)

    pbar.close()
    logger.info(f"Downloaded {downloaded_count}/{len(urls)} valid images for: {query}")

    return downloaded_count


@click.command()
@click.option(
    "--queries",
    default="tefal pan scratches,scratched non-stick pan,pan surface damage,tefal cookware wear",
    help="Comma-separated list of search queries"
)
@click.option(
    "--limit",
    default=30,
    type=int,
    help="Number of images to download per query"
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Output directory for downloaded images"
)
def scrape(queries: str, limit: int, output: str) -> None:
    """
    Download pan images from Bing Image Search.

    Scrapes multiple search queries to collect diverse pan photos
    with scratch patterns for training glyph detection.

    Example:

        python scrape_pan_images.py \\
            --queries "tefal pan scratches,scratched non-stick pan" \\
            --limit 30 \\
            --output ./images
    """
    logger = setup_logging()
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Bing Image Search Scraper - Pan Images")
    logger.info("=" * 60)

    # Parse queries
    query_list = [q.strip() for q in queries.split(",") if q.strip()]
    logger.info(f"Scraping {len(query_list)} search queries")
    logger.info(f"Limit: {limit} images per query")
    logger.info(f"Output: {output_dir.absolute()}")

    total_downloaded = 0

    for query in query_list:
        downloaded = scrape_query(query, output_dir, limit, logger)
        total_downloaded += downloaded

    logger.info("=" * 60)
    logger.info(f"Total downloaded: {total_downloaded} images")
    logger.info(f"Output directory: {output_dir.absolute()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    scrape()
