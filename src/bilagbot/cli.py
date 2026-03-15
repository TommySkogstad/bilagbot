"""CLI for BilagBot — Click-basert kommandogrensesnitt."""

from pathlib import Path

import click

from bilagbot.classifier import ClassificationResult, classify, learn_from_approval
from bilagbot.database import (
    find_duplicate,
    get_connection,
    get_fiken_accounts,
    get_scan,
    get_scans_by_status,
    get_supplier,
    insert_scan,
    sync_fiken_accounts,
    update_scan_classification,
    update_scan_fiken,
    update_scan_status,
    update_supplier_fields,
)
from bilagbot.exceptions import FikenError, ScannerError
from bilagbot.models import InvoiceData, MatchLevel
from bilagbot.review import console, show_pending_list, show_scan_detail, show_status_summary, show_suppliers
from bilagbot.scanner import file_hash, scan_file

SCAN_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"}


@click.group()
@click.version_option(package_name="bilagbot")
def main():
    """BilagBot — AI-drevet bilagsscanner."""


@main.command()
@click.argument("path", type=click.Path(exists=True))
def scan(path: str):
    """Scan en faktura (PDF/bilde) eller alle filer i en mappe."""
    target = Path(path)
    files = []

    if target.is_dir():
        files = sorted(f for f in target.iterdir() if f.suffix.lower() in SCAN_EXTENSIONS)
        if not files:
            console.print(f"[yellow]Ingen støttede filer funnet i {target}[/yellow]")
            return
        console.print(f"Fant [bold]{len(files)}[/bold] filer å skanne i {target}")
    else:
        files = [target]

    conn = get_connection()
    for file in files:
        _scan_single_file(conn, file)
    conn.close()


