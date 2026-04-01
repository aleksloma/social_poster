"""Main orchestrator for social-poster.

Fetches blog posts, generates platform-specific content, and publishes
to LinkedIn, Facebook, and X (Twitter) on a configurable schedule.

Usage:
    python main.py              # Continuous loop (check every N hours)
    python main.py --once       # Single cycle then exit
    python main.py --dry-run    # Fetch and generate but don't publish
"""

import argparse
import logging
import time
import sys

import blog_fetcher
import content_generator
import db
import scheduler
from config import load_config, setup_logging, get_credentials, check_platform_credentials
from publishers import linkedin, facebook, twitter

logger = logging.getLogger(__name__)


def run_cycle(config: dict, credentials: dict, active_platforms: dict[str, bool], dry_run: bool = False) -> None:
    """Execute one full cycle: fetch → generate → schedule → publish.

    Args:
        config: Full config dict from config.yaml.
        credentials: Credentials dict from get_credentials().
        active_platforms: Which platforms are active.
        dry_run: If True, generate content but don't publish.
    """
    blog_config = config["blog"]
    schedule_config = config["schedule"]
    gemini_config = config.get("gemini", {})

    # Step 1: Fetch blog posts
    logger.info("=== Starting cycle ===")
    posts = blog_fetcher.fetch_post_list(blog_config["api_url"])
    if not posts:
        logger.info("No blog posts found, ending cycle")
        return

    logger.info("Found %d blog posts", len(posts))

    # Step 2: Assign posts to platforms
    assignments = scheduler.distribute_posts_round_robin(
        posts, schedule_config, active_platforms,
    )

    if not assignments:
        logger.info("No posts to assign this cycle")
        return

    # Step 3: For each assignment, fetch full content, generate, and publish
    gemini_key = credentials["gemini"]["api_key"]
    if gemini_key:
        content_generator.configure_gemini(gemini_key)
    else:
        logger.error("Gemini API key not configured — cannot generate content")
        return

    # Build a slug → {platform: post} map so we can generate cross-platform
    # differentiated content (each platform gets the others' text as context).
    slug_platforms: dict[str, list[tuple[str, dict]]] = {}
    for platform, assigned_posts in assignments.items():
        for post in assigned_posts:
            slug_platforms.setdefault(post["slug"], []).append((platform, post))

    for slug, platform_posts in slug_platforms.items():
        generated_so_far: dict[str, str] = {}  # platform → generated text

        for platform, post in platform_posts:
            title = post.get("title", slug)
            platform_config = schedule_config.get(platform, {})

            # Check if today is a posting day for this platform
            if not dry_run and not scheduler.should_post_now(platform_config):
                next_time = scheduler.get_next_post_time(platform_config)
                logger.info(
                    "%s: not a posting slot now, next slot: %s — scheduling %s",
                    platform, next_time, slug,
                )

            try:
                generated_text = _process_post(
                    platform, post, config, credentials, gemini_config,
                    blog_config, dry_run, other_posts=generated_so_far,
                )
                if generated_text:
                    generated_so_far[platform] = generated_text
            except Exception as e:
                logger.error("Error processing %s for %s: %s", slug, platform, e, exc_info=True)
                db.mark_failed(slug, platform, str(e))


def _generate_with_quality_check(
    platform: str,
    title: str,
    meta_desc: str,
    blog_url: str,
    plain_text: str,
    gemini_config: dict,
    other_posts: dict[str, str] | None,
) -> str | None:
    """Generate a post and run it through the pre-publish quality gate.

    Retries once with a hint if the first attempt fails the check.
    Returns the final text or None if both attempts fail.
    """
    generated_text = content_generator.generate_post(
        platform=platform,
        title=title,
        meta_description=meta_desc,
        blog_url=blog_url,
        plain_text_content=plain_text,
        model_name=gemini_config.get("model", "gemini-3-flash-preview"),
        max_content_chars=gemini_config.get("max_content_chars", 3000),
        other_posts=other_posts,
    )

    if not generated_text:
        return None

    # Pre-publish quality gate
    ok, reason = content_generator.check_post_before_publish(platform, generated_text, blog_url)
    if ok:
        return generated_text

    logger.warning("Pre-publish check failed for %s/%s: %s — retrying", title, platform, reason)

    # Retry with hint about the failure
    retry_text = content_generator.generate_post(
        platform=platform,
        title=title,
        meta_description=meta_desc,
        blog_url=blog_url,
        plain_text_content=plain_text,
        model_name=gemini_config.get("model", "gemini-3-flash-preview"),
        max_content_chars=gemini_config.get("max_content_chars", 3000),
        other_posts=other_posts,
    )

    if not retry_text:
        return None

    ok2, reason2 = content_generator.check_post_before_publish(platform, retry_text, blog_url)
    if ok2:
        logger.info("Retry passed pre-publish check for %s/%s", title, platform)
        return retry_text

    logger.error(
        "Post for %s/%s failed quality check twice (%s), skipping",
        title, platform, reason2,
    )
    return None


