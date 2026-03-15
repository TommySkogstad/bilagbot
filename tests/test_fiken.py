"""Tester for Fiken API-klient."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bilagbot.exceptions import (
    FikenAuthError,
    FikenError,
    FikenNotFoundError,
    FikenRateLimitError,
    FikenValidationError,
)
from bilagbot.fiken import FikenClient, amount_to_cents, vat_code_to_type

# --- Hjelpefunksjoner ---


class TestVatCodeToType:
    @pytest.mark.parametrize(
        "code,expected",
        [
            ("1", "HIGH"),
            ("3", "HIGH"),
            ("11", "MEDIUM"),
            ("13", "LOW"),
            ("6", "OUTSIDE"),
            ("0", "NONE"),
            ("7", "NONE"),
            ("12", "RAW_FISH"),
            (None, "HIGH"),
            ("999", "HIGH"),
        ],
    )
    def test_mapping(self, code, expected):
        assert vat_code_to_type(code) == expected


class TestAmountToCents:
    @pytest.mark.parametrize(
        "amount,expected",
        [
            (1000.0, 100000),
            (100.12, 10012),
            (0, 0),
            (None, 0),
            (99.999, 10000),
        ],
    )
    def test_conversion(self, amount, expected):
        assert amount_to_cents(amount) == expected


# --- FikenClient fixtures ---


_SENTINEL = object()


def _mock_response(status_code=200, json_data=_SENTINEL, headers=None, text=""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = {} if json_data is _SENTINEL else json_data
    resp.headers = headers or {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code}", request=MagicMock(), response=resp
        )
    return resp


@pytest.fixture
def mock_http():
    return MagicMock(spec=httpx.Client)


@pytest.fixture
def client(mock_http):
    return FikenClient(
        api_token="test-token",
        company_slug="test-company",
        http_client=mock_http,
    )


# --- Init ---


class TestFikenClientInit:
    def test_missing_token(self):
        with patch("bilagbot.fiken.FIKEN_API_TOKEN", ""), patch("bilagbot.fiken.FIKEN_COMPANY_SLUG", ""):
            with pytest.raises(FikenAuthError, match="FIKEN_API_TOKEN"):
                FikenClient(api_token="", company_slug="test")

    def test_missing_slug(self):
        with patch("bilagbot.fiken.FIKEN_API_TOKEN", ""), patch("bilagbot.fiken.FIKEN_COMPANY_SLUG", ""):
            with pytest.raises(FikenError, match="FIKEN_COMPANY_SLUG"):
                FikenClient(api_token="token", company_slug="")


# --- Validate ---


class TestValidate:
    def test_success(self, client, mock_http):
        mock_http.request.return_value = _mock_response(200, {"name": "Test AS", "hasApiAccess": True})
        result = client.validate()
        assert result["name"] == "Test AS"
        assert result["hasApiAccess"] is True

    def test_auth_error(self, client, mock_http):
        mock_http.request.return_value = _mock_response(401)
        with pytest.raises(FikenAuthError):
            client.validate()

    def test_not_found(self, client, mock_http):
        mock_http.request.return_value = _mock_response(404)
        with pytest.raises(FikenNotFoundError):
            client.validate()


# --- Accounts ---


class TestGetAccounts:
    def test_success(self, client, mock_http):
        accounts = [{"code": "6300", "name": "Kontorrekvisita"}, {"code": "6900", "name": "Diverse"}]
        mock_http.request.return_value = _mock_response(200, accounts)
        result = client.get_accounts()
        assert len(result) == 2
        assert result[0]["code"] == "6300"


# --- Contacts ---


class TestContacts:
    def test_find_existing(self, client, mock_http):
        mock_http.request.return_value = _mock_response(200, [{"contactId": 42, "name": "Telia"}])
        result = client.find_contact_by_org_number("915394110")
        assert result["contactId"] == 42

    def test_find_not_found(self, client, mock_http):
        mock_http.request.return_value = _mock_response(200, [])
        result = client.find_contact_by_org_number("000000000")
        assert result is None

    def test_create_contact(self, client, mock_http):
        mock_http.request.return_value = _mock_response(
            201,
            headers={"Location": "https://api.fiken.no/api/v2/companies/test/contacts/99"},
        )
        contact_id = client.create_contact("Ny Leverandør", "123456789")
        assert contact_id == 99

    def test_get_or_create_existing(self, client, mock_http):
        mock_http.request.return_value = _mock_response(200, [{"contactId": 42, "name": "Telia"}])
        contact_id = client.get_or_create_contact("Telia", "915394110")
        assert contact_id == 42

    def test_get_or_create_new(self, client, mock_http):
        # Først find → tom liste, deretter create → 201
        mock_http.request.side_effect = [
            _mock_response(200, []),
            _mock_response(201, headers={"Location": ".../contacts/55"}),
        ]
        contact_id = client.get_or_create_contact("Ny AS", "111222333")
        assert contact_id == 55


# --- Purchases ---


class TestCreatePurchase:
    def test_success(self, client, mock_http):
        mock_http.request.return_value = _mock_response(
            201,
            headers={"Location": "https://api.fiken.no/api/v2/companies/test/purchases/123"},
        )
        purchase_id = client.create_purchase(
            date="2026-03-15",
            account_code="6900",
            vat_code="1",
            gross_amount=50000,
            description="Test kjøp",
        )
        assert purchase_id == 123

        # Verifiser payload
        call_args = mock_http.request.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["date"] == "2026-03-15"
        assert payload["lines"][0]["account"] == "6900"
        assert payload["lines"][0]["vatType"] == "HIGH"
        assert payload["lines"][0]["grossAmount"] == 50000

    def test_with_contact(self, client, mock_http):
        mock_http.request.return_value = _mock_response(
            201,
            headers={"Location": ".../purchases/456"},
        )
        purchase_id = client.create_purchase(
            date="2026-03-15",
            contact_id=42,
            account_code="6300",
            gross_amount=10000,
        )
        assert purchase_id == 456
        payload = mock_http.request.call_args.kwargs.get("json") or mock_http.request.call_args[1].get("json")
        assert payload["supplier"]["contactId"] == 42

    def test_validation_error(self, client, mock_http):
        mock_http.request.return_value = _mock_response(400, text="Missing required field: date")
        with pytest.raises(FikenValidationError, match="Valideringsfeil"):
            client.create_purchase(date="", account_code="6900", gross_amount=100)


# --- Attachments ---


class TestUploadAttachment:
    def test_success(self, client, mock_http, tmp_path):
        test_file = tmp_path / "faktura.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")
        mock_http.request.return_value = _mock_response(201)
        client.upload_attachment(123, test_file)
        assert mock_http.request.called

    def test_file_not_found(self, client, mock_http):
        with pytest.raises(FikenError, match="Fil ikke funnet"):
            client.upload_attachment(123, Path("/finnes/ikke.pdf"))


# --- Post invoice (komplett flyt) ---


class TestPostInvoice:
    def test_full_flow(self, client, mock_http, tmp_path):
        # find_contact → create_contact → create_purchase → upload_attachment
        test_file = tmp_path / "faktura.pdf"
        test_file.write_bytes(b"%PDF test")

        mock_http.request.side_effect = [
            _mock_response(200, []),  # find_contact → ingen
            _mock_response(201, headers={"Location": ".../contacts/10"}),  # create_contact
            _mock_response(201, headers={"Location": ".../purchases/200"}),  # create_purchase
            _mock_response(201),  # upload_attachment
        ]

        purchase_id = client.post_invoice(
            vendor_name="Test AS",
            vendor_org_number="999888777",
            invoice_date="2026-03-01",
            due_date="2026-03-15",
            invoice_number="F-2026-001",
            payment_reference="123456789",
            total_amount=1500.00,
            account_code="6900",
            vat_code="1",
            description="Kontorrekvisita",
            file_path=test_file,
        )

        assert purchase_id == 200
        assert mock_http.request.call_count == 4

    def test_without_attachment(self, client, mock_http):
        mock_http.request.side_effect = [
            _mock_response(200, [{"contactId": 5, "name": "Test"}]),  # find_contact
            _mock_response(201, headers={"Location": ".../purchases/300"}),  # create_purchase
        ]

        purchase_id = client.post_invoice(
            vendor_name="Test AS",
            vendor_org_number="999888777",
            invoice_date="2026-03-01",
            due_date=None,
            invoice_number=None,
            payment_reference=None,
            total_amount=500.00,
            account_code="6300",
            vat_code="11",
            description="Mat",
        )

        assert purchase_id == 300

    def test_attachment_failure_does_not_block(self, client, mock_http, tmp_path):
        test_file = tmp_path / "faktura.pdf"
        test_file.write_bytes(b"%PDF test")

        mock_http.request.side_effect = [
            _mock_response(201, headers={"Location": ".../contacts/10"}),  # create_contact (no org_number → skip find)
            _mock_response(201, headers={"Location": ".../purchases/400"}),  # create_purchase
            _mock_response(500),  # upload_attachment → server error (3 retries)
            _mock_response(500),
            _mock_response(500),
        ]

        purchase_id = client.post_invoice(
            vendor_name="Test",
            vendor_org_number=None,
            invoice_date="2026-03-01",
            due_date=None,
            invoice_number=None,
            payment_reference=None,
            total_amount=100.00,
            account_code="6900",
            vat_code="1",
            description="Test",
            file_path=test_file,
        )

        # Kjøpet opprettes selv om vedlegg feiler
        assert purchase_id == 400


# --- Retry-logikk ---


class TestRetry:
    def test_retry_on_429(self, client, mock_http):
        mock_http.request.side_effect = [
            _mock_response(429),  # 1. forsøk
            _mock_response(200, {"name": "Test"}),  # 2. forsøk OK
        ]
        with patch("bilagbot.fiken.time.sleep"):
            result = client.validate()
        assert result["name"] == "Test"

    def test_retry_on_500(self, client, mock_http):
        mock_http.request.side_effect = [
            _mock_response(500),
            _mock_response(500),
            _mock_response(200, json_data=[]),
        ]
        with patch("bilagbot.fiken.time.sleep"):
            result = client.get_accounts()
        assert result == []

    def test_max_retries_exhausted(self, client, mock_http):
        mock_http.request.side_effect = [
            _mock_response(429),
            _mock_response(429),
            _mock_response(429),
        ]
        with patch("bilagbot.fiken.time.sleep"):
            with pytest.raises(FikenRateLimitError):
                client.validate()


# --- Database-integrasjon ---


class TestDatabaseFiken:
    def test_sync_accounts(self):
        from bilagbot.database import get_connection, get_fiken_account, get_fiken_accounts, sync_fiken_accounts

        conn = get_connection(Path(":memory:"))
        accounts = [
            {"code": "3000", "name": "Salgsinntekt"},
            {"code": "6300", "name": "Kontorrekvisita"},
            {"code": "6900", "name": "Diverse"},
        ]
        count = sync_fiken_accounts(conn, accounts)
        assert count == 3

        cached = get_fiken_accounts(conn)
        assert len(cached) == 3
        assert cached[0]["code"] == "3000"

        found = get_fiken_account(conn, "6300")
        assert found is not None
        assert found["name"] == "Kontorrekvisita"

        not_found = get_fiken_account(conn, "9999")
        assert not_found is None
        conn.close()

    def test_update_scan_fiken(self):
        from bilagbot.database import get_connection, get_scan, insert_scan, update_scan_fiken, update_scan_status

        conn = get_connection(Path(":memory:"))
        scan_id = insert_scan(
            conn,
            file_path="/test.pdf",
            file_hash="abc123",
            supplier_org_number="999888777",
            supplier_name="Test AS",
            total_amount=1000.0,
            vat_amount=250.0,
            currency="NOK",
            invoice_date="2026-03-01",
            due_date="2026-03-15",
            invoice_number="F-001",
            match_level="KNOWN",
            account_code="6900",
            vat_code="1",
            raw_claude_json="{}",
        )

        update_scan_status(conn, scan_id, "APPROVED")
        update_scan_fiken(conn, scan_id, 42)

        row = get_scan(conn, scan_id)
        assert row["status"] == "POSTED"
        assert row["fiken_purchase_id"] == 42
        assert row["fiken_posted_at"] is not None
        conn.close()
