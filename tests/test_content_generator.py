"""Tests for content_generator module."""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import content_generator


class TestGeneratePost:
    def test_linkedin_post_generation(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = "Great LinkedIn post about data analysis. #DataAnalysis #AI"
        mock_model_instance.generate_content.return_value = mock_response

        mock_model_class = mocker.patch("content_generator.genai.GenerativeModel")
        mock_model_class.return_value = mock_model_instance

        result = content_generator.generate_post(
            platform="linkedin",
            title="Best AI Tool for CSV Analysis",
            meta_description="Find the right ai tool...",
            blog_url="https://powerdatachat.com/blog/best-ai-tool",
            plain_text_content="Full article text here...",
        )

        assert result is not None
        assert "LinkedIn" in result or "data" in result.lower()
        mock_model_class.assert_called_once_with("gemini-2.0-flash")
        mock_model_instance.generate_content.assert_called_once()

    def test_facebook_post_generation(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = "Ever spent hours in a spreadsheet? There's a better way."
        mock_model_instance.generate_content.return_value = mock_response

        mock_model_class = mocker.patch("content_generator.genai.GenerativeModel")
        mock_model_class.return_value = mock_model_instance

        result = content_generator.generate_post(
            platform="facebook",
            title="Excel Data Analysis with AI",
            meta_description="Use AI to analyze...",
            blog_url="https://powerdatachat.com/blog/excel-analysis",
            plain_text_content="Article content...",
        )

        assert result is not None
        mock_model_class.assert_called_once_with("gemini-2.0-flash")

    def test_x_post_generation(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = "CSV files don't have to be painful."
        mock_model_instance.generate_content.return_value = mock_response

        mock_model_class = mocker.patch("content_generator.genai.GenerativeModel")
        mock_model_class.return_value = mock_model_instance

        result = content_generator.generate_post(
            platform="x",
            title="Best AI Tool",
            meta_description="Find the right tool...",
            blog_url="https://powerdatachat.com/blog/test",
            plain_text_content="Content...",
        )

        assert result is not None

    def test_unknown_platform_returns_none(self):
        result = content_generator.generate_post(
            platform="tiktok",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content="Content",
        )
        assert result is None

    def test_gemini_api_failure_returns_none(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_model_instance.generate_content.side_effect = Exception("API error")

        mocker.patch("content_generator.genai.GenerativeModel", return_value=mock_model_instance)

        result = content_generator.generate_post(
            platform="linkedin",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content="Content",
        )
        assert result is None

    def test_content_truncation(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = "Generated post"
        mock_model_instance.generate_content.return_value = mock_response

        mocker.patch("content_generator.genai.GenerativeModel", return_value=mock_model_instance)

        long_content = "A" * 10000
        content_generator.generate_post(
            platform="linkedin",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content=long_content,
            max_content_chars=500,
        )

        # Verify the prompt was called with truncated content
        call_args = mock_model_instance.generate_content.call_args[0][0]
        # The content in the prompt should be truncated to 500 chars
        assert "A" * 500 in call_args
        assert "A" * 501 not in call_args

    def test_custom_model_name(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_response = mocker.Mock()
        mock_response.text = "Post text"
        mock_model_instance.generate_content.return_value = mock_response

        mock_model_class = mocker.patch("content_generator.genai.GenerativeModel")
        mock_model_class.return_value = mock_model_instance

        content_generator.generate_post(
            platform="linkedin",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content="Content",
            model_name="gemini-1.5-pro",
        )

        mock_model_class.assert_called_once_with("gemini-1.5-pro")


class TestPromptTemplates:
    def test_all_platforms_have_prompts(self):
        assert "linkedin" in content_generator.PROMPTS
        assert "facebook" in content_generator.PROMPTS
        assert "x" in content_generator.PROMPTS

    def test_prompts_contain_required_placeholders(self):
        for platform, prompt in content_generator.PROMPTS.items():
            assert "{title}" in prompt, f"{platform} prompt missing {{title}}"
            assert "{meta_description}" in prompt, f"{platform} prompt missing {{meta_description}}"
            assert "{blog_url}" in prompt, f"{platform} prompt missing {{blog_url}}"

    def test_x_prompt_omits_full_content(self):
        # X prompt should NOT include {plain_text_content} (only summary)
        assert "{plain_text_content}" not in content_generator.X_PROMPT
