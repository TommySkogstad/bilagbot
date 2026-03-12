"""Scanner: bruker Claude API til å ekstrahere data fra fakturaer."""

import base64
import hashlib
import mimetypes
from pathlib import Path

import anthropic

from bilagbot.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from bilagbot.exceptions import ScannerError
from bilagbot.models import InvoiceData

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
SUPPORTED_TYPES = SUPPORTED_IMAGE_TYPES | {"application/pdf"}

SCAN_PROMPT = """Analyser dette dokumentet (faktura/kvittering). Ekstraher all informasjon du finner.

Regler:
- vendor_name: Navn på leverandør/butikk
- vendor_org_number: Organisasjonsnummer (kun siffer, 9 siffer for norske selskaper)
- invoice_number: Fakturanummer
- invoice_date: Fakturadato i format YYYY-MM-DD
- due_date: Forfallsdato i format YYYY-MM-DD
- total_amount: Totalbeløp inkl. mva som tall
- vat_amount: Totalt MVA-beløp som tall
- vat_rate: MVA-sats i prosent (f.eks. 25.0)
- currency: Valutakode (default "NOK")
- payment_reference: KID-nummer eller betalingsreferanse
- description: Kort beskrivelse av hva fakturaen gjelder
- confidence: Tall mellom 0 og 1 for hvor sikker du er på dataene totalt sett
- suggested_account: Foreslått regnskapskonto (f.eks. "6300" for kontor, "6800" for data/IT)
- suggested_vat_code: Foreslått MVA-kode ("1" for 25%, "11" for 15% mat, "6" for 0%)
- line_items: Liste over enkeltposter med description, quantity, unit_price, amount, vat_rate, vat_amount

Returner null for felt du ikke finner."""


def file_hash(path: Path) -> str:
    """Beregn SHA-256 hash av en fil."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_mime_type(path: Path) -> str:
    """Detekter MIME-type for en fil."""
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        suffix = path.suffix.lower()
        mime_map = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "application/octet-stream")
    return mime


def scan_file(path: Path, *, api_key: str | None = None, model: str | None = None) -> tuple[InvoiceData, str]:
    """Scan en fil med Claude API og returner (InvoiceData, raw_json).

    Raises:
        ScannerError: Hvis filen ikke støttes eller API-kallet feiler.
    """
    key = api_key if api_key is not None else ANTHROPIC_API_KEY
    if not key:
        raise ScannerError("ANTHROPIC_API_KEY er ikke konfigurert. Sett den i .env eller som miljøvariabel.")

    if not path.exists():
        raise ScannerError(f"Filen finnes ikke: {path}")

    mime = detect_mime_type(path)
    if mime not in SUPPORTED_TYPES:
        raise ScannerError(f"Filtypen {mime} støttes ikke. Støttede typer: PDF, JPEG, PNG, GIF, WebP")

    file_bytes = path.read_bytes()
    b64 = base64.standard_b64encode(file_bytes).decode("ascii")

    if mime == "application/pdf":
        content_block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        }
    else:
        content_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": b64},
        }

    client = anthropic.Anthropic(api_key=key)

    try:
        response = client.messages.create(
            model=model or CLAUDE_MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [content_block, {"type": "text", "text": SCAN_PROMPT}],
                }
            ],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": InvoiceData.model_json_schema(),
                },
            },
        )
    except anthropic.APIError as e:
        raise ScannerError(f"Claude API-feil: {e}") from e

    raw_json = response.content[0].text
    invoice = InvoiceData.model_validate_json(raw_json)
    return invoice, raw_json
