"""Generates platform-specific social media content using Google Gemini API.

Uses a two-pass generation approach:
1. Generate the initial post with a platform-specific prompt.
2. Validate the output with a quality-check prompt; use corrected version if needed.

When generating for multiple platforms from the same blog post, previously generated
posts are included in the prompt context to ensure each platform gets a unique angle.
"""

import logging

import google.generativeai as genai

logger = logging.getLogger(__name__)

PLATFORM_DESCRIPTION = """PowerDataChat (powerdatachat.com) is an AI-powered spreadsheet analytics platform.
Users upload Excel or CSV files and ask questions in plain English.
Unlike ChatGPT or other LLMs that guess answers based on patterns, PowerDataChat \
actually executes Python code on the uploaded data and returns COMPUTED results — \
real numbers, charts, tables, and reports.

Key differentiators:
- Python execution, not AI guessing — every answer is computed from actual data
- No formulas, no pivot tables, no coding required
- Works with Excel (.xlsx) and CSV files
- Generates charts, reports, and PDF exports
- Privacy-focused: data is processed securely and not used for training
- Skills system for repeatable analysis workflows

Target audience: business analysts, marketers, finance teams, operations managers, \
and anyone who works with spreadsheets but hates complex formulas."""

LINKEDIN_PROMPT = """You are writing a LinkedIn post for PowerDataChat.

{platform_description}

Transform this blog post into a LinkedIn post.

RULES:
- TOTAL LENGTH: 1,300-1,600 characters (this is the proven sweet spot for engagement)
- FIRST 200 CHARACTERS ARE CRITICAL — this is all people see before "See more". Write a compelling hook that makes them click.
- Structure: Hook (1-2 lines) → Short insight paragraph → Key takeaway → Call to action with blog link
- 3-5 short paragraphs. Use line breaks between paragraphs for readability.
- End with the blog URL on its own line
- Add exactly 3 relevant hashtags on the last line (e.g. #DataAnalysis #AI #Excel)
- Tone: like a smart colleague sharing an insight over coffee — professional but not stiff
- DO NOT start with emoji openers like "🚀" or "💡" or "Did you know?"
- DO NOT use phrases like "In today's fast-paced world" or "Game-changer" or "Excited to share"
- Focus on a SPECIFIC problem that the blog post addresses and how PowerDataChat solves it
- This post WILL include a featured image from the blog, so don't describe the image — the visual context is already there
{other_platforms_context}
Blog Title: {title}
Blog Summary: {meta_description}
Blog URL: {blog_url}
Blog Content (truncated): {plain_text_content}

Write ONLY the LinkedIn post text. Nothing else."""

FACEBOOK_PROMPT = """You are writing a Facebook post for PowerDataChat's page.

{platform_description}

Transform this blog post into a Facebook post.

RULES:
- LENGTH: 2-3 sentences MAXIMUM. Keep it under 100 words. Shorter is better on Facebook.
- Facebook users scroll FAST — you have 1-2 seconds to grab attention
- Start with a relatable question OR a bold, short statement
- Include the blog URL
- NO hashtags (they hurt reach on Facebook pages in 2026)
- Tone: casual, like sharing a useful tip with a friend
- DO NOT sound like a brand announcement or press release
- DO NOT use corporate language like "leverage", "synergy", "cutting-edge"
- This post WILL include the blog's featured image — the image will do heavy lifting for engagement, so keep text minimal and complementary
- The image + short punchy text combo is what works best on Facebook
{other_platforms_context}
Blog Title: {title}
Blog Summary: {meta_description}
Blog URL: {blog_url}
Blog Content (truncated): {plain_text_content}

Write ONLY the Facebook post text. 2-3 sentences max. Nothing else."""

X_PROMPT = """You are writing a tweet for PowerDataChat.

{platform_description}

Transform this blog post into a tweet.

RULES:
- TEXT MUST be under 200 characters (a URL will be appended separately and takes ~23 characters)
- Ideal: 70-120 characters of text
- Make it punchy — a bold claim, a surprising fact, or a sharp question
- DO NOT use more than 1 emoji (zero is fine)
- DO NOT use hashtags unless they genuinely add value and fit naturally
- This tweet WILL include the blog's featured image as an attached media, so don't describe the image
- The goal is to make people stop scrolling and click
- Include the blog URL at the end
{other_platforms_context}
Blog Title: {title}
Blog Summary: {meta_description}
Blog URL: {blog_url}

Write ONLY the tweet text. Nothing else."""

