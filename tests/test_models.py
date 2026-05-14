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


class TestInvoiceDataValidation:
    def test_negative_total_amount_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(total_amount=-100.0)

    def test_negative_vat_amount_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(vat_amount=-10.0)

    def test_zero_total_amount_ok(self):
        invoice = InvoiceData(total_amount=0.0)
        assert invoice.total_amount == 0.0

    def test_none_amounts_ok(self):
        invoice = InvoiceData(total_amount=None, vat_amount=None)
        assert invoice.total_amount is None


class TestInvoiceDataDateValidation:
    def test_invalid_date_format_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(invoice_date="01/01/2024")

    def test_invalid_due_date_format_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(due_date="2024.01.01")

    def test_valid_date_ok(self):
        invoice = InvoiceData(invoice_date="2024-01-15", due_date="2024-02-15")
        assert invoice.invoice_date == "2024-01-15"
        assert invoice.due_date == "2024-02-15"

    def test_none_date_ok(self):
        invoice = InvoiceData(invoice_date=None)
        assert invoice.invoice_date is None


class TestInvoiceDataOrgNumberValidation:
    def test_too_short_org_number_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(vendor_org_number="12345")

    def test_too_long_org_number_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(vendor_org_number="1234567890")

    def test_non_digit_org_number_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(vendor_org_number="12345678X")

    def test_valid_org_number_ok(self):
        invoice = InvoiceData(vendor_org_number="988312495")
        assert invoice.vendor_org_number == "988312495"

    def test_none_org_number_ok(self):
        invoice = InvoiceData(vendor_org_number=None)
        assert invoice.vendor_org_number is None


class TestInvoiceDataConfidenceValidation:
    def test_confidence_above_one_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(confidence=1.5)

    def test_confidence_below_zero_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(confidence=-0.1)

    def test_confidence_at_bounds_ok(self):
        invoice = InvoiceData(confidence=0.0)
        assert invoice.confidence == 0.0
        invoice2 = InvoiceData(confidence=1.0)
        assert invoice2.confidence == 1.0


class TestInvoiceDataVatRateValidation:
    def test_vat_rate_above_100_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(vat_rate=101.0)

    def test_vat_rate_negative_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvoiceData(vat_rate=-1.0)

    def test_vat_rate_zero_ok(self):
        invoice = InvoiceData(vat_rate=0.0)
        assert invoice.vat_rate == 0.0

    def test_vat_rate_100_ok(self):
        invoice = InvoiceData(vat_rate=100.0)
        assert invoice.vat_rate == 100.0


class TestLineItemVatRateValidation:
    def test_line_item_vat_rate_above_100_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LineItem(vat_rate=150.0)

    def test_line_item_vat_rate_negative_raises(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LineItem(vat_rate=-5.0)

    def test_line_item_vat_rate_25_ok(self):
        item = LineItem(vat_rate=25.0)
        assert item.vat_rate == 25.0


class TestEnums:
    def test_match_levels(self):
        assert MatchLevel.UNKNOWN.value == "UNKNOWN"
        assert MatchLevel.KNOWN.value == "KNOWN"
        assert MatchLevel.AUTO.value == "AUTO"

    def test_scan_statuses(self):
        assert ScanStatus.PENDING.value == "PENDING"
        assert ScanStatus.POSTED.value == "POSTED"
