"""Tester for CLI-kommandoer."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bilagbot.cli import _post_single_invoice, main
from bilagbot.database import get_connection, get_scan, insert_scan, update_scan_status
from bilagbot.exceptions import FikenError


@pytest.fixture
def runner():
    return CliRunner()


class TestVersion:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestScanCommand:
    def test_scan_nonexistent_file(self, runner):
        result = runner.invoke(main, ["scan", "/tmp/ghost_file_does_not_exist.pdf"])
        assert result.exit_code != 0

    def test_scan_empty_dir(self, runner, tmp_path):
        result = runner.invoke(main, ["scan", str(tmp_path)])
        assert "Ingen støttede filer" in result.output

    def test_scan_success(self, runner, sample_pdf, known_response, tmp_path):
        """Test full scan-flyt med mocket CLI og in-memory DB."""
        db_path = tmp_path / "test.db"

        cli_output = json.dumps({"result": json.dumps(known_response)})
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = cli_output
        mock_result.stderr = ""

        with patch("bilagbot.scanner.shutil.which", return_value="/usr/bin/claude"), \
             patch("bilagbot.scanner.subprocess.run", return_value=mock_result), \
             patch("bilagbot.cli.get_connection", return_value=get_connection(db_path=db_path)):
            result = runner.invoke(main, ["scan", str(sample_pdf)])

        assert result.exit_code == 0
        assert "Bilag #1" in result.output
        assert "Telenor" in result.output

    def test_scan_duplicate(self, runner, sample_pdf, known_response, tmp_path):
        """Test at duplikater oppdages."""
        db_path = tmp_path / "test.db"

        cli_output = json.dumps({"result": json.dumps(known_response)})
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = cli_output
        mock_result.stderr = ""

        with patch("bilagbot.scanner.shutil.which", return_value="/usr/bin/claude"), \
             patch("bilagbot.scanner.subprocess.run", return_value=mock_result), \
             patch("bilagbot.cli.get_connection", side_effect=lambda: get_connection(db_path=db_path)):
            runner.invoke(main, ["scan", str(sample_pdf)])
            result = runner.invoke(main, ["scan", str(sample_pdf)])

        assert "Allerede skannet" in result.output


class TestReviewCommand:
    def test_review_empty(self, runner, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("bilagbot.cli.get_connection", return_value=get_connection(db_path=db_path)):
            result = runner.invoke(main, ["review"])
        assert "Ingen ventende" in result.output


class TestApproveReject:
    def _setup_db(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path=db_path)
        insert_scan(
            conn, file_path="/tmp/test.pdf", file_hash="abc",
            supplier_org_number="988312495", supplier_name="Telenor",
            total_amount=599.0, vat_amount=119.8, currency="NOK",
            invoice_date="2025-01-15", due_date="2025-02-15",
            invoice_number="INV-001", match_level="KNOWN",
            account_code="6900", vat_code="1", raw_claude_json="{}",
        )
        return conn

    def test_approve(self, runner, tmp_path):
        conn = self._setup_db(tmp_path)
        with patch("bilagbot.cli.get_connection", return_value=conn):
            result = runner.invoke(main, ["approve", "1"])
        assert result.exit_code == 0
        assert "godkjent" in result.output

    def test_approve_nonexistent(self, runner, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path=db_path)
        with patch("bilagbot.cli.get_connection", return_value=conn):
            result = runner.invoke(main, ["approve", "999"])
        assert "finnes ikke" in result.output

    def test_reject(self, runner, tmp_path):
        conn = self._setup_db(tmp_path)
        with patch("bilagbot.cli.get_connection", return_value=conn):
            result = runner.invoke(main, ["reject", "1"])
        assert result.exit_code == 0
        assert "avvist" in result.output

    def test_approve_with_override(self, runner, tmp_path):
        conn = self._setup_db(tmp_path)
        with patch("bilagbot.cli.get_connection", return_value=conn):
            result = runner.invoke(main, ["approve", "1", "--account", "7100", "--vat", "11"])
        assert result.exit_code == 0
        assert "godkjent" in result.output


class TestStatusCommand:
    def test_status_empty(self, runner, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("bilagbot.cli.get_connection", return_value=get_connection(db_path=db_path)):
            result = runner.invoke(main, ["status"])
        assert "Ingen bilag" in result.output


class TestFikenPostCommand:
    def _setup_approved_scan(self, tmp_path, invoice_date="2025-01-15"):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path=db_path)
        from bilagbot.database import update_scan_status
        scan_id = insert_scan(
            conn, file_path="/tmp/test.pdf", file_hash="abc",
            supplier_org_number="988312495", supplier_name="Telenor",
            total_amount=599.0, vat_amount=119.8, currency="NOK",
            invoice_date=invoice_date, due_date="2025-02-15",
            invoice_number="INV-001", match_level="KNOWN",
            account_code="6900", vat_code="1", raw_claude_json="{}",
        )
        update_scan_status(conn, scan_id, "APPROVED")
        return conn, scan_id

    def test_post_missing_invoice_date_blocks(self, runner, tmp_path):
        conn, scan_id = self._setup_approved_scan(tmp_path, invoice_date=None)
        with patch("bilagbot.cli.get_connection", return_value=conn):
            result = runner.invoke(main, ["fiken", "post", str(scan_id)])
        assert "fakturadato" in result.output.lower()
        assert result.exit_code == 0  # graceful exit, not crash

    def test_post_pending_skips_missing_invoice_date(self, runner, tmp_path):
        conn, _ = self._setup_approved_scan(tmp_path, invoice_date=None)
        with patch("bilagbot.cli.get_connection", return_value=conn):
            result = runner.invoke(main, ["fiken", "post-pending"])
        assert "fakturadato" in result.output.lower()


class TestPostSingleInvoice:
    def _setup_approved_scan(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path=db_path)
        scan_id = insert_scan(
            conn, file_path="/tmp/test.pdf", file_hash="abc",
            supplier_org_number="988312495", supplier_name="Telenor",
            total_amount=599.0, vat_amount=119.8, currency="NOK",
            invoice_date="2025-01-15", due_date="2025-02-15",
            invoice_number="INV-001", match_level="KNOWN",
            account_code="6900", vat_code="1", raw_claude_json="{}",
        )
        update_scan_status(conn, scan_id, "APPROVED")
        return conn, scan_id

    def test_fiken_error_sets_failed_status_and_reraises(self, tmp_path):
        """_post_single_invoice setter status FAILED og re-raiser ved FikenError."""
        conn, scan_id = self._setup_approved_scan(tmp_path)
        row = dict(get_scan(conn, scan_id))

        mock_client = MagicMock()
        mock_client.post_invoice.side_effect = FikenError("Nettverksfeil")

        with pytest.raises(FikenError):
            _post_single_invoice(row, conn, mock_client)

        updated = get_scan(conn, scan_id)
        assert updated["status"] == "FAILED"


class TestSuppliersCommand:
    def test_suppliers_list_empty(self, runner, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("bilagbot.cli.get_connection", return_value=get_connection(db_path=db_path)):
            result = runner.invoke(main, ["suppliers", "list"])
        assert "Ingen kjente" in result.output

    def test_suppliers_edit_nonexistent(self, runner, tmp_path):
        db_path = tmp_path / "test.db"
        with patch("bilagbot.cli.get_connection", return_value=get_connection(db_path=db_path)):
            result = runner.invoke(main, ["suppliers", "edit", "123456789", "--account", "6900"])
        assert "finnes ikke" in result.output


class TestConnectionCleanup:
    """Verifiserer at DB-tilkoblingen alltid lukkes, selv ved uventede exceptions."""

    def test_approve_closes_connection_on_database_error(self, runner):
        """conn.close() kalles selv om learn_from_approval kaster DatabaseError."""
        from bilagbot.exceptions import DatabaseError

        conn_mock = MagicMock()
        mock_scan = {
            "id": 1, "status": "PENDING", "supplier_name": "Telenor",
            "supplier_org_number": "988312495", "account_code": "6900",
            "vat_code": "1", "match_level": "KNOWN",
        }

        with patch("bilagbot.cli.get_connection", return_value=conn_mock), \
             patch("bilagbot.cli.get_scan", return_value=mock_scan), \
             patch("bilagbot.cli.update_scan_status"), \
             patch("bilagbot.cli.update_scan_classification"), \
             patch("bilagbot.cli.learn_from_approval", side_effect=DatabaseError("DB-feil")), \
             patch("bilagbot.cli.get_supplier"):
            runner.invoke(main, ["approve", "1"])

        conn_mock.close.assert_called()

    def test_reject_closes_connection_on_database_error(self, runner):
        """conn.close() kalles selv om update_scan_status kaster DatabaseError."""
        from bilagbot.exceptions import DatabaseError

        conn_mock = MagicMock()
        mock_scan = {"id": 1, "status": "PENDING"}

        with patch("bilagbot.cli.get_connection", return_value=conn_mock), \
             patch("bilagbot.cli.get_scan", return_value=mock_scan), \
             patch("bilagbot.cli.update_scan_status", side_effect=DatabaseError("DB-feil")):
            runner.invoke(main, ["reject", "1"])

        conn_mock.close.assert_called()

    def test_scan_closes_connection_on_database_error(self, runner, sample_pdf):
        """conn.close() kalles selv om find_duplicate kaster DatabaseError."""
        from bilagbot.exceptions import DatabaseError

        conn_mock = MagicMock()

        with patch("bilagbot.cli.get_connection", return_value=conn_mock), \
             patch("bilagbot.cli.find_duplicate", side_effect=DatabaseError("DB-feil")):
            runner.invoke(main, ["scan", str(sample_pdf)])

        conn_mock.close.assert_called()
