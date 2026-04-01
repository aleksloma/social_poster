"""Tests for content_generator module."""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import content_generator


def _mock_gemini(mocker, texts):
    """Helper: mock Gemini to return a sequence of response texts."""
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
        post_text = "Great LinkedIn post about data analysis. https://powerdatachat.com/blog/best-ai-tool #DataAnalysis #AI #Excel"
        mock_cls, mock_inst = _mock_gemini(mocker, [
            post_text,
            "PASS",
        ])

        result = content_generator.generate_post(
            platform="linkedin",
            title="Best AI Tool for CSV Analysis",
            meta_description="Find the right ai tool...",
            blog_url="https://powerdatachat.com/blog/best-ai-tool",
            plain_text_content="Full article text here...",
        )

        assert result == post_text
        assert mock_inst.generate_content.call_count == 2
        mock_cls.assert_called_with("gemini-2.0-flash")

    def test_validation_returns_corrected_post(self, mocker):
        corrected = "Corrected and improved post text that is long enough to pass the minimum length threshold for validation cleanup purposes"
        _mock_gemini(mocker, [
            "Original post text https://example.com",
            corrected,
        ])

        result = content_generator.generate_post(
            platform="linkedin",
            title="Test",
            meta_description="Test",
            blog_url="https://example.com",
            plain_text_content="Content...",
        )

        assert corrected in result

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
        mock_model_instance = mocker.Mock()
        gen_resp = mocker.Mock()
        gen_resp.text = "Original generated post https://example.com"
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
        assert result == "Original generated post https://example.com"

    def test_content_truncation(self, mocker):
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

    def test_missing_url_gets_appended(self, mocker):
        """If generated text is missing the blog URL, it gets appended."""
        _mock_gemini(mocker, [
            "A post without the URL. PowerDataChat is great.",
            "PASS",
        ])

        result = content_generator.generate_post(
            platform="facebook",
            title="Test",
            meta_description="Test",
            blog_url="https://powerdatachat.com/blog/test",
            plain_text_content="Content...",
        )

        assert "https://powerdatachat.com/blog/test" in result


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
        assert "{plain_text_content}" not in content_generator.X_PROMPT

    def test_platform_description_mentions_python_execution(self):
        assert "Python execution" in content_generator.PLATFORM_DESCRIPTION
        assert "not AI guessing" in content_generator.PLATFORM_DESCRIPTION


