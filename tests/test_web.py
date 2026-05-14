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


class TestDelete:
    def test_delete(self, client_with_scan):
        res = client_with_scan.delete("/api/scans/1")
        assert res.status_code == 200
        assert res.json()["deleted"] == 1
        # Verify gone
        res = client_with_scan.get("/api/scans/1")
        assert res.status_code == 404

    def test_delete_not_found(self, client):
        res = client.delete("/api/scans/999")
        assert res.status_code == 404


class TestFikenPost:
    @pytest.fixture
    def client_approved_no_date(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = _make_conn(db_path)
        from bilagbot.database import update_scan_status
        insert_scan(
            conn, file_path="/tmp/test.pdf", file_hash="xyz",
            supplier_org_number="988312495", supplier_name="Telenor",
            total_amount=599.0, vat_amount=119.8, currency="NOK",
            invoice_date=None, due_date=None,
            invoice_number="INV-001", match_level="KNOWN",
            account_code="6900", vat_code="1", raw_claude_json="{}",
        )
        update_scan_status(conn, 1, "APPROVED")
        conn.close()
        with patch("bilagbot.web.get_connection", side_effect=lambda: _make_conn(db_path)):
            with TestClient(app) as c:
                yield c

    def test_post_missing_invoice_date_returns_400(self, client_approved_no_date):
        res = client_approved_no_date.post("/api/scans/1/fiken")
        assert res.status_code == 400
        assert "fakturadato" in res.json()["detail"].lower()


class TestUpload:
    def test_unsupported_type(self, client):
        res = client.post("/api/scan", files={"file": ("test.docx", b"dummy", "application/octet-stream")})
        assert res.status_code == 400


class TestSanitizeFilename:
    """Tester for _safe_filename()-hjelperfunksjon."""

    def test_strips_relative_path_traversal(self):
        from bilagbot.web import _safe_filename
        result = _safe_filename("../../etc/passwd.pdf")
        assert ".." not in result
        assert "/" not in result
        assert result.endswith(".pdf")

    def test_strips_absolute_posix_path(self):
        from bilagbot.web import _safe_filename
        result = _safe_filename("/etc/passwd.pdf")
        assert result == "passwd.pdf"

    def test_strips_windows_backslash_traversal(self):
        from bilagbot.web import _safe_filename
        result = _safe_filename("..\\..\\windows\\evil.pdf")
        assert ".." not in result
        assert "\\" not in result

    def test_none_returns_nonempty(self):
        from bilagbot.web import _safe_filename
        result = _safe_filename(None)
        assert result and len(result) > 0

    def test_empty_string_returns_nonempty(self):
        from bilagbot.web import _safe_filename
        result = _safe_filename("")
        assert result and len(result) > 0

    def test_dotdot_only_returns_nonempty(self):
        from bilagbot.web import _safe_filename
        result = _safe_filename("..")
        assert result and ".." not in result

    def test_special_chars_replaced(self):
        from bilagbot.web import _safe_filename
        result = _safe_filename("faktura!@#$%.pdf")
        for ch in "!@#$%":
            assert ch not in result
        assert result.endswith(".pdf")

    def test_normal_filename_unchanged(self):
        from bilagbot.web import _safe_filename
        assert _safe_filename("faktura-2025-01.pdf") == "faktura-2025-01.pdf"

    def test_null_byte_stripped(self):
        from bilagbot.web import _safe_filename
        result = _safe_filename("safe.pdf\x00../../etc/passwd")
        assert "\x00" not in result
        assert ".." not in result

    def test_length_capped(self):
        from bilagbot.web import _safe_filename
        result = _safe_filename("a" * 5000 + ".pdf")
        assert len(result) <= 200


class TestAuth:
    """Tester for HTTP Basic Auth-beskyttelse av API-endepunkter."""

    @pytest.fixture
    def auth_client(self, tmp_path, monkeypatch):
        """Klient med auth aktivert (AUTH_USER/AUTH_PASS satt)."""
        monkeypatch.setattr("bilagbot.web.AUTH_USER", "testuser")
        monkeypatch.setattr("bilagbot.web.AUTH_PASS", "testpass")
        db_path = tmp_path / "test.db"
        conn = _make_conn(db_path)
        insert_scan(
            conn, file_path="/tmp/test.pdf", file_hash="abc123",
            supplier_org_number="988312495", supplier_name="Telenor",
            total_amount=599.0, vat_amount=119.8, currency="NOK",
            invoice_date="2025-01-15", due_date=None,
            invoice_number="INV-001", match_level="UNKNOWN",
            account_code="6900", vat_code="1", raw_claude_json="{}",
        )
        conn.close()
        with patch("bilagbot.web.get_connection", side_effect=lambda: _make_conn(db_path)):
            with TestClient(app) as c:
                yield c

    def test_health_open_without_auth(self, auth_client):
        """Helsesjekken skal vaere aapen ogsaa naar auth er aktivert."""
        res = auth_client.get("/api/health")
        assert res.status_code == 200

    def test_scans_list_requires_auth(self, auth_client):
        """GET /api/scans uten credentials skal returnere 401."""
        res = auth_client.get("/api/scans")
        assert res.status_code == 401

    def test_scan_detail_requires_auth(self, auth_client):
        res = auth_client.get("/api/scans/1")
        assert res.status_code == 401

    def test_approve_requires_auth(self, auth_client):
        res = auth_client.post("/api/scans/1/approve")
        assert res.status_code == 401

    def test_reject_requires_auth(self, auth_client):
        res = auth_client.post("/api/scans/1/reject")
        assert res.status_code == 401

    def test_delete_requires_auth(self, auth_client):
        res = auth_client.delete("/api/scans/1")
        assert res.status_code == 401

    def test_fiken_requires_auth(self, auth_client):
        res = auth_client.post("/api/scans/1/fiken")
        assert res.status_code == 401

    def test_scan_upload_requires_auth(self, auth_client):
        res = auth_client.post("/api/scan", files={"file": ("t.pdf", b"x", "application/pdf")})
        assert res.status_code == 401

    def test_index_requires_auth(self, auth_client):
        res = auth_client.get("/")
        assert res.status_code == 401

    def test_wrong_password_returns_401(self, auth_client):
        res = auth_client.get("/api/scans", auth=("testuser", "feilpassord"))
        assert res.status_code == 401

    def test_wrong_username_returns_401(self, auth_client):
        res = auth_client.get("/api/scans", auth=("feilbruker", "testpass"))
        assert res.status_code == 401

    def test_correct_credentials_returns_200(self, auth_client):
        res = auth_client.get("/api/scans", auth=("testuser", "testpass"))
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_correct_credentials_on_detail(self, auth_client):
        res = auth_client.get("/api/scans/1", auth=("testuser", "testpass"))
        assert res.status_code == 200

    def test_auth_disabled_when_unset(self, client):
        """Naar AUTH_USER/AUTH_PASS er tomme, skal endepunkter vaere aapne (dev-modus)."""
        res = client.get("/api/scans")
        assert res.status_code == 200


class TestUploadSecurity:
    """E2E-tester for sikker filhåndtering i upload-endepunktet."""

    def _mock_scan_success(self, tmp_path):
        """Returnerer kontekstmgr-patch-stack for en vellykket scan."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from bilagbot.models import InvoiceData

        dummy_invoice = InvoiceData(vendor_name="Test AS")
        dummy_json = '{"vendor_name": "Test AS"}'
        mock_result = MagicMock()
        mock_result.match_level.value = "UNKNOWN"
        mock_result.supplier_name = "Test AS"
        mock_result.account_code = None
        mock_result.vat_code = None
        mock_to_thread = AsyncMock(return_value=(dummy_invoice, dummy_json))
        return (
            patch("asyncio.to_thread", mock_to_thread),
            patch("bilagbot.web.scan_file"),
            patch("bilagbot.web.ensure_data_dir"),
            patch("bilagbot.web.file_hash", return_value="uniquehash_traversal"),
            patch("bilagbot.web.find_duplicate", return_value=None),
            patch("bilagbot.web.classify", return_value=mock_result),
            patch("bilagbot.web.insert_scan", return_value=1),
            patch("bilagbot.web.get_scan", return_value={"id": 1, "status": "PENDING"}),
            patch("bilagbot.web.UPLOAD_DIR", tmp_path),
        )

    def test_relative_path_traversal_stays_in_upload_dir(self, client, tmp_path):
        """Filnavn med '../' skal saniteres og filen skal havne i UPLOAD_DIR."""
        patches = self._mock_scan_success(tmp_path)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8]:
            res = client.post(
                "/api/scan",
                files={"file": ("../../evil.pdf", b"%PDF-1.4", "application/pdf")},
            )
        assert res.status_code == 200
        assert not (tmp_path.parent / "evil.pdf").exists(), \
            "Filen skal ikke havne utenfor UPLOAD_DIR"
        uploaded = list(tmp_path.glob("*.pdf"))
        assert len(uploaded) == 1, "Sanitert fil skal ligge i UPLOAD_DIR"
        assert ".." not in uploaded[0].name

    def test_absolute_path_filename_stays_in_upload_dir(self, client, tmp_path):
        """Filnavn med absolutt sti ('/etc/passwd.pdf') skal saniteres til UPLOAD_DIR."""
        patches = self._mock_scan_success(tmp_path)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8]:
            res = client.post(
                "/api/scan",
                files={"file": ("/etc/passwd.pdf", b"%PDF-1.4", "application/pdf")},
            )
        assert res.status_code == 200
        from pathlib import Path
        assert not Path("/etc/passwd_uploaded.pdf").exists(), \
            "Filen skal ikke skrives til /etc/"
        uploaded = list(tmp_path.glob("*.pdf"))
        assert len(uploaded) == 1, "Sanitert fil skal ligge i UPLOAD_DIR"
        assert uploaded[0].name == "passwd.pdf"


class TestGetDbDependency:
    """Tester for get_db() FastAPI-dependency."""

    def test_get_db_yields_connection(self, tmp_path):
        """get_db() skal yielde en åpen sqlite3.Connection."""
        db_path = tmp_path / "dep_test.db"
        _make_conn(db_path).close()
        with patch("bilagbot.web.get_connection", side_effect=lambda: _make_conn(db_path)):
            from bilagbot.web import get_db
            gen = get_db()
            conn = next(gen)
            assert isinstance(conn, sqlite3.Connection)
            try:
                next(gen)
            except StopIteration:
                pass

    def test_get_db_closes_connection_after_request(self, tmp_path):
        """get_db() skal lukke tilkoblingen etter at generatoren er uttømt."""
        from unittest.mock import MagicMock
        mock_conn = MagicMock(spec=sqlite3.Connection)
        with patch("bilagbot.web.get_connection", return_value=mock_conn):
            from bilagbot.web import get_db
            gen = get_db()
            next(gen)
            mock_conn.close.assert_not_called()
            try:
                next(gen)
            except StopIteration:
                pass
            mock_conn.close.assert_called_once()

    def test_get_db_closes_connection_on_exception(self, tmp_path):
        """get_db() skal lukke tilkoblingen selv om et unntak kastes inne i endepunktet."""
        from unittest.mock import MagicMock
        mock_conn = MagicMock(spec=sqlite3.Connection)
        with patch("bilagbot.web.get_connection", return_value=mock_conn):
            from bilagbot.web import get_db
            gen = get_db()
            next(gen)
            try:
                gen.throw(RuntimeError("simulated error"))
            except RuntimeError:
                pass
            mock_conn.close.assert_called_once()

    def test_endpoints_use_get_db_via_depends(self, client_with_scan):
        """Alle endepunkter skal fungere via get_db dependency (regresjonstest)."""
        assert client_with_scan.get("/api/scans").status_code == 200
        assert client_with_scan.get("/api/scans/1").status_code == 200
        assert client_with_scan.post("/api/scans/1/approve").status_code == 200
        assert client_with_scan.get("/api/scans/1").json()["status"] == "APPROVED"


class TestScanAsync:
    def test_scan_delegates_to_asyncio_thread(self, client, tmp_path):
        """api_scan bruker asyncio.to_thread() for scan_file() for ikke å blokkere event loop."""
        from unittest.mock import AsyncMock, MagicMock

        from bilagbot.models import InvoiceData

        dummy_invoice = InvoiceData(vendor_name="Test AS")
        dummy_json = '{"vendor_name": "Test AS"}'

        mock_result = MagicMock()
        mock_result.match_level.value = "UNKNOWN"
        mock_result.supplier_name = "Test AS"
        mock_result.account_code = None
        mock_result.vat_code = None

        mock_to_thread = AsyncMock(return_value=(dummy_invoice, dummy_json))

        with patch("asyncio.to_thread", mock_to_thread), \
             patch("bilagbot.web.scan_file"), \
             patch("bilagbot.web.ensure_data_dir"), \
             patch("bilagbot.web.file_hash", return_value="uniquehash999"), \
             patch("bilagbot.web.find_duplicate", return_value=None), \
             patch("bilagbot.web.classify", return_value=mock_result), \
             patch("bilagbot.web.insert_scan", return_value=42), \
             patch("bilagbot.web.get_scan", return_value={"id": 42, "status": "PENDING"}), \
             patch("bilagbot.web.UPLOAD_DIR", tmp_path):
            res = client.post(
                "/api/scan",
                files={"file": ("faktura.pdf", b"%PDF-1.4", "application/pdf")},
            )

        assert res.status_code == 200
        assert mock_to_thread.called, "scan_file() delegeres ikke til asyncio.to_thread()"
