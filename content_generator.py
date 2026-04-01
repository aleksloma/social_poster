"""Generates platform-specific social media content using Google Gemini API."""

import logging

import google.generativeai as genai

logger = logging.getLogger(__name__)

LINKEDIN_PROMPT = """You are a social media manager for PowerDataChat (powerdatachat.com), an AI-powered spreadsheet analytics platform where users upload Excel or CSV files and ask questions in plain English — it runs Python on the data and returns computed answers, charts, and reports.

Transform the following blog post into a LinkedIn post.

RULES:
- Length: 150-300 words
- Tone: Professional, insight-driven, thought-leadership
- Structure: Start with a hook (problem, surprising fact, or bold statement), then 2-3 short paragraphs, then a call to action with the blog link
- Include the blog post URL at the end
- Add 2-3 relevant hashtags at the very end (like #DataAnalysis #AI #Excel)
- Sound human and authentic, NOT corporate or AI-generated
- Focus on the VALUE and PROBLEM being solved
- Do NOT start with "🚀" or other cliché openers

Blog Title: {title}
Blog Summary: {meta_description}
Blog URL: {blog_url}
Blog Content: {plain_text_content}

Write ONLY the LinkedIn post text, nothing else."""

FACEBOOK_PROMPT = """You are a social media manager for PowerDataChat (powerdatachat.com), an AI-powered spreadsheet analytics platform where users upload Excel or CSV files and ask questions in plain English — it runs Python on the data and returns computed answers, charts, and reports.

Transform the following blog post into a Facebook post.

RULES:
- Length: 80-150 words
- Tone: Conversational, friendly, benefit-focused
- Start with a relatable question or scenario that hooks the reader
- Keep paragraphs very short (1-2 sentences each)
- Include the blog post URL
- Maximum 1-2 hashtags (or none if they feel forced)
- Sound like a helpful friend sharing a tip, NOT a brand pushing content
- Focus on what the reader gains

Blog Title: {title}
Blog Summary: {meta_description}
Blog URL: {blog_url}
Blog Content: {plain_text_content}

Write ONLY the Facebook post text, nothing else."""

X_PROMPT = """You are a social media manager for PowerDataChat (powerdatachat.com), an AI-powered spreadsheet analytics platform.

Transform the following blog post into a tweet.

RULES:
- MUST be under 250 characters (leave room for the URL which will be appended)
- Punchy, hook-driven — bold claim, surprising stat, or provocative question
- Include the blog post URL at the end
- No hashtags unless they fit naturally and don't waste characters
- Make people want to click
- Do NOT use emojis excessively (0-1 max)

Blog Title: {title}
Blog Summary: {meta_description}
Blog URL: {blog_url}

Write ONLY the tweet text, nothing else."""

PROMPTS = {
    "linkedin": LINKEDIN_PROMPT,
    "facebook": FACEBOOK_PROMPT,
    "x": X_PROMPT,
}


def configure_gemini(api_key: str) -> None:
    """Configure the Gemini API with the provided key."""
    genai.configure(api_key=api_key)
    logger.info("Gemini API configured")


def generate_post(
    platform: str,
    title: str,
    meta_description: str,
    blog_url: str,
    plain_text_content: str,
    model_name: str = "gemini-2.0-flash",
    max_content_chars: int = 3000,
) -> str | None:
    """Generate a social media post for the given platform using Gemini.

    Args:
        platform: One of 'linkedin', 'facebook', 'x'.
        title: Blog post title.
        meta_description: Blog post meta description.
        blog_url: Full URL to the blog post.
        plain_text_content: Plain text content of the blog post.
        model_name: Gemini model to use.
        max_content_chars: Max characters of blog content to send to Gemini.

    Returns:
        Generated post text or None on failure.
    """
    prompt_template = PROMPTS.get(platform)
    if not prompt_template:
        logger.error("Unknown platform: %s", platform)
        return None

    truncated_content = plain_text_content[:max_content_chars]

    prompt = prompt_template.format(
        title=title,
        meta_description=meta_description,
        blog_url=blog_url,
        plain_text_content=truncated_content,
    )

    logger.info("Generating %s post for: %s", platform, title)

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        text = response.text.strip()
        logger.info("Generated %s post (%d chars) for: %s", platform, len(text), title)
        return text
    except Exception as e:
        logger.error("Gemini API error generating %s post for %s: %s", platform, title, e)
        return None
