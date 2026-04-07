"""FastAPI web-app for BilagBot."""

import logging
import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bilagbot.classifier import classify, learn_from_approval
from bilagbot.config import DATA_DIR, ensure_data_dir
from bilagbot.database import (
    find_duplicate,
    get_all_scans,
    get_connection,
    get_scan,
    get_scans_by_status,
    get_supplier,
    insert_scan,
    update_scan_classification,
    update_scan_fiken,
    update_scan_status,
)
from bilagbot.exceptions import FikenError, ScannerError
from bilagbot.models import InvoiceData
from bilagbot.scanner import file_hash, scan_file

logger = logging.getLogger(__name__)

app = FastAPI(title="BilagBot", version="0.2.0")

UPLOAD_DIR = DATA_DIR / "uploads"

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ApproveRequest(BaseModel):
    account_code: str | None = None
    vat_code: str | None = None


class ScanResult(BaseModel):
    id: int
    supplier_name: str | None
    supplier_org_number: str | None
    total_amount: float | None
    vat_amount: float | None
    currency: str
    invoice_date: str | None
    due_date: str | None
    invoice_number: str | None
    match_level: str
    account_code: str | None
    vat_code: str | None
    status: str
    scanned_at: str | None
    file_path: str | None


def _row_to_dict(row) -> dict:
    """Konverter sqlite3.Row til dict."""
    if row is None:
        return {}
    return {k: row[k] for k in row.keys()}


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve hovedsiden."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>BilagBot</h1><p>Mangler static/index.html</p>"


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/scan")
async def api_scan(file: UploadFile = File(...)):
    """Last opp og scan et bilag."""
    ensure_data_dir()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Valider filtype
    suffix = Path(file.filename or "unknown").suffix.lower()
    allowed = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
    if suffix not in allowed:
        raise HTTPException(400, f"Filtypen {suffix} stottes ikke. Bruk PDF, JPEG, PNG, GIF eller WebP.")

    # Lagre fil
    dest = UPLOAD_DIR / (file.filename or "unknown")
    # Unngaa overskriving
    counter = 1
    while dest.exists():
        dest = UPLOAD_DIR / f"{dest.stem}_{counter}{dest.suffix}"
        counter += 1

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    conn = get_connection()
    try:
        # Duplikatsjekk
        fhash = file_hash(dest)
        dup = find_duplicate(conn, fhash)
        if dup:
            dest.unlink()
            return {"duplicate": True, "existing_id": dup["id"]}

        # Scan med Claude CLI
        try:
            invoice, raw_json = scan_file(dest)
        except ScannerError as e:
            dest.unlink()
            raise HTTPException(500, f"Scanfeil: {e}")

        # Klassifiser
        result = classify(conn, invoice)

        # Lagre
        scan_id = insert_scan(
            conn,
            file_path=str(dest.resolve()),
            file_hash=fhash,
            supplier_org_number=invoice.vendor_org_number,
            supplier_name=result.supplier_name or invoice.vendor_name,
            total_amount=invoice.total_amount,
            vat_amount=invoice.vat_amount,
            currency=invoice.currency,
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            invoice_number=invoice.invoice_number,
            match_level=result.match_level.value,
            account_code=result.account_code,
            vat_code=result.vat_code,
            raw_claude_json=raw_json,
        )

        row = get_scan(conn, scan_id)
        return {"duplicate": False, "scan": _row_to_dict(row)}
    finally:
        conn.close()


@app.get("/api/scans")
async def api_scans(status: str | None = None):
    """Hent alle bilag, eventuelt filtrert pa status."""
    conn = get_connection()
    try:
        if status:
            rows = get_scans_by_status(conn, status.upper())
        else:
            rows = get_all_scans(conn)
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/scans/{scan_id}")
async def api_scan_detail(scan_id: int):
    """Hent detaljer for ett bilag."""
    conn = get_connection()
    try:
        row = get_scan(conn, scan_id)
        if not row:
            raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")
        return _row_to_dict(row)
    finally:
        conn.close()


