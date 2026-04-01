"""SQLite database for tracking posted content.

Ensures idempotency — each blog post is only posted once per platform.

In Cloud Run Jobs the filesystem resets between runs. To persist state,
the DB is synced to/from a GCS bucket when the GCS_BUCKET env var is set.
"""

import os
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent / "social_poster.db"
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
GCS_DB_BLOB = "social_poster.db"


def _gcs_download() -> None:
    """Download the SQLite DB from GCS if it exists. No-op if GCS_BUCKET is unset."""
    if not GCS_BUCKET:
        return

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(GCS_DB_BLOB)
        if blob.exists():
            blob.download_to_filename(str(DB_PATH))
            logger.info("Downloaded DB from gs://%s/%s", GCS_BUCKET, GCS_DB_BLOB)
        else:
            logger.info("No existing DB in gs://%s/%s, starting fresh", GCS_BUCKET, GCS_DB_BLOB)
    except Exception as e:
        logger.warning("GCS download failed, starting with local DB: %s", e)


def _gcs_upload() -> None:
    """Upload the SQLite DB to GCS. No-op if GCS_BUCKET is unset."""
    if not GCS_BUCKET:
        return

    if not DB_PATH.exists():
        logger.warning("No local DB to upload")
        return

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(GCS_DB_BLOB)
        blob.upload_from_filename(str(DB_PATH))
        logger.info("Uploaded DB to gs://%s/%s", GCS_BUCKET, GCS_DB_BLOB)
    except Exception as e:
        logger.error("GCS upload failed: %s", e)


def sync_from_gcs() -> None:
    """Download DB from GCS at startup. Call before any DB operations."""
    _gcs_download()


def sync_to_gcs() -> None:
    """Upload DB to GCS at shutdown. Call after all DB operations complete."""
    _gcs_upload()


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
