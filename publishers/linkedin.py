"""LinkedIn API publisher with image upload support."""

import logging

import requests

logger = logging.getLogger(__name__)

API_VERSION = "202401"
BASE_URL = "https://api.linkedin.com/rest"


def _headers(access_token: str, content_type: str = "application/json") -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": content_type,
        "LinkedIn-Version": API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _upload_image(access_token: str, person_urn: str, image_data: bytes) -> str | None:
    """Upload an image to LinkedIn and return the image URN.

    Steps:
    1. Initialize upload to get uploadUrl and image URN.
    2. PUT the binary image data to uploadUrl.

    Returns:
        The image URN string, or None on failure.
    """
    # Step 1: Initialize upload
    init_url = f"{BASE_URL}/images?action=initializeUpload"
    init_body = {
        "initializeUploadRequest": {
            "owner": person_urn,
        }
    }

    try:
        resp = requests.post(init_url, json=init_body, headers=_headers(access_token), timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("LinkedIn image upload init failed: %s", e)
        return None

    data = resp.json().get("value", {})
    upload_url = data.get("uploadUrl")
    image_urn = data.get("image")

    if not upload_url or not image_urn:
        logger.error("LinkedIn image init response missing uploadUrl or image URN")
        return None

    # Step 2: Upload the image binary
    try:
        upload_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/octet-stream",
        }
        resp = requests.put(upload_url, data=image_data, headers=upload_headers, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("LinkedIn image binary upload failed: %s", e)
        return None

    logger.info("LinkedIn image uploaded: %s", image_urn)
    return image_urn


def publish(
    access_token: str,
    person_urn: str,
    text: str,
    image_data: bytes | None = None,
) -> bool:
    """Publish a post to LinkedIn, optionally with an image.

    Args:
        access_token: LinkedIn OAuth access token.
        person_urn: LinkedIn person URN (e.g., 'urn:li:person:xxxxx').
        text: The post text/commentary.
        image_data: Optional image binary data.

    Returns:
        True if published successfully, False otherwise.
    """
    image_urn = None
    if image_data:
        image_urn = _upload_image(access_token, person_urn, image_data)
        if not image_urn:
            logger.warning("LinkedIn: image upload failed, posting without image")

    post_url = f"{BASE_URL}/posts"
    body = {
        "author": person_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
    }

    if image_urn:
        body["content"] = {
            "media": {
                "title": "Blog post image",
                "id": image_urn,
            }
        }

    try:
        resp = requests.post(post_url, json=body, headers=_headers(access_token), timeout=30)
        resp.raise_for_status()
        logger.info("LinkedIn post published successfully (with_image=%s)", image_urn is not None)
        return True
    except requests.RequestException as e:
        logger.error("LinkedIn publish failed: %s", e)
        if hasattr(e, "response") and e.response is not None:
            logger.error("Response body: %s", e.response.text)
        return False
