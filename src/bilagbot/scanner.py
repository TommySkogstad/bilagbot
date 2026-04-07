"""Scanner: bruker Claude CLI til a ekstrahere data fra fakturaer."""

import hashlib
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path

from bilagbot.config import CLAUDE_MODEL
from bilagbot.exceptions import ScannerError
from bilagbot.models import InvoiceData

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
SUPPORTED_TYPES = SUPPORTED_IMAGE_TYPES | {"application/pdf"}

SCAN_PROMPT = """Analyser dette dokumentet (faktura/kvittering). Ekstraher all informasjon du finner.

Regler:
- vendor_name: Navn pa leverandor/butikk
- vendor_org_number: Organisasjonsnummer (kun siffer, 9 siffer for norske selskaper)
- invoice_number: Fakturanummer
- invoice_date: Fakturadato i format YYYY-MM-DD
- due_date: Forfallsdato i format YYYY-MM-DD
- total_amount: Totalbelop inkl. mva som tall
- vat_amount: Totalt MVA-belop som tall
- vat_rate: MVA-sats i prosent (f.eks. 25.0)
- currency: Valutakode (default "NOK")
- payment_reference: KID-nummer eller betalingsreferanse
- description: Kort beskrivelse av hva fakturaen gjelder
- confidence: Tall mellom 0 og 1 for hvor sikker du er pa dataene totalt sett
- suggested_account: Foreslatt regnskapskonto (f.eks. "6300" for kontor, "6800" for data/IT)
- suggested_vat_code: Foreslatt MVA-kode ("1" for 25%, "11" for 15% mat, "6" for 0%)
- line_items: Liste over enkeltposter med description, quantity, unit_price, amount, vat_rate, vat_amount

Returner BARE gyldig JSON med disse feltene. Bruk null for felt du ikke finner."""


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


def scan_file(path: Path, *, model: str | None = None) -> tuple[InvoiceData, str]:
    """Scan en fil med Claude CLI og returner (InvoiceData, raw_json).

    Raises:
        ScannerError: Hvis filen ikke stottes eller CLI-kallet feiler.
    """
    if not shutil.which("claude"):
        raise ScannerError("Claude CLI er ikke installert. Installer med: npm install -g @anthropic-ai/claude-code")

    if not path.exists():
        raise ScannerError(f"Filen finnes ikke: {path}")

    mime = detect_mime_type(path)
    if mime not in SUPPORTED_TYPES:
        raise ScannerError(f"Filtypen {mime} stottes ikke. Stottede typer: PDF, JPEG, PNG, GIF, WebP")

    prompt = f"{SCAN_PROMPT}\n\nFil: {path.resolve()}"

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--max-turns", "1",
    ]
    if model or CLAUDE_MODEL:
        cmd.extend(["--model", model or CLAUDE_MODEL])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise ScannerError("Claude CLI tidsavbrudd (120s)")
    except OSError as e:
        raise ScannerError(f"Kunne ikke kjore Claude CLI: {e}")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise ScannerError(f"Claude CLI feilet (kode {result.returncode}): {stderr}")

    # Claude CLI med --output-format json returnerer et JSON-objekt med "result" felt
    try:
        cli_output = json.loads(result.stdout)
        raw_text = cli_output.get("result", result.stdout)
    except json.JSONDecodeError:
        raw_text = result.stdout.strip()

    # Ekstraher JSON fra responsen (Claude kan wrappe i markdown code blocks)
    raw_json = _extract_json(raw_text)

    try:
        invoice = InvoiceData.model_validate_json(raw_json)
    except Exception as e:
        raise ScannerError(f"Kunne ikke parse Claude-respons som InvoiceData: {e}")

    return invoice, raw_json


def _extract_json(text: str) -> str:
    """Ekstraher JSON fra tekst, selv om den er wrappet i markdown code blocks."""
    text = text.strip()

    # Fjern markdown code block hvis til stede
    if text.startswith("```"):
        lines = text.split("\n")
        # Fjern forste linje (```json) og siste linje (```)
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end]).strip()

    # Valider at det er gyldig JSON
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError as e:
        raise ScannerError(f"Ugyldig JSON i Claude-respons: {e}")
