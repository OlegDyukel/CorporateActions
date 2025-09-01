from __future__ import annotations

"""
Lightweight database utilities.

- Loads DATABASE_URL from .env at the project root.
- Provides a typed SQLAlchemy Engine factory for reuse across modules.

This module has a single responsibility: centralize DB connection creation.
"""

from pathlib import Path
from typing import Optional
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from dotenv import load_dotenv


def _project_root() -> Path:
    """Return the project root directory (the parent of the 'src' folder)."""
    # src/core/db.py -> src -> project root
    return Path(__file__).resolve().parents[2]


def load_env(override: bool = False) -> None:
    """Load environment variables from the project's .env file.

    Args:
        override: If True, variables in .env override existing environment vars.
    """
    env_path = _project_root() / ".env"
    load_dotenv(dotenv_path=env_path, override=override)


def get_database_url(env_var: str = "DATABASE_URL") -> str:
    """Fetch the database URL from the environment.

    Raises:
        RuntimeError: If the URL is missing.
    """
    load_env(override=False)
    url = os.getenv(env_var, "").strip()
    if not url:
        raise RuntimeError(
            f"Environment variable {env_var} is not set. Please configure it in .env."
        )
    return url


def get_engine(url: Optional[str] = None) -> Engine:
    """Create and return a SQLAlchemy Engine using the given or env-provided URL.

    Args:
        url: Optional explicit database URL. If None, reads from DATABASE_URL.

    Returns:
        A SQLAlchemy Engine with pool_pre_ping enabled.
    """
    if url is None:
        url = get_database_url()
    url = _normalize_postgres_url(url)
    engine = create_engine(url, pool_pre_ping=True, future=True)
    return engine


def _normalize_postgres_url(url: str) -> str:
    """Ensure we use the psycopg v3 driver.

    Accepts common variations and rewrites them to 'postgresql+psycopg://'.
    """
    # Handle Heroku-style 'postgres://'
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # Rewrite explicit psycopg2 driver to psycopg
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + url[len("postgresql+psycopg2://"):]
    # If driver not specified, default in SA may try psycopg2; pick psycopg instead
    if url.startswith("postgresql://") and "+" not in url[len("postgresql://"):]:
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url
