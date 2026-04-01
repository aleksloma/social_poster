"""X (Twitter) API publisher with image upload support using OAuth 1.0a."""

import logging

from requests_oauthlib import OAuth1Session

logger = logging.getLogger(__name__)

UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
TWEET_URL = "https://api.twitter.com/2/tweets"


def _get_oauth_session(
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
) -> OAuth1Session:
    return OAuth1Session(
        api_key,
        client_secret=api_secret,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
    )


def _upload_media(session: OAuth1Session, image_data: bytes) -> str | None:
    """Upload media to Twitter and return the media_id_string.

    Uses the v1.1 media upload endpoint with multipart form data.

    Returns:
        media_id_string or None on failure.
    """
    try:
        resp = session.post(
            UPLOAD_URL,
            files={"media_data": image_data},
            timeout=60,
        )
        resp.raise_for_status()
        media_id = resp.json().get("media_id_string")
        logger.info("Twitter media uploaded: %s", media_id)
        return media_id
    except Exception as e:
        logger.error("Twitter media upload failed: %s", e)
        return None


def publish(
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
    text: str,
    image_data: bytes | None = None,
) -> bool:
    """Publish a tweet, optionally with an image.

    Args:
        api_key: Twitter API key (consumer key).
        api_secret: Twitter API secret (consumer secret).
        access_token: OAuth access token.
        access_token_secret: OAuth access token secret.
        text: Tweet text.
        image_data: Optional image binary data.

    Returns:
        True if published successfully, False otherwise.
    """
    session = _get_oauth_session(api_key, api_secret, access_token, access_token_secret)

    media_id = None
    if image_data:
        media_id = _upload_media(session, image_data)
        if not media_id:
            logger.warning("Twitter: media upload failed, posting without image")

    body = {"text": text}
    if media_id:
        body["media"] = {"media_ids": [media_id]}

    try:
        resp = session.post(TWEET_URL, json=body, timeout=30)
        resp.raise_for_status()
        tweet_data = resp.json()
        tweet_id = tweet_data.get("data", {}).get("id")
        logger.info("Tweet published: %s", tweet_id)
        return True
    except Exception as e:
        logger.error("Twitter publish failed: %s", e)
        if hasattr(e, "response") and e.response is not None:
            logger.error("Response body: %s", e.response.text)
        return False
