"""FastAPI web-app for BilagBot."""

import asyncio
import logging
import os
import re
import secrets
import sqlite3
import unicodedata
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bilagbot.classifier import classify, learn_from_approval
from bilagbot.config import (  # noqa: F401  # AUTH_USER/AUTH_PASS leses via modul-attributter for testbar monkeypatch
    AUTH_PASS,
    AUTH_USER,
    DATA_DIR,
    ensure_data_dir,
)
from bilagbot.database import (
    find_duplicate,
    get_all_scans,
    get_connection,
    get_fiken_account,
    get_fiken_accounts,
    get_scan,
    get_scans_by_status,
    get_supplier,
    insert_scan,
    update_scan_classification,
    update_scan_fiken,
    update_scan_status,
)
from bilagbot.exceptions import FikenError, ScannerError
from bilagbot.models import InvoiceData, ScanStatus
from bilagbot.scanner import file_hash, scan_file

logger = logging.getLogger(__name__)


def _validate_startup_config() -> None:
    env = os.getenv("BILAGBOT_ENV", "prod").lower()
    if env not in ("dev", "test") and not _auth_enabled():
        raise RuntimeError(
            "AUTH_USER og AUTH_PASS må settes i .env. "
            "Sett BILAGBOT_ENV=dev for lokal utvikling."
        )
    if not _auth_enabled():
        logger.warning("⚠️  Auth er deaktivert — kun for dev/test")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    _validate_startup_config()
    yield


app = FastAPI(title="BilagBot", version="0.2.0", lifespan=_lifespan)

_security = HTTPBasic(auto_error=False)


def _auth_enabled() -> bool:
    """Auth aktiveres kun naar baade AUTH_USER og AUTH_PASS er satt."""
    from bilagbot import web as _self  # les verdier dynamisk for testbar monkeypatch
    return bool(_self.AUTH_USER and _self.AUTH_PASS)


def require_auth(
    credentials: HTTPBasicCredentials | None = Depends(_security),
) -> None:
    """Krev HTTP Basic Auth naar AUTH_USER og AUTH_PASS er konfigurert."""
    from bilagbot import web as _self

    if not _auth_enabled():
        return

    unauthorized = HTTPException(
        status_code=401,
        detail="Ugyldig brukernavn eller passord",
        headers={"WWW-Authenticate": "Basic"},
    )

    if credentials is None:
        raise unauthorized

    user_ok = secrets.compare_digest(credentials.username, _self.AUTH_USER)
    pass_ok = secrets.compare_digest(credentials.password, _self.AUTH_PASS)
    if not (user_ok and pass_ok):
        raise unauthorized


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: yield én DB-tilkobling per request og lukk den etterpå."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


_SAFE_NAME_RE = re.compile(r"[^\w.\-]")


def _safe_filename(raw: str | None) -> str:
    """Returner et trygt filnavn uten path-komponenter eller farlige tegn."""
    if not raw:
        return "ukjent"
    name = unicodedata.normalize("NFKC", raw).replace("\x00", "")
    name = name.replace("\\", "/").split("/")[-1]
    name = name.lstrip(".") or "ukjent"
    name = _SAFE_NAME_RE.sub("_", name)
    return name[:200] or "ukjent"

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

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


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def index():
    """Serve hovedsiden."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>BilagBot</h1><p>Mangler static/index.html</p>"


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/scan", dependencies=[Depends(require_auth)])
async def api_scan(file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db)):
    """Last opp og scan et bilag."""
    ensure_data_dir()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Valider og sanitér filnavn
    safe_name = _safe_filename(file.filename)
    suffix = Path(safe_name).suffix.lower()
    allowed = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
    if suffix not in allowed:
        raise HTTPException(400, f"Filtypen {suffix} stottes ikke. Bruk PDF, JPEG, PNG, GIF eller WebP.")

    # Lagre fil — med containment-sjekk mot UPLOAD_DIR
    upload_root = UPLOAD_DIR.resolve()
    dest = (upload_root / safe_name).resolve()
    try:
        dest.relative_to(upload_root)
    except ValueError:
        raise HTTPException(400, "Ugyldig filnavn.")

    # Unngaa overskriving
    counter = 1
    stem, ext = Path(safe_name).stem, suffix
    while dest.exists():
        dest = (upload_root / f"{stem}_{counter}{ext}").resolve()
        counter += 1

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Filen er for stor (maks 50 MB)")
    with open(dest, "wb") as f:
        f.write(content)

    # Duplikatsjekk
    fhash = file_hash(dest)
    dup = find_duplicate(conn, fhash)
    if dup:
        dest.unlink()
        return {"duplicate": True, "existing_id": dup["id"]}

    # Scan med Claude CLI
    try:
        invoice, raw_json = await asyncio.to_thread(scan_file, dest)
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


@app.get("/api/scans", dependencies=[Depends(require_auth)])
async def api_scans(status: str | None = None, conn: sqlite3.Connection = Depends(get_db)):
    """Hent alle bilag, eventuelt filtrert pa status."""
    if status:
        rows = get_scans_by_status(conn, status.upper())
    else:
        rows = get_all_scans(conn)
    return [_row_to_dict(r) for r in rows]


@app.get("/api/scans/{scan_id}", dependencies=[Depends(require_auth)])
async def api_scan_detail(scan_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Hent detaljer for ett bilag."""
    row = get_scan(conn, scan_id)
    if not row:
        raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")
    return _row_to_dict(row)