@app.post("/api/scans/{scan_id}/approve")
async def api_approve(scan_id: int, body: ApproveRequest | None = None):
    """Godkjenn et bilag og lar leverandoren."""
    conn = get_connection()
    try:
        row = get_scan(conn, scan_id)
        if not row:
            raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")
        if row["status"] != "PENDING":
            raise HTTPException(400, f"Bilag #{scan_id} har status {row['status']}")

        body = body or ApproveRequest()
        final_account = body.account_code or row["account_code"]
        final_vat = body.vat_code or row["vat_code"]

        if body.account_code or body.vat_code:
            update_scan_classification(conn, scan_id, match_level=row["match_level"],
                                       account_code=final_account, vat_code=final_vat)

        update_scan_status(conn, scan_id, "APPROVED")

        invoice = InvoiceData(vendor_name=row["supplier_name"],
                              vendor_org_number=row["supplier_org_number"])
        learn_from_approval(conn, invoice, account_code=final_account, vat_code=final_vat)

        updated = get_scan(conn, scan_id)
        result = _row_to_dict(updated)

        # Sjekk auto-approve status
        if row["supplier_org_number"]:
            supplier = get_supplier(conn, row["supplier_org_number"])
            if supplier and supplier["auto_approve"]:
                result["auto_approved"] = True

        return result
    finally:
        conn.close()


@app.post("/api/scans/{scan_id}/reject")
async def api_reject(scan_id: int):
    """Avvis et bilag."""
    conn = get_connection()
    try:
        row = get_scan(conn, scan_id)
        if not row:
            raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")
        if row["status"] != "PENDING":
            raise HTTPException(400, f"Bilag #{scan_id} har status {row['status']}")

        update_scan_status(conn, scan_id, "REJECTED")
        return _row_to_dict(get_scan(conn, scan_id))
    finally:
        conn.close()


@app.delete("/api/scans/{scan_id}")
async def api_delete(scan_id: int):
    """Slett et bilag permanent."""
    conn = get_connection()
    try:
        row = get_scan(conn, scan_id)
        if not row:
            raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")

        # Slett opplastet fil
        if row["file_path"]:
            p = Path(row["file_path"])
            if p.exists():
                p.unlink()

        conn.execute("DELETE FROM scan_log WHERE id = ?", (scan_id,))
        conn.commit()
        return {"deleted": scan_id}
    finally:
        conn.close()


@app.post("/api/scans/{scan_id}/fiken")
async def api_fiken_post(scan_id: int):
    """Bokfor et godkjent bilag til Fiken."""
    conn = get_connection()
    try:
        row = get_scan(conn, scan_id)
        if not row:
            raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")
        if row["status"] != "APPROVED":
            raise HTTPException(400, f"Bilag #{scan_id} har status {row['status']} — kun APPROVED kan bokfores")
        if not row["account_code"]:
            raise HTTPException(400, f"Bilag #{scan_id} mangler kontokode")

        from bilagbot.fiken import FikenClient

        try:
            client = FikenClient()
            file_path = Path(row["file_path"]) if row["file_path"] else None

            purchase_id = client.post_invoice(
                vendor_name=row["supplier_name"] or "Ukjent leverandor",
                vendor_org_number=row["supplier_org_number"],
                invoice_date=row["invoice_date"] or "1970-01-01",
                due_date=row["due_date"],
                invoice_number=row["invoice_number"],
                payment_reference=None,
                total_amount=row["total_amount"] or 0,
                account_code=row["account_code"],
                vat_code=row["vat_code"],
                description=row["supplier_name"] or "Kjop",
                file_path=file_path,
            )

            update_scan_fiken(conn, scan_id, purchase_id)
            client.close()
            return {"purchase_id": purchase_id, "scan": _row_to_dict(get_scan(conn, scan_id))}
        except FikenError as e:
            update_scan_status(conn, scan_id, "FAILED")
            raise HTTPException(500, f"Fiken-feil: {e}")
    finally:
        conn.close()
