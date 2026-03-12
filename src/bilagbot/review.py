"""Interaktiv review av skannede bilag med Rich."""

import sqlite3

from rich.console import Console
from rich.table import Table

from bilagbot.database import get_scans_by_status

console = Console()


def format_amount(amount: float | None) -> str:
    """Formater beløp med tusenskilletegn."""
    if amount is None:
        return "—"
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


def show_scan_detail(row: sqlite3.Row) -> None:
    """Vis detaljert info om ett bilag."""
    table = Table(title=f"Bilag #{row['id']}", show_header=False, border_style="blue")
    table.add_column("Felt", style="bold cyan", width=20)
    table.add_column("Verdi")

    table.add_row("Fil", row["file_path"])
    table.add_row("Leverandør", row["supplier_name"] or "—")
    table.add_row("Org.nummer", row["supplier_org_number"] or "—")
    table.add_row("Fakturanr.", row["invoice_number"] or "—")
    table.add_row("Fakturadato", row["invoice_date"] or "—")
    table.add_row("Forfallsdato", row["due_date"] or "—")
    table.add_row("Beløp", f"{format_amount(row['total_amount'])} {row['currency']}")
    table.add_row("MVA", format_amount(row["vat_amount"]))
    table.add_row("Konto", row["account_code"] or "—")
    table.add_row("MVA-kode", row["vat_code"] or "—")
    table.add_row("Match", row["match_level"])
    table.add_row("Status", row["status"])
    table.add_row("Skannet", row["scanned_at"])

    console.print(table)


def show_pending_list(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Vis alle ventende bilag og returner listen."""
    rows = get_scans_by_status(conn, "PENDING")
    if not rows:
        console.print("[dim]Ingen ventende bilag.[/dim]")
        return []

    table = Table(title="Ventende bilag", border_style="yellow")
    table.add_column("ID", style="bold", justify="right")
    table.add_column("Leverandør")
    table.add_column("Beløp", justify="right")
    table.add_column("Dato")
    table.add_column("Match", justify="center")
    table.add_column("Konto")

    for row in rows:
        match_style = {"UNKNOWN": "red", "KNOWN": "yellow", "AUTO": "green"}.get(row["match_level"], "white")
        table.add_row(
            str(row["id"]),
            row["supplier_name"] or "Ukjent",
            f"{format_amount(row['total_amount'])} {row['currency']}",
            row["invoice_date"] or "—",
            f"[{match_style}]{row['match_level']}[/{match_style}]",
            row["account_code"] or "—",
        )

    console.print(table)
    return rows


def show_status_summary(conn: sqlite3.Connection) -> None:
    """Vis statusoversikt for alle bilag."""
    from bilagbot.database import get_all_scans

    rows = get_all_scans(conn)
    if not rows:
        console.print("[dim]Ingen bilag i databasen.[/dim]")
        return

    counts: dict[str, int] = {}
    total_amount = 0.0
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        if row["total_amount"]:
            total_amount += row["total_amount"]

    table = Table(title="Bilagsoversikt", border_style="blue")
    table.add_column("Status", style="bold")
    table.add_column("Antall", justify="right")

    status_styles = {"PENDING": "yellow", "APPROVED": "green", "REJECTED": "red",
                     "POSTED": "blue", "FAILED": "red bold"}
    for status, count in sorted(counts.items()):
        style = status_styles.get(status, "white")
        table.add_row(f"[{style}]{status}[/{style}]", str(count))

    table.add_row("", "")
    table.add_row("[bold]Totalt[/bold]", str(len(rows)))

    console.print(table)
    console.print(f"\nTotalbeløp: [bold]{format_amount(total_amount)} NOK[/bold]")


def show_suppliers(conn: sqlite3.Connection) -> None:
    """Vis alle kjente leverandører."""
    from bilagbot.database import get_all_suppliers

    suppliers = get_all_suppliers(conn)
    if not suppliers:
        console.print("[dim]Ingen kjente leverandører.[/dim]")
        return

    table = Table(title="Kjente leverandører", border_style="green")
    table.add_column("Org.nr", style="bold")
    table.add_column("Navn")
    table.add_column("Konto")
    table.add_column("MVA-kode")
    table.add_column("Auto", justify="center")
    table.add_column("Godkj.", justify="right")

    for s in suppliers:
        auto = "[green]✓[/green]" if s["auto_approve"] else "[dim]—[/dim]"
        table.add_row(
            s["org_number"],
            s["supplier_name"],
            s["account_code"] or "—",
            s["vat_code"] or "—",
            auto,
            str(s["approval_count"]),
        )

    console.print(table)
