"""Tester for Pydantic-modeller."""


from bilagbot.models import InvoiceData, LineItem, MatchLevel, ScanStatus


class TestLineItem:
    def test_empty(self):
        item = LineItem()
        assert item.description is None
        assert item.amount is None

    def test_full(self):
        item = LineItem(description="Vare", quantity=2.0, unit_price=50.0, amount=100.0, vat_rate=25.0, vat_amount=20.0)
        assert item.amount == 100.0
        assert item.vat_rate == 25.0


class TestInvoiceData:
    def test_defaults(self):
        invoice = InvoiceData()
        assert invoice.currency == "NOK"
        assert invoice.line_items == []
        assert invoice.vendor_name is None

    def test_from_fixture(self, known_response):
        invoice = InvoiceData(**known_response)
        assert invoice.vendor_name == "Telenor Norge AS"
        assert invoice.vendor_org_number == "988312495"
        assert invoice.total_amount == 599.0
        assert invoice.currency == "NOK"
        assert len(invoice.line_items) == 1
        assert invoice.line_items[0].description == "Mobilabonnement Smart Bedrift"

    def test_null_fields(self, unknown_response):
        invoice = InvoiceData(**unknown_response)
        assert invoice.vendor_org_number is None
        assert invoice.invoice_number is None
        assert invoice.due_date is None

    def test_json_roundtrip(self, known_response):
        invoice = InvoiceData(**known_response)
        json_str = invoice.model_dump_json()
        restored = InvoiceData.model_validate_json(json_str)
        assert restored.vendor_name == invoice.vendor_name
        assert restored.total_amount == invoice.total_amount


class TestEnums:
    def test_match_levels(self):
        assert MatchLevel.UNKNOWN.value == "UNKNOWN"
        assert MatchLevel.KNOWN.value == "KNOWN"
        assert MatchLevel.AUTO.value == "AUTO"

    def test_scan_statuses(self):
        assert ScanStatus.PENDING.value == "PENDING"
        assert ScanStatus.POSTED.value == "POSTED"
