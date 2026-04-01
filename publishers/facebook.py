"""Facebook Page API publisher with image support."""

import logging

import requests

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


def publish(
    page_id: str,
    page_access_token: str,
    text: str,
    image_url: str | None = None,
) -> bool:
    """Publish a post to a Facebook Page, optionally with an image.

    For image posts, Facebook fetches the image from the provided URL directly,
    so we pass the public image URL rather than uploading binary data.

    Args:
        page_id: Facebook Page ID.
        page_access_token: Page access token with publish permissions.
        text: The post text.
        image_url: Optional public URL of the image (Facebook fetches it).

    Returns:
        True if published successfully, False otherwise.
    """
    if image_url:
        # Post with image via /photos endpoint
        url = f"{GRAPH_API_BASE}/{page_id}/photos"
        params = {
            "access_token": page_access_token,
            "message": text,
            "url": image_url,
        }
    else:
        # Text-only post via /feed endpoint
        url = f"{GRAPH_API_BASE}/{page_id}/feed"
        params = {
            "access_token": page_access_token,
            "message": text,
        }

    try:
        resp = requests.post(url, data=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        post_id = data.get("id") or data.get("post_id")
        logger.info("Facebook post published: %s", post_id)
        return True
    except requests.RequestException as e:
        logger.error("Facebook publish failed: %s", e)
        if hasattr(e, "response") and e.response is not None:
            logger.error("Response body: %s", e.response.text)
        return False
