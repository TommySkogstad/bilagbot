"""Pydantic-modeller for BilagBot."""

from enum import Enum

from pydantic import BaseModel


class LineItem(BaseModel):
    """Enkeltpost på en faktura."""

    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None
    vat_rate: float | None = None
    vat_amount: float | None = None


class InvoiceData(BaseModel):
    """Strukturert data ekstrahert fra en faktura."""

    vendor_name: str | None = None
    vendor_org_number: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    total_amount: float | None = None
    vat_amount: float | None = None
    vat_rate: float | None = None
    currency: str = "NOK"
    payment_reference: str | None = None
    description: str | None = None
    confidence: float | None = None
    suggested_account: str | None = None
    suggested_vat_code: str | None = None
    line_items: list[LineItem] = []


class MatchLevel(str, Enum):
    """Nivå av leverandørgjenkjenning."""

    UNKNOWN = "UNKNOWN"
    KNOWN = "KNOWN"
    AUTO = "AUTO"


class ScanStatus(str, Enum):
    """Status for et skannet bilag."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    POSTED = "POSTED"
    FAILED = "FAILED"
