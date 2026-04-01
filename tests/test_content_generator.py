"""Tests for content_generator module."""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import content_generator


def _mock_gemini(mocker, texts):
    """Helper: mock Gemini to return a sequence of response texts.

    Args:
        mocker: pytest-mock fixture.
        texts: list of strings for successive generate_content calls.
    """
    mock_model_instance = mocker.Mock()
    responses = []
    for t in texts:
        resp = mocker.Mock()
        resp.text = t
        responses.append(resp)
    mock_model_instance.generate_content.side_effect = responses

    mock_model_class = mocker.patch("content_generator.genai.GenerativeModel")
    mock_model_class.return_value = mock_model_instance
    return mock_model_class, mock_model_instance


class TestGeneratePost:
    def test_linkedin_post_generation_with_validation_pass(self, mocker):
        """Two Gemini calls: generation + validation that returns PASS."""
        mock_cls, mock_inst = _mock_gemini(mocker, [
            "Great LinkedIn post about data analysis. #DataAnalysis #AI #Excel",
            "PASS",
        ])

        result = content_generator.generate_post(
            platform="linkedin",
            title="Best AI Tool for CSV Analysis",
            meta_description="Find the right ai tool...",
            blog_url="https://powerdatachat.com/blog/best-ai-tool",
            plain_text_content="Full article text here...",
        )

        assert result == "Great LinkedIn post about data analysis. #DataAnalysis #AI #Excel"
        assert mock_inst.generate_content.call_count == 2
        mock_cls.assert_called_with("gemini-2.0-flash")

    def test_validation_returns_corrected_post(self, mocker):
        """Validation returns a corrected version instead of PASS."""
        _mock_gemini(mocker, [
            "Original post text",
            "Corrected and improved post text",
        ])

        result = content_generator.generate_post(
            platform="linkedin",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content="Content...",
        )

        assert result == "Corrected and improved post text"

    def test_facebook_post_generation(self, mocker):
        _mock_gemini(mocker, [
            "Ever spent hours in a spreadsheet? There's a better way.",
            "PASS",
        ])

        result = content_generator.generate_post(
            platform="facebook",
            title="Excel Data Analysis with AI",
            meta_description="Use AI to analyze...",
            blog_url="https://powerdatachat.com/blog/excel-analysis",
            plain_text_content="Article content...",
        )

        assert result is not None

    def test_x_post_generation(self, mocker):
        _mock_gemini(mocker, [
            "CSV files don't have to be painful.",
            "PASS",
        ])

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

    def test_validation_failure_uses_original(self, mocker):
        """If validation call itself errors out, the original post is kept."""
        mock_model_instance = mocker.Mock()
        gen_resp = mocker.Mock()
        gen_resp.text = "Original generated post"
        mock_model_instance.generate_content.side_effect = [
            gen_resp,
            Exception("validation API error"),
        ]
        mocker.patch("content_generator.genai.GenerativeModel", return_value=mock_model_instance)

        result = content_generator.generate_post(
            platform="facebook",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content="Content",
        )
        assert result == "Original generated post"

    def test_content_truncation(self, mocker):
        _mock_gemini(mocker, ["Generated post", "PASS"])

        mock_cls, mock_inst = _mock_gemini(mocker, ["Generated post", "PASS"])

        long_content = "A" * 10000
        content_generator.generate_post(
            platform="linkedin",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content=long_content,
            max_content_chars=500,
        )

        # Verify the generation prompt was called with truncated content
        gen_call_args = mock_inst.generate_content.call_args_list[0][0][0]
        assert "A" * 500 in gen_call_args
        assert "A" * 501 not in gen_call_args

    def test_custom_model_name(self, mocker):
        mock_cls, mock_inst = _mock_gemini(mocker, ["Post text", "PASS"])

        content_generator.generate_post(
            platform="linkedin",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content="Content",
            model_name="gemini-1.5-pro",
        )

        mock_cls.assert_called_with("gemini-1.5-pro")

    def test_other_posts_included_in_prompt(self, mocker):
        """When other_posts is provided, previously generated texts appear in the prompt."""
        mock_cls, mock_inst = _mock_gemini(mocker, ["Facebook post", "PASS"])

        content_generator.generate_post(
            platform="facebook",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content="Content",
            other_posts={"linkedin": "Previously generated LinkedIn content here"},
        )

        gen_prompt = mock_inst.generate_content.call_args_list[0][0][0]
        assert "Previously generated LinkedIn content here" in gen_prompt
        assert "completely different angle" in gen_prompt.lower()


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
            assert "{platform_description}" in prompt, f"{platform} prompt missing {{platform_description}}"
            assert "{other_platforms_context}" in prompt, f"{platform} prompt missing {{other_platforms_context}}"

    def test_x_prompt_omits_full_content(self):
        # X prompt should NOT include {plain_text_content} (only summary)
        assert "{plain_text_content}" not in content_generator.X_PROMPT

    def test_platform_description_mentions_python_execution(self):
        assert "Python execution" in content_generator.PLATFORM_DESCRIPTION
        assert "not AI guessing" in content_generator.PLATFORM_DESCRIPTION


class TestValidation:
    def test_validate_post_pass(self, mocker):
        mock_model_instance = mocker.Mock()
        resp = mocker.Mock()
        resp.text = "PASS"
        mock_model_instance.generate_content.return_value = resp
        mocker.patch("content_generator.genai.GenerativeModel", return_value=mock_model_instance)

        result = content_generator._validate_post("linkedin", "Original post", "gemini-2.0-flash")
        assert result == "Original post"

    def test_validate_post_corrected(self, mocker):
        mock_model_instance = mocker.Mock()
        resp = mocker.Mock()
        resp.text = "Better version of the post"
        mock_model_instance.generate_content.return_value = resp
        mocker.patch("content_generator.genai.GenerativeModel", return_value=mock_model_instance)

        result = content_generator._validate_post("linkedin", "Original post", "gemini-2.0-flash")
        assert result == "Better version of the post"

    def test_validate_post_api_error_returns_original(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_model_instance.generate_content.side_effect = Exception("API down")
        mocker.patch("content_generator.genai.GenerativeModel", return_value=mock_model_instance)

        result = content_generator._validate_post("facebook", "Original post", "gemini-2.0-flash")
        assert result == "Original post"


class TestBuildOtherPlatformsContext:
    def test_empty_dict_returns_empty_string(self):
        assert content_generator._build_other_platforms_context({}) == ""

    def test_includes_platform_posts(self):
        result = content_generator._build_other_platforms_context({
            "linkedin": "LinkedIn text here",
        })
        assert "LINKEDIN" in result
        assert "LinkedIn text here" in result
        assert "completely different angle" in result.lower()

    def test_multiple_platforms(self):
        result = content_generator._build_other_platforms_context({
            "linkedin": "LI text",
            "facebook": "FB text",
        })
        assert "LINKEDIN" in result
        assert "FACEBOOK" in result
        assert "LI text" in result
        assert "FB text" in result
