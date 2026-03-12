"""Konfigurasjon for BilagBot."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Last .env fra current directory eller prosjektrot
load_dotenv()

DATA_DIR = Path(os.getenv("BILAGBOT_DATA_DIR", Path.home() / ".bilagbot"))
DB_PATH = DATA_DIR / "bilag.db"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250514")

AUTO_APPROVE_THRESHOLD = int(os.getenv("AUTO_APPROVE_THRESHOLD", "3"))


def ensure_data_dir() -> Path:
    """Opprett data-katalog hvis den ikke finnes."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
