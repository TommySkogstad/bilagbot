"""Tester for review.py — formatering og Rich-visning."""

import io
from unittest.mock import patch

from rich.console import Console

from bilagbot.database import get_scan, insert_scan, upsert_supplier
from bilagbot.review import format_amount, show_pending_list, show_scan_detail, show_status_summary, show_suppliers


def _make_console() -> Console:
    return Console(file=io.StringIO(), highlight=False)


def _insert_scan(conn, *, match_level="KNOWN", total_amount=599.0):
    return insert_scan(
        conn,
        file_path="/tmp/test.pdf",
        file_hash="abc123",
        supplier_org_number="988312495",
        supplier_name="Telenor",
        total_amount=total_amount,
        vat_amount=119.8,
        currency="NOK",
        invoice_date="2025-01-15",
        due_date="2025-02-15",
        invoice_number="INV-001",
        match_level=match_level,
        account_code="6900",
        vat_code="1",
        raw_claude_json="{}",
    )


class TestFormatAmount:
    def test_none_returns_dash(self):
        assert format_amount(None) == "—"

    def test_zero_contains_zero(self):
        result = format_amount(0.0)
        assert "0" in result

    def test_positive_amount_formatted(self):
        result = format_amount(1234.56)
        assert "1 234" in result
        assert "56" in result

    def test_large_amount(self):
        result = format_amount(1000000.0)
        assert "1 000 000" in result


class TestShowScanDetail:
    def test_renders_without_crash(self, db):
        scan_id = _insert_scan(db)
        row = get_scan(db, scan_id)
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_scan_detail(row)
        output = mock_console.file.getvalue()
        assert "Bilag #1" in output

    def test_shows_supplier_name(self, db):
        scan_id = _insert_scan(db)
        row = get_scan(db, scan_id)
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_scan_detail(row)
        output = mock_console.file.getvalue()
        assert "Telenor" in output

    def test_shows_formatted_amount(self, db):
        scan_id = _insert_scan(db, total_amount=1234.56)
        row = get_scan(db, scan_id)
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_scan_detail(row)
        output = mock_console.file.getvalue()
        assert "1 234" in output


class TestShowPendingList:
    def test_empty_returns_empty_list(self, db):
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            result = show_pending_list(db)
        assert result == []
        assert "Ingen ventende" in mock_console.file.getvalue()

    def test_returns_one_row(self, db):
        _insert_scan(db)
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            result = show_pending_list(db)
        assert len(result) == 1

    def test_returns_multiple_rows(self, db):
        _insert_scan(db)
        insert_scan(
            db,
            file_path="/tmp/other.pdf",
            file_hash="def456",
            supplier_org_number=None,
            supplier_name="Ukjent AS",
            total_amount=200.0,
            vat_amount=50.0,
            currency="NOK",
            invoice_date=None,
            due_date=None,
            invoice_number=None,
            match_level="UNKNOWN",
            account_code=None,
            vat_code=None,
            raw_claude_json="{}",
        )
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            result = show_pending_list(db)
        assert len(result) == 2

    def test_match_level_unknown_included(self, db):
        _insert_scan(db, match_level="UNKNOWN")
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            result = show_pending_list(db)
        assert len(result) == 1


class TestShowStatusSummary:
    def test_empty_db_no_crash(self, db):
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_status_summary(db)
        assert "Ingen bilag" in mock_console.file.getvalue()

    def test_with_pending_scan(self, db):
        _insert_scan(db)
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_status_summary(db)
        output = mock_console.file.getvalue()
        assert "PENDING" in output

    def test_totalt_shown(self, db):
        _insert_scan(db)
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_status_summary(db)
        output = mock_console.file.getvalue()
        assert "Totalt" in output

    def test_totalbelop_shown(self, db):
        _insert_scan(db, total_amount=599.0)
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_status_summary(db)
        output = mock_console.file.getvalue()
        assert "599" in output


class TestShowSuppliers:
    def test_empty_no_crash(self, db):
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_suppliers(db)
        assert "Ingen kjente" in mock_console.file.getvalue()

    def test_with_supplier_shows_org_number(self, db):
        upsert_supplier(db, org_number="988312495", supplier_name="Telenor", account_code="6900")
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_suppliers(db)
        output = mock_console.file.getvalue()
        assert "988312495" in output

    def test_with_supplier_shows_name(self, db):
        upsert_supplier(db, org_number="988312495", supplier_name="Telenor", account_code="6900")
        mock_console = _make_console()
        with patch("bilagbot.review.console", mock_console):
            show_suppliers(db)
        output = mock_console.file.getvalue()
        assert "Telenor" in output
