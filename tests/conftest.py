"""Pytest fixtures for BilagBot."""

import json
from pathlib import Path

import pytest

from bilagbot.database import get_connection
from bilagbot.models import InvoiceData

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def db():
    """In-memory SQLite database."""
    conn = get_connection(db_path=":memory:")
    yield conn
    conn.close()


@pytest.fixture
def known_response() -> dict:
    """Claude-respons for kjent leverandør."""
    return json.loads((FIXTURES_DIR / "claude_response_known.json").read_text())


@pytest.fixture
def unknown_response() -> dict:
    """Claude-respons for ukjent leverandør."""
    return json.loads((FIXTURES_DIR / "claude_response_unknown.json").read_text())


@pytest.fixture
def known_invoice(known_response) -> InvoiceData:
    """InvoiceData fra kjent leverandør."""
    return InvoiceData(**known_response)


@pytest.fixture
def unknown_invoice(unknown_response) -> InvoiceData:
    """InvoiceData fra ukjent leverandør."""
    return InvoiceData(**unknown_response)


@pytest.fixture
def sample_pdf(tmp_path) -> Path:
    """Opprett en minimal test-PDF."""
    pdf = tmp_path / "test.pdf"
    # Minimal gyldig PDF
    pdf.write_bytes(
        b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
    )
    return pdf
