"""SQLite database for tracking posted content.

Ensures idempotency — each blog post is only posted once per platform.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent / "social_poster.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database, creating tables if needed."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posted (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blog_slug TEXT NOT NULL,
            platform TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            generated_text TEXT,
            scheduled_for TEXT,
            published_at TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(blog_slug, platform)
        )
    """)
    conn.commit()
    return conn


def is_posted(blog_slug: str, platform: str) -> bool:
    """Check if a blog post has already been posted or is pending for a platform."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM posted WHERE blog_slug = ? AND platform = ?",
            (blog_slug, platform),
        ).fetchone()
        return row is not None and row["status"] in ("published", "pending")
    finally:
        conn.close()


def mark_pending(blog_slug: str, platform: str, generated_text: str, scheduled_for: str) -> None:
    """Record a post as pending (scheduled but not yet published)."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO posted
               (blog_slug, platform, status, generated_text, scheduled_for)
               VALUES (?, ?, 'pending', ?, ?)""",
            (blog_slug, platform, generated_text, scheduled_for),
        )
        conn.commit()
        logger.info("Marked %s/%s as pending (scheduled for %s)", blog_slug, platform, scheduled_for)
    finally:
        conn.close()


def mark_published(blog_slug: str, platform: str) -> None:
    """Mark a post as successfully published."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE posted SET status = 'published', published_at = ?
               WHERE blog_slug = ? AND platform = ?""",
            (datetime.utcnow().isoformat(), blog_slug, platform),
        )
        conn.commit()
        logger.info("Marked %s/%s as published", blog_slug, platform)
    finally:
        conn.close()


def mark_failed(blog_slug: str, platform: str, error: str) -> None:
    """Mark a post as failed with an error message."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE posted SET status = 'failed', error_message = ?
               WHERE blog_slug = ? AND platform = ?""",
            (error, blog_slug, platform),
        )
        conn.commit()
        logger.warning("Marked %s/%s as failed: %s", blog_slug, platform, error)
    finally:
        conn.close()


def get_pending_posts(platform: str) -> list[dict]:
    """Return all pending posts for a given platform."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM posted WHERE platform = ? AND status = 'pending'",
            (platform,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_post_count_this_week(platform: str) -> int:
    """Return how many posts were published this week (Mon-Sun) for a platform."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM posted
               WHERE platform = ? AND status = 'published'
               AND published_at >= date('now', 'weekday 1', '-7 days')""",
            (platform,),
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def reset_failed(blog_slug: str, platform: str) -> None:
    """Remove a failed record so it can be retried."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM posted WHERE blog_slug = ? AND platform = ? AND status = 'failed'",
            (blog_slug, platform),
        )
        conn.commit()
    finally:
        conn.close()
