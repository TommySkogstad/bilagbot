"""Tester for web-appen (FastAPI)."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bilagbot.database import insert_scan
from bilagbot.web import app

SCHEMA = """
CREATE TABLE IF NOT EXISTS known_suppliers (
    org_number TEXT PRIMARY KEY, supplier_name TEXT NOT NULL,
    account_code TEXT, account_name TEXT, vat_code TEXT,
    auto_approve BOOLEAN DEFAULT FALSE, approval_count INTEGER DEFAULT 0,
    last_seen_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, file_hash TEXT NOT NULL,
    supplier_org_number TEXT, supplier_name TEXT, total_amount REAL, vat_amount REAL,
    currency TEXT DEFAULT 'NOK', invoice_date TEXT, due_date TEXT, invoice_number TEXT,
    match_level TEXT NOT NULL, account_code TEXT, vat_code TEXT, status TEXT NOT NULL DEFAULT 'PENDING',
    raw_claude_json TEXT, scanned_at TEXT NOT NULL, reviewed_at TEXT, posted_at TEXT,
    fiken_purchase_id INTEGER, fiken_posted_at TEXT
);
CREATE TABLE IF NOT EXISTS fiken_accounts (
    code TEXT PRIMARY KEY, name TEXT NOT NULL, last_synced_at TEXT NOT NULL
);
"""


def _make_conn(db_path: Path) -> sqlite3.Connection:
    """Lag SQLite-forbindelse som tillater cross-thread bruk (for testing)."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"
    _make_conn(db_path).close()  # Init schema
    with patch("bilagbot.web.get_connection", side_effect=lambda: _make_conn(db_path)):
        with TestClient(app) as c:
            yield c


@pytest.fixture
def client_with_scan(tmp_path):
    db_path = tmp_path / "test.db"
    conn = _make_conn(db_path)
    insert_scan(
        conn, file_path="/tmp/test.pdf", file_hash="abc123",
        supplier_org_number="988312495", supplier_name="Telenor Norge AS",
        total_amount=599.0, vat_amount=119.8, currency="NOK",
        invoice_date="2025-01-15", due_date="2025-02-15",
        invoice_number="INV-001", match_level="UNKNOWN",
        account_code="6900", vat_code="1", raw_claude_json="{}",
    )
    conn.close()
    with patch("bilagbot.web.get_connection", side_effect=lambda: _make_conn(db_path)):
        with TestClient(app) as c:
            yield c


class TestHealth:
    def test_health(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


class TestIndex:
    def test_index_returns_html(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "BilagBot" in res.text


class TestScans:
    def test_list_empty(self, client):
        res = client.get("/api/scans")
        assert res.status_code == 200
        assert res.json() == []

    def test_list_with_scan(self, client_with_scan):
        res = client_with_scan.get("/api/scans")
        assert res.status_code == 200
        scans = res.json()
        assert len(scans) == 1
        assert scans[0]["supplier_name"] == "Telenor Norge AS"

    def test_filter_by_status(self, client_with_scan):
        res = client_with_scan.get("/api/scans?status=PENDING")
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_filter_empty_status(self, client_with_scan):
        res = client_with_scan.get("/api/scans?status=APPROVED")
        assert res.status_code == 200
        assert len(res.json()) == 0

    def test_detail(self, client_with_scan):
        res = client_with_scan.get("/api/scans/1")
        assert res.status_code == 200
        assert res.json()["supplier_name"] == "Telenor Norge AS"

    def test_detail_not_found(self, client):
        res = client.get("/api/scans/999")
        assert res.status_code == 404


class TestApproveReject:
    def test_approve(self, client_with_scan):
        res = client_with_scan.post("/api/scans/1/approve")
        assert res.status_code == 200
        assert res.json()["status"] == "APPROVED"

    def test_approve_with_override(self, client_with_scan):
        res = client_with_scan.post("/api/scans/1/approve",
                                     json={"account_code": "7100", "vat_code": "11"})
        assert res.status_code == 200
        assert res.json()["account_code"] == "7100"

    def test_reject(self, client_with_scan):
        res = client_with_scan.post("/api/scans/1/reject")
        assert res.status_code == 200
        assert res.json()["status"] == "REJECTED"

    def test_approve_not_found(self, client):
        res = client.post("/api/scans/999/approve")
        assert res.status_code == 404

    def test_double_approve(self, client_with_scan):
        client_with_scan.post("/api/scans/1/approve")
        res = client_with_scan.post("/api/scans/1/approve")
        assert res.status_code == 400


class TestUpload:
    def test_unsupported_type(self, client):
        res = client.post("/api/scan", files={"file": ("test.docx", b"dummy", "application/octet-stream")})
        assert res.status_code == 400
