"""Resolve env vars with optional fallback to repo-root `.env` (local/dev).

Production (Render, etc.) should set os.environ; fallback helps Docker/local runs.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = REPO_ROOT / ".env"


def get_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if value:
        return value
    try:
        return (dotenv_values(ENV_FILE_PATH).get(name) or "").strip()
    except Exception:  # noqa: BLE001
        return ""
