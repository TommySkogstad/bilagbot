"""Tester for scanner (med mocket Claude CLI)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from bilagbot.exceptions import ScannerError
from bilagbot.models import InvoiceData
from bilagbot.scanner import detect_mime_type, file_hash, scan_file


class TestFileHash:
    def test_hash_consistent(self, sample_pdf):
        h1 = file_hash(sample_pdf)
        h2 = file_hash(sample_pdf)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_different_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"hello")
        f2.write_bytes(b"world")
        assert file_hash(f1) != file_hash(f2)


class TestDetectMimeType:
    @pytest.mark.parametrize("suffix,expected", [
        (".pdf", "application/pdf"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".png", "image/png"),
    ])
    def test_known_types(self, tmp_path, suffix, expected):
        f = tmp_path / f"test{suffix}"
        f.write_bytes(b"dummy")
        assert detect_mime_type(f) == expected


class TestScanFile:
    def test_missing_cli(self, sample_pdf):
        with patch("bilagbot.scanner.shutil.which", return_value=None):
            with pytest.raises(ScannerError, match="Claude CLI er ikke installert"):
                scan_file(sample_pdf)

    def test_nonexistent_file(self, tmp_path):
        with patch("bilagbot.scanner.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(ScannerError, match="finnes ikke"):
                scan_file(tmp_path / "ghost.pdf")

    def test_unsupported_type(self, tmp_path):
        f = tmp_path / "test.docx"
        f.write_bytes(b"dummy")
        with patch("bilagbot.scanner.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(ScannerError, match="stottes ikke"):
                scan_file(f)

    def test_successful_scan(self, sample_pdf, known_response):
        """Test scan med mocket Claude CLI."""
        cli_output = json.dumps({"result": json.dumps(known_response)})
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = cli_output
        mock_result.stderr = ""

        with patch("bilagbot.scanner.shutil.which", return_value="/usr/bin/claude"), \
             patch("bilagbot.scanner.subprocess.run", return_value=mock_result):
            invoice, raw_json = scan_file(sample_pdf)

        assert isinstance(invoice, InvoiceData)
        assert invoice.vendor_name == "Telenor Norge AS"
        assert invoice.total_amount == 599.0
        assert json.loads(raw_json)["vendor_org_number"] == "988312495"

    def test_successful_scan_raw_json(self, sample_pdf, known_response):
        """Test scan der CLI returnerer ren JSON (uten result-wrapper)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(known_response)
        mock_result.stderr = ""

        with patch("bilagbot.scanner.shutil.which", return_value="/usr/bin/claude"), \
             patch("bilagbot.scanner.subprocess.run", return_value=mock_result):
            invoice, raw_json = scan_file(sample_pdf)

        assert isinstance(invoice, InvoiceData)
        assert invoice.vendor_name == "Telenor Norge AS"

    def test_successful_scan_markdown_wrapped(self, sample_pdf, known_response):
        """Test scan der CLI returnerer JSON wrappet i markdown code block."""
        wrapped = f"```json\n{json.dumps(known_response)}\n```"
        cli_output = json.dumps({"result": wrapped})
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = cli_output
        mock_result.stderr = ""

        with patch("bilagbot.scanner.shutil.which", return_value="/usr/bin/claude"), \
             patch("bilagbot.scanner.subprocess.run", return_value=mock_result):
            invoice, raw_json = scan_file(sample_pdf)

        assert isinstance(invoice, InvoiceData)
        assert invoice.vendor_name == "Telenor Norge AS"

    def test_cli_error(self, sample_pdf):
        """Test at CLI-feil wrapes som ScannerError."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: authentication failed"

        with patch("bilagbot.scanner.shutil.which", return_value="/usr/bin/claude"), \
             patch("bilagbot.scanner.subprocess.run", return_value=mock_result):
            with pytest.raises(ScannerError, match="Claude CLI feilet"):
                scan_file(sample_pdf)

    def test_cli_timeout(self, sample_pdf):
        """Test at timeout wrapes som ScannerError."""
        import subprocess

        with patch("bilagbot.scanner.shutil.which", return_value="/usr/bin/claude"), \
             patch("bilagbot.scanner.subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 120)):
            with pytest.raises(ScannerError, match="tidsavbrudd"):
                scan_file(sample_pdf)