VALIDATION_PROMPT = """Review this {platform} post for PowerDataChat. Check ALL of the following:

Post to review:
\"\"\"
{generated_post}
\"\"\"

Check:
1. LENGTH: Is it within the required range? (LinkedIn: 1,300-1,600 chars | Facebook: under 100 words | X: under 200 chars)
2. ACCURACY: Does it correctly describe PowerDataChat (Python execution on data, not AI guessing)?
3. URL: Does it include the blog URL?
4. TONE: Does it sound human and natural, not corporate or AI-generated?
5. HOOK: Does the opening line grab attention?
6. UNIQUENESS: Does it bring a fresh angle (not just restating the blog title)?

If ALL checks pass, respond with exactly: PASS
If ANY check fails, respond with a corrected version of the post that fixes all issues. Write ONLY the corrected post, nothing else."""

PROMPTS = {
    "linkedin": LINKEDIN_PROMPT,
    "facebook": FACEBOOK_PROMPT,
    "x": X_PROMPT,
}


def configure_gemini(api_key: str) -> None:
    """Configure the Gemini API with the provided key."""
    genai.configure(api_key=api_key)
    logger.info("Gemini API configured")


def _build_other_platforms_context(other_posts: dict[str, str]) -> str:
    """Build a prompt fragment listing posts already generated for other platforms.

    This ensures each platform gets a completely different angle.
    """
    if not other_posts:
        return ""

    lines = [
        "\nThe following posts were already generated for other platforms. "
        "Your post MUST take a completely different angle:\n"
    ]
    for platform, text in other_posts.items():
        lines.append(f"--- {platform.upper()} post ---")
        lines.append(text)
        lines.append("")
    return "\n".join(lines) + "\n"


def _validate_post(
    platform: str,
    generated_post: str,
    model_name: str,
) -> str:
    """Run a quality-check pass on the generated post.

    Returns the original post if it passes validation, or the corrected version.
    """
    prompt = VALIDATION_PROMPT.format(
        platform=platform,
        generated_post=generated_post,
    )

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        result = response.text.strip()

        if result == "PASS":
            logger.info("Validation PASSED for %s post", platform)
            return generated_post

        logger.info(
            "Validation returned corrected %s post (original: %d chars, corrected: %d chars)",
            platform, len(generated_post), len(result),
        )
        return result
    except Exception as e:
        logger.warning("Validation call failed for %s, using original post: %s", platform, e)
        return generated_post


def generate_post(
    platform: str,
    title: str,
    meta_description: str,
    blog_url: str,
    plain_text_content: str,
    model_name: str = "gemini-2.0-flash",
    max_content_chars: int = 3000,
    other_posts: dict[str, str] | None = None,
) -> str | None:
    """Generate a social media post for the given platform using Gemini.

    Uses a two-pass approach: generate then validate. When other_posts is
    provided, includes them in the prompt to ensure a different angle.

    Args:
        platform: One of 'linkedin', 'facebook', 'x'.
        title: Blog post title.
        meta_description: Blog post meta description.
        blog_url: Full URL to the blog post.
        plain_text_content: Plain text content of the blog post.
        model_name: Gemini model to use.
        max_content_chars: Max characters of blog content to send to Gemini.
        other_posts: Dict mapping platform name to already-generated post text,
                     used to ensure cross-platform uniqueness.

    Returns:
        Generated (and validated) post text, or None on failure.
    """
    prompt_template = PROMPTS.get(platform)
    if not prompt_template:
        logger.error("Unknown platform: %s", platform)
        return None

    truncated_content = plain_text_content[:max_content_chars]
    other_platforms_context = _build_other_platforms_context(other_posts or {})

    prompt = prompt_template.format(
        platform_description=PLATFORM_DESCRIPTION,
        title=title,
        meta_description=meta_description,
        blog_url=blog_url,
        plain_text_content=truncated_content,
        other_platforms_context=other_platforms_context,
    )

    logger.info("Generating %s post for: %s", platform, title)

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = response.text.strip()
        logger.info("Generated %s post (%d chars) for: %s", platform, len(text), title)
    except Exception as e:
        logger.error("Gemini API error generating %s post for %s: %s", platform, title, e)
        return None

    # Pass 2: validation / quality check
    logger.debug("Original %s post:\n%s", platform, text)
    final_text = _validate_post(platform, text, model_name)
    if final_text != text:
        logger.debug("Corrected %s post:\n%s", platform, final_text)

    return final_text
