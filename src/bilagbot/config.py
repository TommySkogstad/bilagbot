"""Konfigurasjon for BilagBot."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Last .env fra current directory eller prosjektrot (ignorerer krypterte filer)
try:
    load_dotenv()
except UnicodeDecodeError:
    pass  # git-crypt-kryptert .env i CI

DATA_DIR = Path(os.getenv("BILAGBOT_DATA_DIR", Path.home() / ".bilagbot"))
DB_PATH = DATA_DIR / "bilag.db"

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "")

AUTO_APPROVE_THRESHOLD = int(os.getenv("AUTO_APPROVE_THRESHOLD", "3"))

# HTTP Basic Auth for web-UI/API. Aktiveres kun naar baade AUTH_USER og AUTH_PASS er satt.
AUTH_USER = os.getenv("AUTH_USER", "")
AUTH_PASS = os.getenv("AUTH_PASS", "")

# Fiken API
FIKEN_API_TOKEN = os.getenv("FIKEN_API_TOKEN", "")
FIKEN_COMPANY_SLUG = os.getenv("FIKEN_COMPANY_SLUG", "")
FIKEN_BASE_URL = "https://api.fiken.no/api/v2"
FIKEN_ENABLED = bool(FIKEN_API_TOKEN and FIKEN_COMPANY_SLUG)


def ensure_data_dir() -> Path:
    """Opprett data-katalog hvis den ikke finnes."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
