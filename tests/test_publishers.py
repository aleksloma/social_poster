"""Tests for publisher modules — credential checking and API mocking."""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from publishers import linkedin, facebook, twitter


class TestLinkedInPublisher:
    def test_publish_text_only(self, mocker):
        mock_post = mocker.patch("publishers.linkedin.requests.post")
        mock_resp = mocker.Mock()
        mock_resp.raise_for_status = mocker.Mock()
        mock_post.return_value = mock_resp

        result = linkedin.publish(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
            text="Test LinkedIn post",
            image_data=None,
        )
        assert result is True
        mock_post.assert_called_once()

        # Verify the post body
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["author"] == "urn:li:person:abc123"
        assert body["commentary"] == "Test LinkedIn post"
        assert body["visibility"] == "PUBLIC"
        assert "content" not in body  # No image

    def test_publish_with_image(self, mocker):
        # Mock image upload init
        mock_post = mocker.patch("publishers.linkedin.requests.post")
        mock_put = mocker.patch("publishers.linkedin.requests.put")

        # First call: image init
        init_resp = mocker.Mock()
        init_resp.raise_for_status = mocker.Mock()
        init_resp.json.return_value = {
            "value": {
                "uploadUrl": "https://upload.linkedin.com/upload/123",
                "image": "urn:li:image:abc",
            }
        }

        # Second call: create post
        post_resp = mocker.Mock()
        post_resp.raise_for_status = mocker.Mock()

        mock_post.side_effect = [init_resp, post_resp]

        # PUT for image binary
        upload_resp = mocker.Mock()
        upload_resp.raise_for_status = mocker.Mock()
        mock_put.return_value = upload_resp

        result = linkedin.publish(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
            text="Test with image",
            image_data=b"fake image data",
        )
        assert result is True
        assert mock_post.call_count == 2
        mock_put.assert_called_once()

    def test_publish_failure(self, mocker):
        import requests
        mocker.patch(
            "publishers.linkedin.requests.post",
            side_effect=requests.RequestException("API error"),
        )

        result = linkedin.publish(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
            text="Test post",
        )
        assert result is False


class TestFacebookPublisher:
    def test_publish_text_only(self, mocker):
        mock_post = mocker.patch("publishers.facebook.requests.post")
        mock_resp = mocker.Mock()
        mock_resp.raise_for_status = mocker.Mock()
        mock_resp.json.return_value = {"id": "123456_789"}
        mock_post.return_value = mock_resp

        result = facebook.publish(
            page_id="123456",
            page_access_token="test-token",
            text="Test Facebook post",
            image_url=None,
        )
        assert result is True

        # Should use /feed endpoint for text-only
        call_args = mock_post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
        assert "/feed" in url

    def test_publish_with_image(self, mocker):
        mock_post = mocker.patch("publishers.facebook.requests.post")
        mock_resp = mocker.Mock()
        mock_resp.raise_for_status = mocker.Mock()
        mock_resp.json.return_value = {"id": "123456_photo_789"}
        mock_post.return_value = mock_resp

        result = facebook.publish(
            page_id="123456",
            page_access_token="test-token",
            text="Test with image",
            image_url="https://example.com/image.png",
        )
        assert result is True

        # Should use /photos endpoint
        call_args = mock_post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
        assert "/photos" in url

    def test_publish_failure(self, mocker):
        import requests
        mocker.patch(
            "publishers.facebook.requests.post",
            side_effect=requests.RequestException("API error"),
        )

        result = facebook.publish(
            page_id="123456",
            page_access_token="test-token",
            text="Test post",
        )
        assert result is False


class TestTwitterPublisher:
    def test_publish_text_only(self, mocker):
        mock_session = mocker.Mock()
        mock_resp = mocker.Mock()
        mock_resp.raise_for_status = mocker.Mock()
        mock_resp.json.return_value = {"data": {"id": "1234567890"}}
        mock_session.post.return_value = mock_resp

        mocker.patch("publishers.twitter.OAuth1Session", return_value=mock_session)

        result = twitter.publish(
            api_key="key",
            api_secret="secret",
            access_token="token",
            access_token_secret="token_secret",
            text="Test tweet",
            image_data=None,
        )
        assert result is True
        # Only one post call (tweet, no media upload)
        mock_session.post.assert_called_once()

    def test_publish_with_image(self, mocker):
        mock_session = mocker.Mock()

        # First call: media upload
        media_resp = mocker.Mock()
        media_resp.raise_for_status = mocker.Mock()
        media_resp.json.return_value = {"media_id_string": "media123"}

        # Second call: create tweet
        tweet_resp = mocker.Mock()
        tweet_resp.raise_for_status = mocker.Mock()
        tweet_resp.json.return_value = {"data": {"id": "tweet456"}}

        mock_session.post.side_effect = [media_resp, tweet_resp]
        mocker.patch("publishers.twitter.OAuth1Session", return_value=mock_session)

        result = twitter.publish(
            api_key="key",
            api_secret="secret",
            access_token="token",
            access_token_secret="token_secret",
            text="Test tweet with image",
            image_data=b"fake image",
        )
        assert result is True
        assert mock_session.post.call_count == 2

    def test_publish_failure(self, mocker):
        mock_session = mocker.Mock()
        mock_session.post.side_effect = Exception("API error")

        mocker.patch("publishers.twitter.OAuth1Session", return_value=mock_session)

        result = twitter.publish(
            api_key="key",
            api_secret="secret",
            access_token="token",
            access_token_secret="token_secret",
            text="Test tweet",
        )
        assert result is False


class TestCredentialSkipping:
    """Test that the config module correctly identifies missing credentials."""

    def test_all_credentials_present(self, mocker):
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import check_platform_credentials

        creds = {
            "gemini": {"api_key": "test"},
            "linkedin": {
                "access_token": "token",
                "person_urn": "urn:li:person:123",
                "client_id": "id",
                "client_secret": "secret",
            },
            "facebook": {
                "page_id": "123",
                "page_access_token": "token",
                "app_id": "id",
                "app_secret": "secret",
            },
            "x": {
                "api_key": "key",
                "api_secret": "secret",
                "access_token": "token",
                "access_token_secret": "token_secret",
            },
        }

        result = check_platform_credentials(creds)
        assert result["linkedin"] is True
        assert result["facebook"] is True
        assert result["x"] is True

    def test_missing_linkedin_credentials(self):
        from config import check_platform_credentials

        creds = {
            "gemini": {"api_key": ""},
            "linkedin": {
                "access_token": "",
                "person_urn": "",
                "client_id": "",
                "client_secret": "",
            },
            "facebook": {
                "page_id": "123",
                "page_access_token": "token",
                "app_id": "",
                "app_secret": "",
            },
            "x": {
                "api_key": "",
                "api_secret": "",
                "access_token": "",
                "access_token_secret": "",
            },
        }

        result = check_platform_credentials(creds)
        assert result["linkedin"] is False
        assert result["facebook"] is True
        assert result["x"] is False

    def test_partial_x_credentials(self):
        from config import check_platform_credentials

        creds = {
            "gemini": {"api_key": "key"},
            "linkedin": {"access_token": "t", "person_urn": "u", "client_id": "", "client_secret": ""},
            "facebook": {"page_id": "", "page_access_token": "", "app_id": "", "app_secret": ""},
            "x": {
                "api_key": "key",
                "api_secret": "secret",
                "access_token": "",  # Missing!
                "access_token_secret": "token_secret",
            },
        }

        result = check_platform_credentials(creds)
        assert result["x"] is False  # Missing access_token
