"""Tests for blog_fetcher module."""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blog_fetcher


SAMPLE_POST_LIST_RESPONSE = {
    "posts": [
        {
            "slug": "best-ai-tool-for-csv-analysis",
            "title": "Best AI Tool for CSV Analysis in 2026",
            "meta_description": "Find the right ai tool for csv analysis...",
            "published_at": "2026-04-01T10:00:00+00:00",
            "featured_image": "/static/blog/images/best-ai-tool-for-csv-analysis.png",
        },
        {
            "slug": "excel-data-analysis-with-ai",
            "title": "Excel Data Analysis with AI",
            "meta_description": "Use AI to analyze your Excel data...",
            "published_at": "2026-03-30T10:00:00+00:00",
            "featured_image": "/static/blog/images/excel-data-analysis.png",
        },
    ],
    "total": 2,
    "limit": 20,
    "offset": 0,
}

SAMPLE_FULL_POST = {
    "slug": "best-ai-tool-for-csv-analysis",
    "title": "Best AI Tool for CSV Analysis in 2026",
    "html_content": "<h2>Introduction</h2><p>Full article body here.</p><p>Second paragraph.</p>",
    "meta_description": "Find the right ai tool...",
    "meta_keywords": "csv, ai, analysis",
    "author": "PowerDataChat",
    "published_at": "2026-04-01T10:00:00+00:00",
    "featured_image": "/static/blog/images/best-ai-tool-for-csv-analysis.png",
    "saved_at": "2026-04-01T10:00:00+00:00",
}


class TestFetchPostList:
    def test_success(self, mocker):
        mock_resp = mocker.Mock()
        mock_resp.json.return_value = SAMPLE_POST_LIST_RESPONSE
        mock_resp.raise_for_status = mocker.Mock()
        mocker.patch("blog_fetcher.requests.get", return_value=mock_resp)

        posts = blog_fetcher.fetch_post_list("https://powerdatachat.com/api/blog/posts")
        assert len(posts) == 2
        assert posts[0]["slug"] == "best-ai-tool-for-csv-analysis"

    def test_empty_response(self, mocker):
        mock_resp = mocker.Mock()
        mock_resp.json.return_value = {"posts": [], "total": 0}
        mock_resp.raise_for_status = mocker.Mock()
        mocker.patch("blog_fetcher.requests.get", return_value=mock_resp)

        posts = blog_fetcher.fetch_post_list("https://example.com/api/blog/posts")
        assert posts == []

    def test_network_failure_returns_empty(self, mocker):
        import requests
        mocker.patch("blog_fetcher.requests.get", side_effect=requests.RequestException("timeout"))

        posts = blog_fetcher.fetch_post_list("https://example.com/api/blog/posts")
        assert posts == []


class TestFetchFullPost:
    def test_success(self, mocker):
        mock_resp = mocker.Mock()
        mock_resp.json.return_value = SAMPLE_FULL_POST
        mock_resp.raise_for_status = mocker.Mock()
        mocker.patch("blog_fetcher.requests.get", return_value=mock_resp)

        post = blog_fetcher.fetch_full_post(
            "https://powerdatachat.com/api/blog/posts",
            "best-ai-tool-for-csv-analysis",
        )
        assert post is not None
        assert post["slug"] == "best-ai-tool-for-csv-analysis"
        assert "<h2>" in post["html_content"]

    def test_network_failure_returns_none(self, mocker):
        import requests
        mocker.patch("blog_fetcher.requests.get", side_effect=requests.RequestException("fail"))

        post = blog_fetcher.fetch_full_post("https://example.com/api/blog/posts", "some-slug")
        assert post is None


class TestHtmlToPlainText:
    def test_strips_tags(self):
        html = "<h2>Title</h2><p>Paragraph one.</p><p>Paragraph two.</p>"
        text = blog_fetcher.html_to_plain_text(html)
        assert "Title" in text
        assert "Paragraph one." in text
        assert "<h2>" not in text
        assert "<p>" not in text

    def test_handles_empty_string(self):
        assert blog_fetcher.html_to_plain_text("") == ""

    def test_collapses_blank_lines(self):
        html = "<p>A</p><br><br><br><br><p>B</p>"
        text = blog_fetcher.html_to_plain_text(html)
        # Should not have more than 2 consecutive newlines
        assert "\n\n\n" not in text


class TestGetFullImageUrl:
    def test_relative_path(self):
        url = blog_fetcher.get_full_image_url(
            "https://powerdatachat.com",
            "/static/blog/images/test.png",
        )
        assert url == "https://powerdatachat.com/static/blog/images/test.png"

    def test_absolute_url(self):
        url = blog_fetcher.get_full_image_url(
            "https://powerdatachat.com",
            "https://cdn.example.com/image.png",
        )
        assert url == "https://cdn.example.com/image.png"

    def test_none_image(self):
        assert blog_fetcher.get_full_image_url("https://example.com", None) is None

    def test_empty_image(self):
        assert blog_fetcher.get_full_image_url("https://example.com", "") is None


class TestDownloadImage:
    def test_success(self, mocker):
        mock_resp = mocker.Mock()
        mock_resp.content = b"\x89PNG fake image data"
        mock_resp.raise_for_status = mocker.Mock()
        mocker.patch("blog_fetcher.requests.get", return_value=mock_resp)

        data = blog_fetcher.download_image("https://example.com/image.png")
        assert data == b"\x89PNG fake image data"

    def test_failure_returns_none(self, mocker):
        import requests
        mocker.patch("blog_fetcher.requests.get", side_effect=requests.RequestException("fail"))

        data = blog_fetcher.download_image("https://example.com/image.png")
        assert data is None

    def test_none_url_returns_none(self):
        assert blog_fetcher.download_image(None) is None