def _scan_single_file(conn, file: Path) -> None:
    """Scan én enkelt fil."""
    console.print(f"\n[bold blue]Skanner:[/bold blue] {file.name}")

    # Duplikatsjekk
    fhash = file_hash(file)
    dup = find_duplicate(conn, fhash)
    if dup:
        console.print(f"  [yellow]⚠ Allerede skannet (bilag #{dup['id']})[/yellow]")
        return

    # Scan med Claude
    try:
        invoice, raw_json = scan_file(file)
    except ScannerError as e:
        console.print(f"  [red]✗ Feil: {e}[/red]")
        return

    # Klassifiser
    result: ClassificationResult = classify(conn, invoice)

    # Lagre i database
    scan_id = insert_scan(
        conn,
        file_path=str(file.resolve()),
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

    # Vis resultat
    match_colors = {MatchLevel.UNKNOWN: "red", MatchLevel.KNOWN: "yellow", MatchLevel.AUTO: "green"}
    color = match_colors[result.match_level]

    console.print(f"  [green]✓[/green] Bilag #{scan_id}")
    console.print(f"    Leverandør: {result.supplier_name or 'Ukjent'}")
    if invoice.vendor_org_number:
        console.print(f"    Org.nr: {invoice.vendor_org_number}")
    console.print(f"    Beløp: {invoice.total_amount or 0:,.2f} {invoice.currency}")
    console.print(f"    Match: [{color}]{result.match_level.value}[/{color}]")
    if result.account_code:
        console.print(f"    Konto: {result.account_code}")


@main.command()
def review():
    """Vis ventende bilag for review."""
    conn = get_connection()
    rows = show_pending_list(conn)
    if rows:
        console.print("\nBruk [bold]bilag approve <id>[/bold] eller [bold]bilag reject <id>[/bold]")
    conn.close()


@main.command()
@click.argument("scan_id", type=int)
@click.option("--account", "-a", help="Override kontokode")
@click.option("--vat", "-v", help="Override MVA-kode")
def approve(scan_id: int, account: str | None, vat: str | None):
    """Godkjenn et bilag og lær leverandøren."""
    conn = get_connection()
    row = get_scan(conn, scan_id)
    if not row:
        console.print(f"[red]Bilag #{scan_id} finnes ikke[/red]")
        conn.close()
        return

    if row["status"] != "PENDING":
        console.print(f"[yellow]Bilag #{scan_id} har status {row['status']}, kan ikke godkjennes[/yellow]")
        conn.close()
        return

    # Bruk override eller eksisterende verdier
    final_account = account or row["account_code"]
    final_vat = vat or row["vat_code"]

    # Oppdater klassifisering hvis override
    if account or vat:
        update_scan_classification(
            conn, scan_id,
            match_level=row["match_level"],
            account_code=final_account,
            vat_code=final_vat,
        )

    update_scan_status(conn, scan_id, "APPROVED")

    # Lær leverandøren
    invoice = InvoiceData(
        vendor_name=row["supplier_name"],
        vendor_org_number=row["supplier_org_number"],
    )
    learn_from_approval(conn, invoice, account_code=final_account, vat_code=final_vat)

    show_scan_detail(get_scan(conn, scan_id))
    console.print(f"[green]✓ Bilag #{scan_id} godkjent[/green]")

    # Sjekk om leverandør nå er auto-approved
    if row["supplier_org_number"]:
        supplier = get_supplier(conn, row["supplier_org_number"])
        if supplier and supplier["auto_approve"]:
            console.print(f"[green]★ {supplier['supplier_name']} er nå auto-godkjent![/green]")

    conn.close()


@main.command()
@click.argument("scan_id", type=int)
def reject(scan_id: int):
    """Avvis et bilag."""
    conn = get_connection()
    row = get_scan(conn, scan_id)
    if not row:
        console.print(f"[red]Bilag #{scan_id} finnes ikke[/red]")
        conn.close()
        return

    if row["status"] != "PENDING":
        console.print(f"[yellow]Bilag #{scan_id} har status {row['status']}, kan ikke avvises[/yellow]")
        conn.close()
        return

    update_scan_status(conn, scan_id, "REJECTED")
    console.print(f"[red]✗ Bilag #{scan_id} avvist[/red]")
    conn.close()


@main.command()
def status():
    """Vis oversikt over alle bilag."""
    conn = get_connection()
    show_status_summary(conn)
    conn.close()


@main.group()
def suppliers():
    """Vis og rediger kjente leverandører."""


@suppliers.command("list")
def suppliers_list():
    """Vis alle kjente leverandører."""
    conn = get_connection()
    show_suppliers(conn)
    conn.close()


@suppliers.command("edit")
@click.argument("org_number")
@click.option("--account", "-a", help="Kontokode")
@click.option("--vat", "-v", help="MVA-kode")
@click.option("--auto/--no-auto", default=None, help="Sett auto-approve")
def suppliers_edit(org_number: str, account: str | None, vat: str | None, auto: bool | None):
    """Rediger en leverandør."""
    conn = get_connection()
    supplier = get_supplier(conn, org_number)
    if not supplier:
        console.print(f"[red]Leverandør {org_number} finnes ikke[/red]")
        conn.close()
        return

    if account or vat:
        update_supplier_fields(conn, org_number, account_code=account, vat_code=vat)
    if auto is not None:
        from bilagbot.database import update_supplier_auto_approve
        update_supplier_auto_approve(conn, org_number, auto)

    supplier = get_supplier(conn, org_number)
    console.print(f"[green]✓ {supplier['supplier_name']} oppdatert[/green]")
    console.print(f"  Konto: {supplier['account_code'] or '—'}")
    console.print(f"  MVA: {supplier['vat_code'] or '—'}")
    console.print(f"  Auto: {'Ja' if supplier['auto_approve'] else 'Nei'}")
    conn.close()


# --- Fiken-kommandoer ---

@main.group()
def fiken():
    """Fiken API-integrasjon."""


@fiken.command("validate")
def fiken_validate():
    """Test Fiken API-forbindelse."""
    from bilagbot.config import FIKEN_API_TOKEN, FIKEN_COMPANY_SLUG

    if not FIKEN_API_TOKEN or not FIKEN_COMPANY_SLUG:
        console.print("[red]FIKEN_API_TOKEN og FIKEN_COMPANY_SLUG må settes i .env[/red]")
        return

    from bilagbot.fiken import FikenClient

    try:
        client = FikenClient()
        company = client.validate()
        console.print("[green]✓ Koblet til Fiken[/green]")
        console.print(f"  Firma: {company.get('name', '?')}")
        console.print(f"  Org.nr: {company.get('organizationNumber', '?')}")
        console.print(f"  API-tilgang: {'Ja' if company.get('hasApiAccess') else '[red]Nei[/red]'}")
        client.close()
    except FikenError as e:
        console.print(f"[red]✗ Feil: {e}[/red]")


@fiken.command("sync-accounts")
def fiken_sync_accounts():
    """Synkroniser kontoplan fra Fiken."""
    from bilagbot.fiken import FikenClient

    try:
        client = FikenClient()
        accounts = client.get_accounts()
        conn = get_connection()
        count = sync_fiken_accounts(conn, accounts)
        console.print(f"[green]✓ Synkronisert {count} kontoer fra Fiken[/green]")
        conn.close()
        client.close()
    except FikenError as e:
        console.print(f"[red]✗ Feil: {e}[/red]")


@fiken.command("accounts")
def fiken_accounts_list():
    """Vis cached kontoplan fra Fiken."""
    conn = get_connection()
    accounts = get_fiken_accounts(conn)
    if not accounts:
        console.print("[yellow]Ingen kontoer i cache. Kjør 'bilag fiken sync-accounts' først.[/yellow]")
    else:
        from rich.table import Table

        table = Table(title=f"Fiken-kontoplan ({len(accounts)} kontoer)")
        table.add_column("Kode", style="bold")
        table.add_column("Navn")
        for acc in accounts:
            table.add_row(acc["code"], acc["name"])
        console.print(table)
    conn.close()


@fiken.command("post")
@click.argument("scan_id", type=int)
def fiken_post(scan_id: int):
    """Bokfør et godkjent bilag til Fiken."""
    conn = get_connection()
    row = get_scan(conn, scan_id)
    if not row:
        console.print(f"[red]Bilag #{scan_id} finnes ikke[/red]")
        conn.close()
        return

    if row["status"] != "APPROVED":
        console.print(f"[yellow]Bilag #{scan_id} har status {row['status']} — kun APPROVED kan bokføres[/yellow]")
        conn.close()
        return

    if not row["account_code"]:
        console.print(f"[red]Bilag #{scan_id} mangler kontokode — bruk 'bilag approve {scan_id} -a <konto>'[/red]")
        conn.close()
        return

    from bilagbot.fiken import FikenClient

    try:
        client = FikenClient()
        file_path = Path(row["file_path"]) if row["file_path"] else None

        purchase_id = client.post_invoice(
            vendor_name=row["supplier_name"] or "Ukjent leverandør",
            vendor_org_number=row["supplier_org_number"],
            invoice_date=row["invoice_date"] or "1970-01-01",
            due_date=row["due_date"],
            invoice_number=row["invoice_number"],
            payment_reference=None,
            total_amount=row["total_amount"] or 0,
            account_code=row["account_code"],
            vat_code=row["vat_code"],
            description=row["supplier_name"] or "Kjøp",
            file_path=file_path,
        )

        update_scan_fiken(conn, scan_id, purchase_id)
        console.print(f"[green]✓ Bilag #{scan_id} bokført til Fiken (kjøp #{purchase_id})[/green]")
        client.close()
    except FikenError as e:
        update_scan_status(conn, scan_id, "FAILED")
        console.print(f"[red]✗ Fiken-feil: {e}[/red]")
    finally:
        conn.close()


@fiken.command("post-pending")
def fiken_post_pending():
    """Bokfør alle godkjente bilag til Fiken."""
    conn = get_connection()
    approved = get_scans_by_status(conn, "APPROVED")

    if not approved:
        console.print("[yellow]Ingen godkjente bilag å bokføre.[/yellow]")
        conn.close()
        return

    postable = [r for r in approved if r["account_code"]]
    skipped = len(approved) - len(postable)

    if skipped:
        console.print(f"[yellow]Hopper over {skipped} bilag uten kontokode[/yellow]")

    if not postable:
        console.print("[yellow]Ingen bilag med kontokode å bokføre.[/yellow]")
        conn.close()
        return

    from bilagbot.fiken import FikenClient

    try:
        client = FikenClient()
        success = 0
        failed = 0

        for row in postable:
            try:
                file_path = Path(row["file_path"]) if row["file_path"] else None
                purchase_id = client.post_invoice(
                    vendor_name=row["supplier_name"] or "Ukjent leverandør",
                    vendor_org_number=row["supplier_org_number"],
                    invoice_date=row["invoice_date"] or "1970-01-01",
                    due_date=row["due_date"],
                    invoice_number=row["invoice_number"],
                    payment_reference=None,
                    total_amount=row["total_amount"] or 0,
                    account_code=row["account_code"],
                    vat_code=row["vat_code"],
                    description=row["supplier_name"] or "Kjøp",
                    file_path=file_path,
                )
                update_scan_fiken(conn, row["id"], purchase_id)
                console.print(f"  [green]✓[/green] #{row['id']} → kjøp #{purchase_id}")
                success += 1
            except FikenError as e:
                update_scan_status(conn, row["id"], "FAILED")
                console.print(f"  [red]✗[/red] #{row['id']}: {e}")
                failed += 1

        console.print(f"\n[bold]Resultat: {success} bokført, {failed} feilet[/bold]")
        client.close()
    except FikenError as e:
        console.print(f"[red]✗ Fiken-feil: {e}[/red]")
    finally:
        conn.close()
