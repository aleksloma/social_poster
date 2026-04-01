"""Fetches blog posts from the PowerDataChat public API."""

import logging
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def fetch_post_list(api_url: str, limit: int = 20, offset: int = 0) -> list[dict]:
    """Fetch the list of blog posts from the API.

    Args:
        api_url: Base blog posts API URL.
        limit: Max number of posts to fetch.
        offset: Pagination offset.

    Returns:
        List of post summary dicts with keys: slug, title, meta_description,
        published_at, featured_image.
    """
    url = f"{api_url}?limit={limit}&offset={offset}"
    logger.info("Fetching blog post list from %s", url)

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch post list: %s", e)
        # Retry once
        try:
            logger.info("Retrying post list fetch...")
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e2:
            logger.error("Retry failed: %s", e2)
            return []

    data = resp.json()
    posts = data.get("posts", [])
    logger.info("Fetched %d blog posts (total: %s)", len(posts), data.get("total"))
    return posts


def fetch_full_post(api_url: str, slug: str) -> dict | None:
    """Fetch the full content of a single blog post by slug.

    Args:
        api_url: Base blog posts API URL.
        slug: The post slug.

    Returns:
        Full post dict or None on failure.
    """
    url = f"{api_url}/{slug}"
    logger.info("Fetching full post: %s", slug)

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch post %s: %s", slug, e)
        try:
            logger.info("Retrying fetch for %s...", slug)
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e2:
            logger.error("Retry failed for %s: %s", slug, e2)
            return None

    return resp.json()


def html_to_plain_text(html_content: str) -> str:
    """Strip HTML tags and return clean plain text."""
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def get_full_image_url(base_url: str, featured_image: str | None) -> str | None:
    """Return the full image URL, prepending base_url if the path is relative."""
    if not featured_image:
        return None
    if featured_image.startswith("http"):
        return featured_image
    return f"{base_url.rstrip('/')}{featured_image}"


def download_image(image_url: str) -> bytes | None:
    """Download an image and return its binary content, or None on failure."""
    if not image_url:
        return None

    logger.info("Downloading image: %s", image_url)
    try:
        resp = requests.get(image_url, timeout=30)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as e:
        logger.warning("Failed to download image %s: %s", image_url, e)
        return None
