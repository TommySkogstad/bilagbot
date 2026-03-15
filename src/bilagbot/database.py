"""SQLite-database for BilagBot."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bilagbot.config import DB_PATH, ensure_data_dir
from bilagbot.exceptions import DatabaseError

SCHEMA = """
CREATE TABLE IF NOT EXISTS known_suppliers (
    org_number TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    account_code TEXT,
    account_name TEXT,
    vat_code TEXT,
    auto_approve BOOLEAN DEFAULT FALSE,
    approval_count INTEGER DEFAULT 0,
    last_seen_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    supplier_org_number TEXT,
    supplier_name TEXT,
    total_amount REAL,
    vat_amount REAL,
    currency TEXT DEFAULT 'NOK',
    invoice_date TEXT,
    due_date TEXT,
    invoice_number TEXT,
    match_level TEXT NOT NULL,
    account_code TEXT,
    vat_code TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    raw_claude_json TEXT,
    scanned_at TEXT NOT NULL,
    reviewed_at TEXT,
    posted_at TEXT
);

CREATE TABLE IF NOT EXISTS fiken_accounts (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    last_synced_at TEXT NOT NULL
);
"""

MIGRATIONS = [
    # Sprint 2: Fiken-felter i scan_log
    "ALTER TABLE scan_log ADD COLUMN fiken_purchase_id INTEGER",
    "ALTER TABLE scan_log ADD COLUMN fiken_posted_at TEXT",
]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Opprett databaseforbindelse og initialiser schema."""
    if db_path is None:
        ensure_data_dir()
        db_path = DB_PATH
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _run_migrations(conn)
    return conn


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Kjør migrasjoner som legger til nye kolonner (ignorerer duplikater)."""
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Kolonne finnes allerede


def insert_scan(conn: sqlite3.Connection, *, file_path: str, file_hash: str, supplier_org_number: str | None,
                supplier_name: str | None, total_amount: float | None, vat_amount: float | None,
                currency: str, invoice_date: str | None, due_date: str | None, invoice_number: str | None,
                match_level: str, account_code: str | None, vat_code: str | None,
                raw_claude_json: str) -> int:
    """Sett inn en ny scan-logg og returner ID."""
    try:
        cursor = conn.execute(
            """INSERT INTO scan_log (file_path, file_hash, supplier_org_number, supplier_name,
               total_amount, vat_amount, currency, invoice_date, due_date, invoice_number,
               match_level, account_code, vat_code, status, raw_claude_json, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
            (file_path, file_hash, supplier_org_number, supplier_name, total_amount, vat_amount,
             currency, invoice_date, due_date, invoice_number, match_level, account_code,
             vat_code, raw_claude_json, _now()),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    except sqlite3.Error as e:
        raise DatabaseError(f"Kunne ikke sette inn scan: {e}") from e


def get_scan(conn: sqlite3.Connection, scan_id: int) -> sqlite3.Row | None:
    """Hent en scan-logg etter ID."""
    return conn.execute("SELECT * FROM scan_log WHERE id = ?", (scan_id,)).fetchone()


def get_scans_by_status(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    """Hent alle scan-logger med gitt status."""
    return conn.execute("SELECT * FROM scan_log WHERE status = ? ORDER BY scanned_at DESC", (status,)).fetchall()


def get_all_scans(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Hent alle scan-logger."""
    return conn.execute("SELECT * FROM scan_log ORDER BY scanned_at DESC").fetchall()


def update_scan_status(conn: sqlite3.Connection, scan_id: int, status: str) -> None:
    """Oppdater status for en scan-logg."""
    now = _now()
    reviewed_col = "reviewed_at" if status in ("APPROVED", "REJECTED") else "posted_at" if status == "POSTED" else None
    if reviewed_col:
        conn.execute(f"UPDATE scan_log SET status = ?, {reviewed_col} = ? WHERE id = ?", (status, now, scan_id))
    else:
        conn.execute("UPDATE scan_log SET status = ? WHERE id = ?", (status, scan_id))
    conn.commit()


def update_scan_classification(conn: sqlite3.Connection, scan_id: int, *, match_level: str,
                               account_code: str | None, vat_code: str | None) -> None:
    """Oppdater klassifisering for en scan-logg."""
    conn.execute(
        "UPDATE scan_log SET match_level = ?, account_code = ?, vat_code = ? WHERE id = ?",
        (match_level, account_code, vat_code, scan_id),
    )
    conn.commit()


def find_duplicate(conn: sqlite3.Connection, file_hash: str) -> sqlite3.Row | None:
    """Sjekk om en fil allerede er skannet (basert på hash)."""
    return conn.execute("SELECT * FROM scan_log WHERE file_hash = ?", (file_hash,)).fetchone()


# --- Leverandør-CRUD ---

def get_supplier(conn: sqlite3.Connection, org_number: str) -> sqlite3.Row | None:
    """Hent en kjent leverandør etter orgnummer."""
    return conn.execute("SELECT * FROM known_suppliers WHERE org_number = ?", (org_number,)).fetchone()


def get_all_suppliers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Hent alle kjente leverandører."""
    return conn.execute("SELECT * FROM known_suppliers ORDER BY supplier_name").fetchall()


def upsert_supplier(conn: sqlite3.Connection, *, org_number: str, supplier_name: str,
                    account_code: str | None = None, account_name: str | None = None,
                    vat_code: str | None = None) -> None:
    """Opprett eller oppdater en leverandør."""
    now = _now()
    existing = get_supplier(conn, org_number)
    if existing:
        conn.execute(
            """UPDATE known_suppliers SET supplier_name = ?, account_code = COALESCE(?, account_code),
               account_name = COALESCE(?, account_name), vat_code = COALESCE(?, vat_code),
               approval_count = approval_count + 1, last_seen_at = ?, updated_at = ?
               WHERE org_number = ?""",
            (supplier_name, account_code, account_name, vat_code, now, now, org_number),
        )
    else:
        conn.execute(
            """INSERT INTO known_suppliers (org_number, supplier_name, account_code, account_name,
               vat_code, auto_approve, approval_count, last_seen_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, FALSE, 1, ?, ?, ?)""",
            (org_number, supplier_name, account_code, account_name, vat_code, now, now, now),
        )
    conn.commit()


def update_supplier_auto_approve(conn: sqlite3.Connection, org_number: str, auto_approve: bool) -> None:
    """Sett auto-approve for en leverandør."""
    conn.execute(
        "UPDATE known_suppliers SET auto_approve = ?, updated_at = ? WHERE org_number = ?",
        (auto_approve, _now(), org_number),
    )
    conn.commit()


def update_supplier_fields(conn: sqlite3.Connection, org_number: str, *,
                           account_code: str | None = None, account_name: str | None = None,
                           vat_code: str | None = None) -> None:
    """Oppdater spesifikke felt for en leverandør."""
    updates = []
    params: list = []
    if account_code is not None:
        updates.append("account_code = ?")
        params.append(account_code)
    if account_name is not None:
        updates.append("account_name = ?")
        params.append(account_name)
    if vat_code is not None:
        updates.append("vat_code = ?")
        params.append(vat_code)
    if not updates:
        return
    updates.append("updated_at = ?")
    params.append(_now())
    params.append(org_number)
    conn.execute(f"UPDATE known_suppliers SET {', '.join(updates)} WHERE org_number = ?", params)
    conn.commit()


# --- Fiken-operasjoner ---

def update_scan_fiken(conn: sqlite3.Connection, scan_id: int, purchase_id: int) -> None:
    """Lagre Fiken purchase ID og marker som POSTED."""
    now = _now()
    conn.execute(
        "UPDATE scan_log SET status = 'POSTED', fiken_purchase_id = ?, fiken_posted_at = ?, posted_at = ? WHERE id = ?",
        (purchase_id, now, now, scan_id),
    )
    conn.commit()


def sync_fiken_accounts(conn: sqlite3.Connection, accounts: list[dict]) -> int:
    """Synkroniser kontoplan fra Fiken til lokal cache. Returnerer antall kontoer."""
    now = _now()
    conn.execute("DELETE FROM fiken_accounts")
    for account in accounts:
        code = str(account.get("code", ""))
        name = account.get("name", "")
        if code and name:
            conn.execute(
                "INSERT OR REPLACE INTO fiken_accounts (code, name, last_synced_at) VALUES (?, ?, ?)",
                (code, name, now),
            )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM fiken_accounts").fetchone()[0]


def get_fiken_accounts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Hent cached Fiken-kontoplan."""
    return conn.execute("SELECT code, name FROM fiken_accounts ORDER BY code").fetchall()


def get_fiken_account(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    """Sjekk om en kontokode finnes i cached Fiken-kontoplan."""
    return conn.execute("SELECT code, name FROM fiken_accounts WHERE code = ?", (code,)).fetchone()
