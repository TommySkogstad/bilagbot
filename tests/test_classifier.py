"""Tester for klassifisering og læring."""


from bilagbot.classifier import classify, learn_from_approval
from bilagbot.database import get_supplier, update_supplier_auto_approve, upsert_supplier
from bilagbot.models import InvoiceData, MatchLevel


class TestClassify:
    def test_unknown_no_org_number(self, db, unknown_invoice):
        result = classify(db, unknown_invoice)
        assert result.match_level == MatchLevel.UNKNOWN
        assert result.account_code == "7140"  # Fra suggested_account

    def test_unknown_new_supplier(self, db, known_invoice):
        result = classify(db, known_invoice)
        assert result.match_level == MatchLevel.UNKNOWN

    def test_known_supplier(self, db, known_invoice):
        upsert_supplier(db, org_number="988312495", supplier_name="Telenor",
                        account_code="6900", vat_code="1")
        result = classify(db, known_invoice)
        assert result.match_level == MatchLevel.KNOWN
        assert result.account_code == "6900"
        assert result.vat_code == "1"

    def test_auto_supplier(self, db, known_invoice):
        upsert_supplier(db, org_number="988312495", supplier_name="Telenor",
                        account_code="6900", vat_code="1")
        update_supplier_auto_approve(db, "988312495", True)
        result = classify(db, known_invoice)
        assert result.match_level == MatchLevel.AUTO

    def test_supplier_values_override_suggested(self, db, known_invoice):
        """Leverandørens lagrede verdier brukes fremfor Claudes forslag."""
        upsert_supplier(db, org_number="988312495", supplier_name="Telenor",
                        account_code="6100", vat_code="6")
        result = classify(db, known_invoice)
        assert result.account_code == "6100"
        assert result.vat_code == "6"

    def test_supplier_falls_back_to_suggested(self, db, known_invoice):
        """Faller tilbake til Claude-forslag hvis leverandør mangler verdier."""
        upsert_supplier(db, org_number="988312495", supplier_name="Telenor")
        result = classify(db, known_invoice)
        assert result.account_code == "6900"  # suggested_account
        assert result.vat_code == "1"  # suggested_vat_code


class TestLearning:
    def test_learn_new_supplier(self, db, known_invoice):
        learn_from_approval(db, known_invoice, account_code="6900", vat_code="1")
        supplier = get_supplier(db, "988312495")
        assert supplier is not None
        assert supplier["supplier_name"] == "Telenor Norge AS"
        assert supplier["account_code"] == "6900"

    def test_learn_increments_count(self, db, known_invoice):
        learn_from_approval(db, known_invoice)
        learn_from_approval(db, known_invoice)
        supplier = get_supplier(db, "988312495")
        assert supplier["approval_count"] == 2

    def test_auto_approve_after_threshold(self, db, known_invoice):
        """Auto-approve aktiveres etter 3 godkjenninger."""
        for _ in range(3):
            learn_from_approval(db, known_invoice, account_code="6900")
        supplier = get_supplier(db, "988312495")
        assert supplier["auto_approve"]

    def test_no_learn_without_org_number(self, db, unknown_invoice):
        learn_from_approval(db, unknown_invoice)
        assert get_supplier(db, "") is None

    def test_no_learn_without_name(self, db):
        invoice = InvoiceData(vendor_org_number="123456789")
        learn_from_approval(db, invoice)
        assert get_supplier(db, "123456789") is None
