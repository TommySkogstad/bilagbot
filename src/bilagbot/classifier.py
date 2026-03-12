"""Klassifisering: leverandørgjenkjenning og læring."""

import sqlite3

from bilagbot.config import AUTO_APPROVE_THRESHOLD
from bilagbot.database import get_supplier, update_supplier_auto_approve, upsert_supplier
from bilagbot.models import InvoiceData, MatchLevel


class ClassificationResult:
    """Resultat av klassifisering."""

    def __init__(self, match_level: MatchLevel, account_code: str | None = None,
                 vat_code: str | None = None, supplier_name: str | None = None):
        self.match_level = match_level
        self.account_code = account_code
        self.vat_code = vat_code
        self.supplier_name = supplier_name


def classify(conn: sqlite3.Connection, invoice: InvoiceData) -> ClassificationResult:
    """Klassifiser en faktura basert på leverandørgjenkjenning.

    Returnerer:
        - AUTO: Leverandøren er kjent og auto-godkjent
        - KNOWN: Leverandøren er kjent men ikke auto-godkjent
        - UNKNOWN: Ny/ukjent leverandør
    """
    org_number = invoice.vendor_org_number
    if not org_number:
        return ClassificationResult(
            match_level=MatchLevel.UNKNOWN,
            account_code=invoice.suggested_account,
            vat_code=invoice.suggested_vat_code,
            supplier_name=invoice.vendor_name,
        )

    supplier = get_supplier(conn, org_number)
    if supplier is None:
        return ClassificationResult(
            match_level=MatchLevel.UNKNOWN,
            account_code=invoice.suggested_account,
            vat_code=invoice.suggested_vat_code,
            supplier_name=invoice.vendor_name,
        )

    account_code = supplier["account_code"] or invoice.suggested_account
    vat_code = supplier["vat_code"] or invoice.suggested_vat_code

    if supplier["auto_approve"]:
        return ClassificationResult(
            match_level=MatchLevel.AUTO,
            account_code=account_code,
            vat_code=vat_code,
            supplier_name=supplier["supplier_name"],
        )

    return ClassificationResult(
        match_level=MatchLevel.KNOWN,
        account_code=account_code,
        vat_code=vat_code,
        supplier_name=supplier["supplier_name"],
    )


def learn_from_approval(conn: sqlite3.Connection, invoice: InvoiceData,
                        account_code: str | None = None, vat_code: str | None = None) -> None:
    """Lær fra en godkjent faktura — oppdater eller opprett leverandør.

    Etter AUTO_APPROVE_THRESHOLD godkjenninger settes auto_approve=True.
    """
    org_number = invoice.vendor_org_number
    if not org_number or not invoice.vendor_name:
        return

    upsert_supplier(
        conn,
        org_number=org_number,
        supplier_name=invoice.vendor_name,
        account_code=account_code,
        vat_code=vat_code,
    )

    supplier = get_supplier(conn, org_number)
    if supplier and supplier["approval_count"] >= AUTO_APPROVE_THRESHOLD and not supplier["auto_approve"]:
        update_supplier_auto_approve(conn, org_number, True)
