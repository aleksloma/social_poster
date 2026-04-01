"""Tests for scheduler module."""

import sys
import os
from datetime import datetime
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scheduler


class TestGetNextPostTime:
    def test_next_tuesday(self):
        # Monday at 10:00 UTC, config says Tuesday at 14:00
        now = datetime(2026, 3, 30, 10, 0, 0)  # Monday
        config = {"days": [1, 3], "post_hour_utc": 14}  # Tue, Thu

        result = scheduler.get_next_post_time(config, now=now)
        assert result is not None
        assert result.weekday() == 1  # Tuesday
        assert result.hour == 14

    def test_today_if_before_post_hour(self):
        # Tuesday at 10:00, post hour is 14:00
        now = datetime(2026, 3, 31, 10, 0, 0)  # Tuesday
        config = {"days": [1], "post_hour_utc": 14}

        result = scheduler.get_next_post_time(config, now=now)
        assert result is not None
        assert result.day == 31  # Same day
        assert result.hour == 14

    def test_skip_today_if_past_post_hour(self):
        # Tuesday at 16:00, post hour is 14:00 — should skip to next Tuesday
        now = datetime(2026, 3, 31, 16, 0, 0)  # Tuesday
        config = {"days": [1], "post_hour_utc": 14}

        result = scheduler.get_next_post_time(config, now=now)
        assert result is not None
        assert result.day == 7  # Next Tuesday (April 7)
        assert result.hour == 14

    def test_empty_days_returns_none(self):
        config = {"days": [], "post_hour_utc": 14}
        result = scheduler.get_next_post_time(config, now=datetime(2026, 3, 30, 10, 0, 0))
        assert result is None

    def test_multiple_days(self):
        # Wednesday at 10:00, config says Mon/Wed/Fri
        now = datetime(2026, 4, 1, 10, 0, 0)  # Wednesday
        config = {"days": [0, 2, 4], "post_hour_utc": 16}

        result = scheduler.get_next_post_time(config, now=now)
        assert result is not None
        assert result.weekday() == 2  # Wednesday (today, before post hour)
        assert result.hour == 16


class TestShouldPostNow:
    def test_matching_day_and_hour(self):
        now = datetime(2026, 3, 31, 14, 30, 0)  # Tuesday at 14:30
        config = {"days": [1], "post_hour_utc": 14}
        assert scheduler.should_post_now(config, now=now) is True

    def test_wrong_day(self):
        now = datetime(2026, 3, 30, 14, 0, 0)  # Monday
        config = {"days": [1], "post_hour_utc": 14}  # Tuesday
        assert scheduler.should_post_now(config, now=now) is False

    def test_wrong_hour(self):
        now = datetime(2026, 3, 31, 10, 0, 0)  # Tuesday at 10:00
        config = {"days": [1], "post_hour_utc": 14}
        assert scheduler.should_post_now(config, now=now) is False

    def test_empty_days(self):
        now = datetime(2026, 3, 31, 14, 0, 0)
        config = {"days": [], "post_hour_utc": 14}
        assert scheduler.should_post_now(config, now=now) is False


class TestAssignPostsToPlatforms:
    @patch("scheduler.db")
    def test_assigns_to_active_platforms(self, mock_db):
        mock_db.get_post_count_this_week.return_value = 0
        mock_db.is_posted.return_value = False

        posts = [
            {"slug": "post-1", "title": "Post 1"},
            {"slug": "post-2", "title": "Post 2"},
            {"slug": "post-3", "title": "Post 3"},
        ]
        schedule_config = {
            "linkedin": {"posts_per_week": 2, "days": [1, 3]},
            "facebook": {"posts_per_week": 3, "days": [0, 2, 4]},
            "x": {"posts_per_week": 2, "days": [1, 4]},
        }
        active = {"linkedin": True, "facebook": True, "x": True}

        result = scheduler.assign_posts_to_platforms(posts, schedule_config, active)
        assert "linkedin" in result
        assert "facebook" in result
        assert "x" in result
        assert len(result["linkedin"]) <= 2
        assert len(result["facebook"]) <= 3
        assert len(result["x"]) <= 2

    @patch("scheduler.db")
    def test_skips_inactive_platforms(self, mock_db):
        mock_db.get_post_count_this_week.return_value = 0
        mock_db.is_posted.return_value = False

        posts = [{"slug": "post-1", "title": "Post 1"}]
        schedule_config = {
            "linkedin": {"posts_per_week": 2},
            "facebook": {"posts_per_week": 3},
            "x": {"posts_per_week": 2},
        }
        active = {"linkedin": False, "facebook": True, "x": False}

        result = scheduler.assign_posts_to_platforms(posts, schedule_config, active)
        assert "linkedin" not in result
        assert "x" not in result
        assert "facebook" in result

    @patch("scheduler.db")
    def test_skips_already_posted(self, mock_db):
        mock_db.get_post_count_this_week.return_value = 0
        mock_db.is_posted.return_value = True  # All already posted

        posts = [{"slug": "post-1"}, {"slug": "post-2"}]
        schedule_config = {"linkedin": {"posts_per_week": 2}}
        active = {"linkedin": True, "facebook": False, "x": False}

        result = scheduler.assign_posts_to_platforms(posts, schedule_config, active)
        assert "linkedin" not in result  # No eligible posts

    @patch("scheduler.db")
    def test_respects_weekly_quota(self, mock_db):
        mock_db.get_post_count_this_week.return_value = 2  # Already at quota
        mock_db.is_posted.return_value = False

        posts = [{"slug": "post-1"}]
        schedule_config = {"linkedin": {"posts_per_week": 2}}
        active = {"linkedin": True, "facebook": False, "x": False}

        result = scheduler.assign_posts_to_platforms(posts, schedule_config, active)
        assert "linkedin" not in result  # Quota reached


class TestDistributePostsRoundRobin:
    @patch("scheduler.db")
    def test_distributes_evenly(self, mock_db):
        mock_db.get_post_count_this_week.return_value = 0
        mock_db.is_posted.return_value = False

        posts = [
            {"slug": "post-1"},
            {"slug": "post-2"},
            {"slug": "post-3"},
            {"slug": "post-4"},
            {"slug": "post-5"},
            {"slug": "post-6"},
            {"slug": "post-7"},
        ]
        schedule_config = {
            "linkedin": {"posts_per_week": 2},
            "facebook": {"posts_per_week": 3},
            "x": {"posts_per_week": 2},
        }
        active = {"linkedin": True, "facebook": True, "x": True}

        result = scheduler.distribute_posts_round_robin(posts, schedule_config, active)

        total_assigned = sum(len(p) for p in result.values())
        assert total_assigned == 7  # All posts assigned
        assert len(result.get("linkedin", [])) <= 2
        assert len(result.get("facebook", [])) <= 3
        assert len(result.get("x", [])) <= 2

    @patch("scheduler.db")
    def test_no_active_platforms(self, mock_db):
        posts = [{"slug": "post-1"}]
        schedule_config = {}
        active = {"linkedin": False, "facebook": False, "x": False}

        result = scheduler.distribute_posts_round_robin(posts, schedule_config, active)
        assert result == {}

    @patch("scheduler.db")
    def test_no_posts(self, mock_db):
        mock_db.get_post_count_this_week.return_value = 0
        schedule_config = {"linkedin": {"posts_per_week": 2}}
        active = {"linkedin": True, "facebook": False, "x": False}

        result = scheduler.distribute_posts_round_robin([], schedule_config, active)
        assert result == {}
