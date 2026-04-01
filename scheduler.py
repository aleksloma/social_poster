"""Scheduler — decides which blog posts go to which platforms and when.

Distributes blog posts across platforms based on config.yaml schedule settings.
Ensures each platform gets its configured number of posts per week, distributed
across the configured days.
"""

import logging
from datetime import datetime, timedelta

import db

logger = logging.getLogger(__name__)


def get_next_post_time(platform_config: dict, now: datetime | None = None) -> datetime | None:
    """Calculate the next scheduled post time for a platform.

    Args:
        platform_config: Dict with keys 'days' (list of weekday ints 0-6),
                         'post_hour_utc' (int).
        now: Current UTC datetime (defaults to utcnow).

    Returns:
        Next datetime when a post should go out, or None if no days configured.
    """
    if now is None:
        now = datetime.utcnow()

    days = platform_config.get("days", [])
    hour = platform_config.get("post_hour_utc", 12)

    if not days:
        return None

    current_weekday = now.weekday()

    # Check today and the next 7 days to find the next slot
    for offset in range(8):
        candidate_day = (current_weekday + offset) % 7
        if candidate_day in days:
            candidate_date = now.date() + timedelta(days=offset)
            candidate_time = datetime(
                candidate_date.year, candidate_date.month, candidate_date.day,
                hour, 0, 0,
            )
            # If it's today but past the post hour, skip to next occurrence
            if offset == 0 and now >= candidate_time:
                continue
            return candidate_time

    return None


def should_post_now(platform_config: dict, now: datetime | None = None) -> bool:
    """Check if the current time matches a scheduled posting slot.

    Returns True if today is a posting day AND the current hour matches
    the configured post_hour_utc.
    """
    if now is None:
        now = datetime.utcnow()

    days = platform_config.get("days", [])
    hour = platform_config.get("post_hour_utc", 12)

    return now.weekday() in days and now.hour == hour


def assign_posts_to_platforms(
    blog_posts: list[dict],
    schedule_config: dict,
    active_platforms: dict[str, bool],
) -> dict[str, list[dict]]:
    """Distribute blog posts across active platforms.

    Each platform gets up to posts_per_week new posts. Posts that have already
    been sent to a platform are skipped. Posts are distributed round-robin
    across platforms so not every post goes to every platform.

    Args:
        blog_posts: List of blog post dicts (must have 'slug' key).
        schedule_config: The 'schedule' section from config.yaml.
        active_platforms: Dict mapping platform name to bool (True = active).

    Returns:
        Dict mapping platform name to list of blog posts assigned to it.
    """
    assignments: dict[str, list[dict]] = {}

    for platform in ["linkedin", "facebook", "x"]:
        if not active_platforms.get(platform, False):
            logger.debug("Skipping %s (not active)", platform)
            continue

        platform_config = schedule_config.get(platform, {})
        posts_per_week = platform_config.get("posts_per_week", 2)

        # How many have we already posted this week?
        posted_this_week = db.get_post_count_this_week(platform)
        remaining_slots = max(0, posts_per_week - posted_this_week)

        if remaining_slots == 0:
            logger.info("%s: weekly quota reached (%d/%d)", platform, posted_this_week, posts_per_week)
            continue

        # Filter to posts not yet sent to this platform
        eligible = [
            post for post in blog_posts
            if not db.is_posted(post["slug"], platform)
        ]

        # Take up to remaining_slots posts
        assigned = eligible[:remaining_slots]
        if assigned:
            assignments[platform] = assigned
            logger.info(
                "%s: assigned %d posts (slots: %d, eligible: %d)",
                platform, len(assigned), remaining_slots, len(eligible),
            )
        else:
            logger.info("%s: no new eligible posts", platform)

    return assignments


def distribute_posts_round_robin(
    blog_posts: list[dict],
    schedule_config: dict,
    active_platforms: dict[str, bool],
) -> dict[str, list[dict]]:
    """Distribute posts round-robin so different platforms get different posts.

    This prevents all platforms from posting the exact same blog articles.
    Each blog post is assigned to one or two platforms, cycling through them.

    Args:
        blog_posts: List of blog post dicts (must have 'slug' key).
        schedule_config: The 'schedule' section from config.yaml.
        active_platforms: Dict mapping platform name to bool (True = active).

    Returns:
        Dict mapping platform name to list of blog posts assigned to it.
    """
    platforms = [p for p in ["linkedin", "facebook", "x"] if active_platforms.get(p, False)]
    if not platforms:
        return {}

    # Build capacity for each platform
    capacity = {}
    for platform in platforms:
        platform_config = schedule_config.get(platform, {})
        posts_per_week = platform_config.get("posts_per_week", 2)
        posted_this_week = db.get_post_count_this_week(platform)
        capacity[platform] = max(0, posts_per_week - posted_this_week)

    assignments: dict[str, list[dict]] = {p: [] for p in platforms}
    platform_idx = 0

    for post in blog_posts:
        # Try each platform starting from the current index
        assigned = False
        for _ in range(len(platforms)):
            platform = platforms[platform_idx % len(platforms)]
            platform_idx += 1

            if capacity[platform] <= 0:
                continue
            if db.is_posted(post["slug"], platform):
                continue

            assignments[platform].append(post)
            capacity[platform] -= 1
            assigned = True
            break

        if not assigned:
            logger.debug("No platform slot available for post: %s", post.get("slug"))

    # Remove empty assignments
    assignments = {p: posts for p, posts in assignments.items() if posts}

    for platform, posts in assignments.items():
        logger.info("%s: %d posts assigned via round-robin", platform, len(posts))

    return assignments