@app.post("/api/scans/{scan_id}/approve", dependencies=[Depends(require_auth)])
async def api_approve(scan_id: int, body: ApproveRequest | None = None, conn: sqlite3.Connection = Depends(get_db)):
    """Godkjenn et bilag og lar leverandoren."""
    row = get_scan(conn, scan_id)
    if not row:
        raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")
    if row["status"] != ScanStatus.PENDING.value:
        raise HTTPException(400, f"Bilag #{scan_id} har status {row['status']}")

    body = body or ApproveRequest()
    final_account = body.account_code or row["account_code"]
    final_vat = body.vat_code or row["vat_code"]

    if final_account and get_fiken_accounts(conn):
        if not get_fiken_account(conn, final_account):
            raise HTTPException(400, f"Ugyldig kontokode: {final_account} finnes ikke i fiken_accounts")

    if body.account_code or body.vat_code:
        update_scan_classification(conn, scan_id, match_level=row["match_level"],
                                   account_code=final_account, vat_code=final_vat)

    update_scan_status(conn, scan_id, ScanStatus.APPROVED.value)

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


@app.post("/api/scans/{scan_id}/reject", dependencies=[Depends(require_auth)])
async def api_reject(scan_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Avvis et bilag."""
    row = get_scan(conn, scan_id)
    if not row:
        raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")
    if row["status"] != ScanStatus.PENDING.value:
        raise HTTPException(400, f"Bilag #{scan_id} har status {row['status']}")

    update_scan_status(conn, scan_id, ScanStatus.REJECTED.value)
    return _row_to_dict(get_scan(conn, scan_id))


@app.delete("/api/scans/{scan_id}", dependencies=[Depends(require_auth)])
async def api_delete(scan_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Slett et bilag permanent."""
    row = get_scan(conn, scan_id)
    if not row:
        raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")

    # Slett opplastet fil — verifiser at stien er innenfor UPLOAD_DIR
    if row["file_path"]:
        p = Path(row["file_path"]).resolve()
        try:
            p.relative_to(UPLOAD_DIR.resolve())
            if p.exists():
                p.unlink()
        except ValueError:
            logger.warning("api_delete: file_path utenfor UPLOAD_DIR, hopper over: %s", p)

    conn.execute("DELETE FROM scan_log WHERE id = ?", (scan_id,))
    conn.commit()
    return {"deleted": scan_id}


@app.post("/api/scans/{scan_id}/fiken", dependencies=[Depends(require_auth)])
async def api_fiken_post(scan_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Bokfor et godkjent bilag til Fiken."""
    row = get_scan(conn, scan_id)
    if not row:
        raise HTTPException(404, f"Bilag #{scan_id} finnes ikke")
    if row["status"] != ScanStatus.APPROVED.value:
        raise HTTPException(400, f"Bilag #{scan_id} har status {row['status']} — kun APPROVED kan bokfores")
    if not row["account_code"]:
        raise HTTPException(400, f"Bilag #{scan_id} mangler kontokode")
    if not row["invoice_date"]:
        raise HTTPException(400, f"Bilag #{scan_id} mangler fakturadato — legg inn dato før bokføring")

    from bilagbot.fiken import FikenClient

    client = FikenClient()
    try:
        file_path = Path(row["file_path"]) if row["file_path"] else None

        purchase_id = client.post_invoice(
            vendor_name=row["supplier_name"] or "Ukjent leverandor",
            vendor_org_number=row["supplier_org_number"],
            invoice_date=row["invoice_date"],
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
        return {"purchase_id": purchase_id, "scan": _row_to_dict(get_scan(conn, scan_id))}
    except FikenError as e:
        update_scan_status(conn, scan_id, ScanStatus.FAILED.value)
        raise HTTPException(500, f"Fiken-feil: {e}")
    finally:
        client.close()