def _process_post(
    platform: str,
    post: dict,
    config: dict,
    credentials: dict,
    gemini_config: dict,
    blog_config: dict,
    dry_run: bool,
    other_posts: dict[str, str] | None = None,
) -> str | None:
    """Process a single post for a single platform: fetch → generate → publish.

    Returns the generated text (for cross-platform differentiation) or None.
    """
    slug = post["slug"]
    title = post.get("title", slug)
    base_url = blog_config["base_url"]

    # Fetch full post content
    full_post = blog_fetcher.fetch_full_post(blog_config["api_url"], slug)
    if not full_post:
        logger.error("Could not fetch full post for %s, skipping", slug)
        return None

    # Prepare data for content generation
    plain_text = blog_fetcher.html_to_plain_text(full_post.get("html_content", ""))
    blog_url = f"{base_url}/blog/{slug}"
    meta_desc = full_post.get("meta_description", "")

    # Generate with quality check (retries once on failure)
    generated_text = _generate_with_quality_check(
        platform, title, meta_desc, blog_url, plain_text,
        gemini_config, other_posts,
    )

    if not generated_text:
        logger.error("Content generation failed for %s/%s, skipping", slug, platform)
        db.mark_failed(slug, platform, "Failed pre-publish quality check")
        return None

    # Mark as pending in DB
    db.mark_pending(slug, platform, generated_text, "now")

    if dry_run:
        logger.info("=== DRY RUN: %s / %s ===", platform.upper(), title)
        print(f"\n{'='*60}")
        print(f"Platform: {platform.upper()}")
        print(f"Blog: {title}")
        print(f"URL: {blog_url}")
        print(f"{'='*60}")
        print(generated_text)
        print(f"{'='*60}\n")
        return generated_text

    # Download image — detailed logging at each step
    raw_featured_image = full_post.get("featured_image")
    logger.info("%s: raw featured_image field: %r", platform, raw_featured_image)

    image_url = blog_fetcher.get_full_image_url(base_url, raw_featured_image)
    logger.info("%s: resolved image URL: %s", platform, image_url)

    image_data = blog_fetcher.download_image(image_url) if image_url else None
    if image_data:
        logger.info("%s: image downloaded for %s (%d bytes), will attach", platform, slug, len(image_data))
    elif image_url:
        logger.warning("%s: image download failed for %s, posting without image", platform, slug)
    else:
        logger.info("%s: no featured image for %s, posting text-only", platform, slug)

    # Publish
    logger.info("%s: publishing with image_data=%s, image_url=%s", platform, image_data is not None, image_url)
    success = _publish_to_platform(platform, credentials, generated_text, image_data, image_url)

    if success:
        db.mark_published(slug, platform)
    else:
        db.mark_failed(slug, platform, "Publishing failed")

    return generated_text


def _publish_to_platform(
    platform: str,
    credentials: dict,
    text: str,
    image_data: bytes | None,
    image_url: str | None,
) -> bool:
    """Dispatch publishing to the correct platform module."""
    try:
        if platform == "linkedin":
            creds = credentials["linkedin"]
            return linkedin.publish(
                access_token=creds["access_token"],
                person_urn=creds["person_urn"],
                text=text,
                image_data=image_data,
            )
        elif platform == "facebook":
            creds = credentials["facebook"]
            return facebook.publish(
                page_id=creds["page_id"],
                page_access_token=creds["page_access_token"],
                text=text,
                image_url=image_url,
            )
        elif platform == "x":
            creds = credentials["x"]
            return twitter.publish(
                api_key=creds["api_key"],
                api_secret=creds["api_secret"],
                access_token=creds["access_token"],
                access_token_secret=creds["access_token_secret"],
                text=text,
                image_data=image_data,
            )
        else:
            logger.error("Unknown platform: %s", platform)
            return False
    except Exception as e:
        logger.error("Publish error for %s: %s", platform, e, exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(description="Social media auto-poster for PowerDataChat")
    parser.add_argument("--once", action="store_true", help="Run a single cycle then exit")
    parser.add_argument("--dry-run", action="store_true", help="Generate content but don't publish")
    args = parser.parse_args()

    config = load_config()
    setup_logging(config)

    logger.info("Social Poster starting up")

    # Restore DB from GCS if running in Cloud Run
    db.sync_from_gcs()

    credentials = get_credentials()
    active_platforms = check_platform_credentials(credentials)

    if not any(active_platforms.values()) and not args.dry_run:
        logger.warning("No platforms have valid credentials configured. Nothing to do.")
        # In dry-run mode, we still generate content even without platform credentials
        if not args.dry_run:
            sys.exit(0)

    # In dry-run mode, mark all platforms as active for generation purposes
    if args.dry_run:
        active_platforms = {p: True for p in ["linkedin", "facebook", "x"]}
        logger.info("Dry-run mode: all platforms enabled for content generation")

    check_interval = config["schedule"].get("check_interval_hours", 6)

    if args.once or args.dry_run:
        logger.info("Running single cycle (once=%s, dry_run=%s)", args.once, args.dry_run)
        run_cycle(config, credentials, active_platforms, dry_run=args.dry_run)
        db.sync_to_gcs()
        logger.info("Cycle complete, exiting")
    else:
        logger.info("Starting continuous loop (interval: %d hours)", check_interval)
        while True:
            try:
                run_cycle(config, credentials, active_platforms, dry_run=False)
                db.sync_to_gcs()
            except Exception as e:
                logger.error("Cycle error (will retry next interval): %s", e, exc_info=True)

            logger.info("Sleeping for %d hours until next cycle", check_interval)
            time.sleep(check_interval * 3600)


if __name__ == "__main__":
    main()
