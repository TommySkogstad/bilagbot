"""Tester for databaseoperasjoner."""


from bilagbot.database import (
    find_duplicate,
    get_all_scans,
    get_all_suppliers,
    get_scan,
    get_scans_by_status,
    get_supplier,
    insert_scan,
    update_scan_classification,
    update_scan_status,
    update_supplier_auto_approve,
    update_supplier_fields,
    upsert_supplier,
)


class TestScanLog:
    def test_insert_and_get(self, db):
        scan_id = insert_scan(
            db, file_path="/tmp/test.pdf", file_hash="abc123",
            supplier_org_number="988312495", supplier_name="Telenor",
            total_amount=599.0, vat_amount=119.8, currency="NOK",
            invoice_date="2025-01-15", due_date="2025-02-15",
            invoice_number="INV-001", match_level="KNOWN",
            account_code="6900", vat_code="1", raw_claude_json="{}",
        )
        assert scan_id == 1

        row = get_scan(db, scan_id)
        assert row is not None
        assert row["supplier_name"] == "Telenor"
        assert row["total_amount"] == 599.0
        assert row["status"] == "PENDING"

    def test_get_nonexistent(self, db):
        assert get_scan(db, 999) is None

    def test_status_update(self, db):
        scan_id = insert_scan(
            db, file_path="/tmp/test.pdf", file_hash="abc",
            supplier_org_number=None, supplier_name=None,
            total_amount=100.0, vat_amount=20.0, currency="NOK",
            invoice_date=None, due_date=None, invoice_number=None,
            match_level="UNKNOWN", account_code=None, vat_code=None,
            raw_claude_json="{}",
        )
        update_scan_status(db, scan_id, "APPROVED")
        row = get_scan(db, scan_id)
        assert row["status"] == "APPROVED"
        assert row["reviewed_at"] is not None

    def test_classification_update(self, db):
        scan_id = insert_scan(
            db, file_path="/tmp/test.pdf", file_hash="def",
            supplier_org_number=None, supplier_name=None,
            total_amount=100.0, vat_amount=20.0, currency="NOK",
            invoice_date=None, due_date=None, invoice_number=None,
            match_level="UNKNOWN", account_code=None, vat_code=None,
            raw_claude_json="{}",
        )
        update_scan_classification(db, scan_id, match_level="KNOWN", account_code="6300", vat_code="1")
        row = get_scan(db, scan_id)
        assert row["match_level"] == "KNOWN"
        assert row["account_code"] == "6300"

    def test_duplicate_detection(self, db):
        insert_scan(
            db, file_path="/tmp/test.pdf", file_hash="same_hash",
            supplier_org_number=None, supplier_name=None,
            total_amount=100.0, vat_amount=20.0, currency="NOK",
            invoice_date=None, due_date=None, invoice_number=None,
            match_level="UNKNOWN", account_code=None, vat_code=None,
            raw_claude_json="{}",
        )
        dup = find_duplicate(db, "same_hash")
        assert dup is not None
        assert find_duplicate(db, "different_hash") is None

    def test_get_by_status(self, db):
        for i in range(3):
            insert_scan(
                db, file_path=f"/tmp/test{i}.pdf", file_hash=f"hash{i}",
                supplier_org_number=None, supplier_name=None,
                total_amount=100.0, vat_amount=20.0, currency="NOK",
                invoice_date=None, due_date=None, invoice_number=None,
                match_level="UNKNOWN", account_code=None, vat_code=None,
                raw_claude_json="{}",
            )
        update_scan_status(db, 1, "APPROVED")

        pending = get_scans_by_status(db, "PENDING")
        assert len(pending) == 2

        approved = get_scans_by_status(db, "APPROVED")
        assert len(approved) == 1

    def test_get_all(self, db):
        for i in range(3):
            insert_scan(
                db, file_path=f"/tmp/test{i}.pdf", file_hash=f"hash{i}",
                supplier_org_number=None, supplier_name=None,
                total_amount=100.0, vat_amount=20.0, currency="NOK",
                invoice_date=None, due_date=None, invoice_number=None,
                match_level="UNKNOWN", account_code=None, vat_code=None,
                raw_claude_json="{}",
            )
        assert len(get_all_scans(db)) == 3


class TestSuppliers:
    def test_upsert_new(self, db):
        upsert_supplier(db, org_number="988312495", supplier_name="Telenor",
                        account_code="6900", vat_code="1")
        supplier = get_supplier(db, "988312495")
        assert supplier is not None
        assert supplier["supplier_name"] == "Telenor"
        assert supplier["account_code"] == "6900"
        assert supplier["approval_count"] == 1

    def test_upsert_existing_increments(self, db):
        upsert_supplier(db, org_number="988312495", supplier_name="Telenor")
        upsert_supplier(db, org_number="988312495", supplier_name="Telenor Norge AS")
        supplier = get_supplier(db, "988312495")
        assert supplier["approval_count"] == 2
        assert supplier["supplier_name"] == "Telenor Norge AS"

    def test_auto_approve(self, db):
        upsert_supplier(db, org_number="123456789", supplier_name="Test AS")
        supplier = get_supplier(db, "123456789")
        assert not supplier["auto_approve"]

        update_supplier_auto_approve(db, "123456789", True)
        supplier = get_supplier(db, "123456789")
        assert supplier["auto_approve"]

    def test_update_fields(self, db):
        upsert_supplier(db, org_number="123456789", supplier_name="Test AS")
        update_supplier_fields(db, "123456789", account_code="7100", vat_code="11")
        supplier = get_supplier(db, "123456789")
        assert supplier["account_code"] == "7100"
        assert supplier["vat_code"] == "11"

    def test_get_all_sorted(self, db):
        upsert_supplier(db, org_number="222222222", supplier_name="Zulu AS")
        upsert_supplier(db, org_number="111111111", supplier_name="Alfa AS")
        suppliers = get_all_suppliers(db)
        assert len(suppliers) == 2
        assert suppliers[0]["supplier_name"] == "Alfa AS"

    def test_coalesce_on_upsert(self, db):
        """Eksisterende verdier beholdes hvis nye er None."""
        upsert_supplier(db, org_number="123456789", supplier_name="Test AS",
                        account_code="6900", vat_code="1")
        upsert_supplier(db, org_number="123456789", supplier_name="Test AS")
        supplier = get_supplier(db, "123456789")
        assert supplier["account_code"] == "6900"
        assert supplier["vat_code"] == "1"
