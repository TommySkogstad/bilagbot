"""Tester for scanner (med mocket Claude API)."""

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
    def test_missing_api_key(self, sample_pdf, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        with pytest.raises(ScannerError, match="ANTHROPIC_API_KEY"):
            scan_file(sample_pdf, api_key="")

    def test_nonexistent_file(self, tmp_path):
        with pytest.raises(ScannerError, match="finnes ikke"):
            scan_file(tmp_path / "ghost.pdf", api_key="test-key")

    def test_unsupported_type(self, tmp_path):
        f = tmp_path / "test.docx"
        f.write_bytes(b"dummy")
        with pytest.raises(ScannerError, match="støttes ikke"):
            scan_file(f, api_key="test-key")

    def test_successful_scan(self, sample_pdf, known_response):
        """Test scan med mocket Claude API."""
        mock_text = MagicMock()
        mock_text.text = json.dumps(known_response)
        mock_response = MagicMock()
        mock_response.content = [mock_text]

        with patch("bilagbot.scanner.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            invoice, raw_json = scan_file(sample_pdf, api_key="test-key")

        assert isinstance(invoice, InvoiceData)
        assert invoice.vendor_name == "Telenor Norge AS"
        assert invoice.total_amount == 599.0
        assert json.loads(raw_json)["vendor_org_number"] == "988312495"

    def test_api_error(self, sample_pdf):
        """Test at API-feil wrapes som ScannerError."""
        import anthropic

        with patch("bilagbot.scanner.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.side_effect = anthropic.APIError(
                message="Rate limited", request=MagicMock(), body=None
            )
            with pytest.raises(ScannerError, match="Claude API-feil"):
                scan_file(sample_pdf, api_key="test-key")