class TestCleanValidationResponse:
    def test_pass_returns_original(self):
        result = content_generator._clean_validation_response("PASS", "Original post")
        assert result == "Original post"

    def test_pass_with_period_returns_original(self):
        result = content_generator._clean_validation_response("PASS.", "Original post")
        assert result == "Original post"

    def test_pass_case_insensitive(self):
        result = content_generator._clean_validation_response("Pass", "Original post")
        assert result == "Original post"

    def test_pass_with_whitespace(self):
        result = content_generator._clean_validation_response("  PASS  ", "Original post")
        assert result == "Original post"

    def test_preamble_with_corrected_version_marker(self):
        response = (
            "The original post is 1780 characters, which exceeds the LinkedIn "
            "recommended range of 1,300-1,600 characters.\n\n"
            "Here is the corrected version:\n\n"
            "Your business decisions demand accurate data. PowerDataChat "
            "executes real Python code on your spreadsheets.\n\n"
            "https://powerdatachat.com/blog/test\n\n"
            "#DataAnalysis #AI #Excel"
        )
        result = content_generator._clean_validation_response(response, "Original")
        assert "Your business decisions" in result
        assert "The original post is" not in result
        assert "Here is the corrected" not in result

    def test_preamble_with_heres_the_corrected(self):
        response = (
            "Some analysis text here.\n"
            "Here's the corrected post:\n\n"
            "Clean post text that should be extracted. "
            "PowerDataChat is great.\n\nhttps://example.com"
        )
        result = content_generator._clean_validation_response(response, "Original")
        assert "Clean post text" in result
        assert "Some analysis" not in result

    def test_clean_response_passes_through(self):
        clean_post = (
            "Your business decisions demand accurate data. PowerDataChat "
            "executes real Python code on your spreadsheets. "
            "Try it at https://powerdatachat.com/blog/test\n\n"
            "#DataAnalysis #AI #Excel"
        )
        result = content_generator._clean_validation_response(clean_post, "Original")
        assert result == clean_post

    def test_contaminated_response_falls_back(self):
        """If cleanup still has contamination phrases, falls back to original."""
        bad_response = (
            "The original post is fine but all other checks passed. "
            "This post mentions PowerDataChat."
        )
        result = content_generator._clean_validation_response(bad_response, "Original fallback")
        assert result == "Original fallback"

    def test_too_short_result_falls_back(self):
        response = (
            "Here is the corrected version:\n\n"
            "Short"
        )
        result = content_generator._clean_validation_response(response, "Original fallback")
        assert result == "Original fallback"


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
        resp.text = "Better version of the post with enough content to pass the length check easily"
        mock_model_instance.generate_content.return_value = resp
        mocker.patch("content_generator.genai.GenerativeModel", return_value=mock_model_instance)

        result = content_generator._validate_post("linkedin", "Original post", "gemini-2.0-flash")
        assert "Better version" in result

    def test_validate_post_api_error_returns_original(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_model_instance.generate_content.side_effect = Exception("API down")
        mocker.patch("content_generator.genai.GenerativeModel", return_value=mock_model_instance)

        result = content_generator._validate_post("facebook", "Original post", "gemini-2.0-flash")
        assert result == "Original post"

    def test_validate_strips_preamble(self, mocker):
        """Validation response with preamble gets cleaned."""
        mock_model_instance = mocker.Mock()
        resp = mocker.Mock()
        resp.text = (
            "The original post is 1780 characters.\n\n"
            "Here is the corrected version:\n\n"
            "Cleaned post content that is long enough to pass the minimum length check threshold."
        )
        mock_model_instance.generate_content.return_value = resp
        mocker.patch("content_generator.genai.GenerativeModel", return_value=mock_model_instance)

        result = content_generator._validate_post("linkedin", "Original post", "gemini-2.0-flash")
        assert "Cleaned post content" in result
        assert "The original post is" not in result


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


class TestCheckPostBeforePublish:
    """Tests for the deterministic pre-publish quality gate."""

    def test_empty_text_fails(self):
        ok, reason = content_generator.check_post_before_publish("linkedin", "", "https://example.com")
        assert not ok
        assert "empty" in reason.lower() or "short" in reason.lower()

    def test_too_short_text_fails(self):
        ok, reason = content_generator.check_post_before_publish("linkedin", "Hi", "https://example.com")
        assert not ok

    def test_validation_leak_detected(self):
        text = "the original post is 1780 characters and exceeds the limit. PowerDataChat is great."
        ok, reason = content_generator.check_post_before_publish("linkedin", text, "https://example.com")
        assert not ok
        assert "validation leak" in reason.lower()

    def test_llm_meta_talk_detected(self):
        text = "As an AI, I think PowerDataChat is great. https://example.com #Data"
        ok, reason = content_generator.check_post_before_publish("linkedin", text * 10, "https://example.com")
        assert not ok
        assert "meta-talk" in reason.lower()

    def test_missing_blog_url_fails(self):
        text = "Great post about PowerDataChat and data analysis. #DataAnalysis #AI #Excel " + "x" * 500
        ok, reason = content_generator.check_post_before_publish("linkedin", text, "https://example.com/blog/test")
        assert not ok
        assert "url" in reason.lower()

    def test_markdown_detected(self):
        text = "**Bold text** about PowerDataChat. https://example.com #Data " + "x" * 500
        ok, reason = content_generator.check_post_before_publish("linkedin", text, "https://example.com")
        assert not ok
        assert "markdown" in reason.lower()

    def test_missing_powerdatachat_mention_fails(self):
        text = "Great tool for data analysis. https://example.com #Data " + "x" * 500
        ok, reason = content_generator.check_post_before_publish("linkedin", text, "https://example.com")
        assert not ok
        assert "powerdatachat" in reason.lower()

    def test_linkedin_without_hashtag_fails(self):
        text = "PowerDataChat is an amazing tool for data. https://example.com " + "x" * 500
        ok, reason = content_generator.check_post_before_publish("linkedin", text, "https://example.com")
        assert not ok
        assert "hashtag" in reason.lower()

    def test_linkedin_too_short_fails(self):
        text = "PowerDataChat rocks! https://example.com #Data"
        ok, reason = content_generator.check_post_before_publish("linkedin", text, "https://example.com")
        assert not ok
        assert "length" in reason.lower()

    def test_x_over_280_fails(self):
        text = "PowerDataChat " + "x" * 280 + " https://example.com"
        ok, reason = content_generator.check_post_before_publish("x", text, "https://example.com")
        assert not ok
        assert "280" in reason

    def test_facebook_too_many_hashtags_fails(self):
        text = "PowerDataChat is great. https://example.com #one #two #three"
        ok, reason = content_generator.check_post_before_publish("facebook", text, "https://example.com")
        assert not ok
        assert "hashtag" in reason.lower()

    def test_valid_linkedin_post_passes(self):
        text = (
            "Most teams still copy-paste data between spreadsheets and ChatGPT. "
            "The results? Approximate, unverifiable, and often wrong.\n\n"
            "PowerDataChat takes a fundamentally different approach. Instead of "
            "pattern-matching, it writes and executes actual Python code on your "
            "data. Every number is computed, not guessed. No formulas, no pivot "
            "tables, no coding skills required.\n\n"
            "Upload your Excel or CSV file, ask a question in plain English, and "
            "get real answers backed by real computation. Charts, reports, and "
            "insights generated automatically from your actual data.\n\n"
            "https://powerdatachat.com/blog/python-vs-guessing\n\n"
            "#DataAnalysis #AI #Excel"
        )
        ok, reason = content_generator.check_post_before_publish(
            "linkedin", text, "https://powerdatachat.com/blog/python-vs-guessing"
        )
        assert ok, f"Expected pass but got: {reason}"

    def test_valid_facebook_post_passes(self):
        text = (
            "Ever spent hours building a pivot table only to second-guess the result? "
            "PowerDataChat runs real Python on your data — no formulas needed. "
            "https://powerdatachat.com/blog/test"
        )
        ok, reason = content_generator.check_post_before_publish(
            "facebook", text, "https://powerdatachat.com/blog/test"
        )
        assert ok, f"Expected pass but got: {reason}"

    def test_valid_x_post_passes(self):
        text = "Stop guessing, start computing. PowerDataChat runs Python on your spreadsheets. https://powerdatachat.com/blog/test"
        ok, reason = content_generator.check_post_before_publish(
            "x", text, "https://powerdatachat.com/blog/test"
        )
        assert ok, f"Expected pass but got: {reason}"
