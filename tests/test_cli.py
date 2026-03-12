"""Tester for CLI-kommandoer."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from bilagbot.cli import main
from bilagbot.database import get_connection, insert_scan


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
        """Test full scan-flyt med mocket API og in-memory DB."""
        db_path = tmp_path / "test.db"

        mock_text = MagicMock()
        mock_text.text = json.dumps(known_response)
        mock_response = MagicMock()
        mock_response.content = [mock_text]

        with patch("bilagbot.scanner.anthropic.Anthropic") as MockClient, \
             patch("bilagbot.cli.get_connection", return_value=get_connection(db_path=db_path)):
            MockClient.return_value.messages.create.return_value = mock_response
            result = runner.invoke(main, ["scan", str(sample_pdf)])

        assert result.exit_code == 0
        assert "Bilag #1" in result.output
        assert "Telenor" in result.output

    def test_scan_duplicate(self, runner, sample_pdf, known_response, tmp_path):
        """Test at duplikater oppdages."""
        db_path = tmp_path / "test.db"

        mock_text = MagicMock()
        mock_text.text = json.dumps(known_response)
        mock_response = MagicMock()
        mock_response.content = [mock_text]

        with patch("bilagbot.scanner.anthropic.Anthropic") as MockClient, \
             patch("bilagbot.cli.get_connection", side_effect=lambda: get_connection(db_path=db_path)):
            MockClient.return_value.messages.create.return_value = mock_response
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
