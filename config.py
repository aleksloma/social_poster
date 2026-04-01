"""Configuration loader for social-poster.

Loads settings from config.yaml and environment variables from .env file.
"""

import os
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def load_config() -> dict:
    """Load and return the config.yaml as a dictionary."""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def setup_logging(config: dict) -> None:
    """Configure logging to console and file based on config."""
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    log_file = log_cfg.get("file", "social_poster.log")

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler(BASE_DIR / log_file)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


def get_credentials() -> dict:
    """Return all credentials from environment, grouped by platform.

    Returns a dict with keys: 'gemini', 'linkedin', 'facebook', 'x'.
    Each value is a dict of credential key-value pairs.
    Missing or empty values are returned as empty strings.
    """
    def env(key: str) -> str:
        return os.environ.get(key, "").strip()

    return {
        "gemini": {
            "api_key": env("GEMINI_API_KEY"),
        },
        "linkedin": {
            "access_token": env("LINKEDIN_ACCESS_TOKEN"),
            "person_urn": env("LINKEDIN_PERSON_URN"),
            "client_id": env("LINKEDIN_CLIENT_ID"),
            "client_secret": env("LINKEDIN_CLIENT_SECRET"),
        },
        "facebook": {
            "page_id": env("FACEBOOK_PAGE_ID"),
            "page_access_token": env("FACEBOOK_PAGE_ACCESS_TOKEN"),
            "app_id": env("FACEBOOK_APP_ID"),
            "app_secret": env("FACEBOOK_APP_SECRET"),
        },
        "x": {
            "api_key": env("X_API_KEY"),
            "api_secret": env("X_API_SECRET"),
            "access_token": env("X_ACCESS_TOKEN"),
            "access_token_secret": env("X_ACCESS_TOKEN_SECRET"),
        },
    }


def check_platform_credentials(credentials: dict) -> dict[str, bool]:
    """Check which platforms have valid credentials configured.

    Returns a dict mapping platform name to bool (True = credentials present).
    LinkedIn requires access_token + person_urn.
    Facebook requires page_id + page_access_token.
    X requires all 4 OAuth keys.
    """
    logger = logging.getLogger(__name__)

    linkedin_creds = credentials["linkedin"]
    linkedin_ok = bool(
        linkedin_creds["access_token"] and linkedin_creds["person_urn"]
    )

    facebook_creds = credentials["facebook"]
    facebook_ok = bool(
        facebook_creds["page_id"] and facebook_creds["page_access_token"]
    )

    x_creds = credentials["x"]
    x_ok = bool(
        x_creds["api_key"]
        and x_creds["api_secret"]
        and x_creds["access_token"]
        and x_creds["access_token_secret"]
    )

    platforms = {
        "linkedin": linkedin_ok,
        "facebook": facebook_ok,
        "x": x_ok,
    }

    for platform, is_active in platforms.items():
        if is_active:
            logger.info("%s: credentials configured, platform ACTIVE", platform.capitalize())
        else:
            logger.warning("%s: credentials not configured, skipping", platform.capitalize())

    return platforms
