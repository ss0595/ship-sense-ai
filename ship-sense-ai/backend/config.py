"""Configuration helpers.

Secrets are read from environment variables or a local `.env` file. The `.env`
file is intentionally ignored by git so API keys are not committed.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines into the process environment if not already set."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def key_configured(name: str) -> bool:
    """Return True when an environment variable has a non-empty value."""
    return bool(os.getenv(name, "").strip())
