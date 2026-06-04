"""Pydantic-modeller for BilagBot."""

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_validator


class LineItem(BaseModel):
    """Enkeltpost på en faktura."""

    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None
    vat_rate: float | None = None
    vat_amount: float | None = None

    @field_validator("vat_rate")
    @classmethod
    def vat_rate_in_range(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError(f"MVA-sats må være mellom 0 og 100: {v}")
        return v


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

    @field_validator("invoice_date", "due_date", mode="before")
    @classmethod
    def validate_date_format(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except (ValueError, TypeError):
                raise ValueError(f"Ugyldig dato (forventet YYYY-MM-DD): {v}")
        return v

    @field_validator("vendor_org_number", mode="before")
    @classmethod
    def validate_org_number(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^\d{9}$", v):
            raise ValueError(f"Org.nr. må være nøyaktig 9 sifre: {v}")
        return v

    @field_validator("total_amount", "vat_amount")
    @classmethod
    def must_be_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Beløp kan ikke være negativt")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError(f"Confidence må være mellom 0.0 og 1.0: {v}")
        return v

    @field_validator("vat_rate")
    @classmethod
    def vat_rate_in_range(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError(f"MVA-sats må være mellom 0 og 100: {v}")
        return v


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
