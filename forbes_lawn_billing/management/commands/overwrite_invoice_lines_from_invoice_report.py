import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


# ----------------------------
# Helpers
# ----------------------------

def dec(val) -> Decimal:
    """Decimal-safe conversion. Accepts '', None, '70.20', '$70.20'."""
    if val is None:
        return Decimal("0")
    s = str(val).strip().replace("$", "").replace(",", "")
    if s == "":
        return Decimal("0")
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise CommandError(f"Cannot parse Decimal from {val!r}") from e


def month_range(year: int, month: int) -> tuple[date, date]:
    """Returns [start, end_exclusive) range."""
    if month < 1 or month > 12:
        raise CommandError("month must be 1..12")
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def year_range(year: int) -> tuple[date, date]:
    """Returns [start, end_exclusive) for full year."""
    return date(year, 1, 1), date(year + 1, 1, 1)


def parse_jobber_date(raw: str):
    """
    Parse Jobber-style dates into a date object.
    Handles:
      - 'Dec 16, 2025'
      - '7-Mar-25'
      - '03/07/2025'
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    for fmt in ("%b %d, %Y", "%d-%b-%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def normalize_service_name(name: str) -> str:
    """
    Normalize Jobber/DB service names so they match ItemModel.name reliably.
    Fixes:
      - leading commas
      - repeated whitespace
      - trailing hyphen/dash patterns like ' -'
    """
    s = (name or "").strip()

    # Sometimes Jobber output has leading comma before the service name
    s = s.lstrip(",").strip()

    # Collapse any weird spacing (Jobber likes double spaces)
    s = re.sub(r"\s+", " ", s)

    # Remove trailing dash like "... -"
    s = re.sub(r"\s*-\s*$", "", s)

    return s.strip()


_LINE_ITEM_PATTERN = re.compile(
    r"""
    (?P<name>[^()]+?)        # text up to '(' (no parentheses)
    \(\s*
    (?P<qty>[\d.]+)          # quantity
    \s*,\s*\$
    (?P<rate>[\d.]+)         # rate
    \s*\)
    """,
    re.VERBOSE,
)


def parse_line_items(text: str) -> list[dict]:
    """
    Parse Jobber 'Line items' like:
      "2025 Lawn Treatments (1, $55), AER/S Fall Aeration... (1, $55), Tip (1, $0)"

    Returns list of:
      {"name": str, "qty": Decimal, "rate": Decimal}

    Rules:
      - Normalizes names (comma/space/dash cleanup)
      - Ignores lines with rate == 0.00 (including Tip $0)
      - Keeps Tip if it has a nonzero rate (so you can capture missing tips)
    """
    items: list[dict] = []
    if not text:
        return items

    for m in _LINE_ITEM_PATTERN.finditer(text):
        raw_name = m.group("name")
        name = normalize_service_name(raw_name)

        qty = Decimal(m.group("qty"))
        rate = Decimal(m.group("rate"))

        if rate == Decimal("0") or rate == Decimal("0.00"):
            continue

        # Normalize any line that contains 'tip' into 'Tip'
        if "tip" in name.lower():
            name = "Tip"

        items.append({"name": name or "Service", "qty": qty, "rate": rate})

    return items


# ----------------------------
# Report row struct
# ----------------------------

@dataclass
class ReportRow:
    invoice_number: str
    client_name: str
    issued_date: date
    pre_tax_total: Decimal
    tax_amount: Decimal
    total: Decimal
    job_numbers_raw: str
    line_items_text: str


# ----------------------------
# Command
# ----------------------------

class Command(BaseCommand):
    help = (
        "Backfill Job #s and overwrite invoice lines from Jobber Invoice report.\n"
        "Creates 1+ InvoiceLine rows by parsing Jobber 'Line items' (preserves splits).\n"
        "Normalizes service names so they match ItemModel.name.\n"
        "Optionally unpost/repost invoices after overwriting lines.\n"
    )

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True, help="Path to Jobber INVOICE report CSV.")
        parser.add_argument("--year", type=int, required=True)

        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--month", type=int, help="Month 1..12")
        group.add_argument("--all-year", action="store_true", help="Process the full year.")

        parser.add_argument("--commit", action="store_true", help="Actually write changes. Default is dry-run.")
        parser.add_argument("--repost", action="store_true", help="Unpost/repost invoices after overwriting lines.")
        parser.add_argument("--unpost-only", action="store_true", help="Only unpost matching invoices; do not overwrite lines.")
        parser.add_argument("--overwrite-only", action="store_true", help="Overwrite lines but do not repost.")

        parser.add_argument("--skip-paid", action="store_true", help="Skip invoices marked paid_in_full.")

    def handle(self, *args, **opts):
        csv_path = Path(opts["csv"])
        if not csv_path.exists():
            raise CommandError(f"CSV not found: {csv_path}")

        year = opts["year"]
        month = opts.get("month")
        all_year = opts.get("all_year", False)

        if all_year:
            start, end = year_range(year)
            scope_label = f"{year}-FULL"
        else:
            if not month:
                raise CommandError("You must provide --month OR --all-year.")
            start, end = month_range(year, month)
            scope_label = f"{year}-{month:02d}"

        commit = opts["commit"]
        repost = opts["repost"]
        unpost_only = opts["unpost_only"]
        overwrite_only = opts["overwrite_only"]
        skip_paid = opts["skip_paid"]

        if unpost_only and overwrite_only:
            raise CommandError("--unpost-only and --overwrite-only cannot be used together.")

        # Lazy model loading (safe in management commands)
        Invoice = apps.get_model("forbes_lawn_billing", "Invoice")
        InvoiceLine = apps.get_model("forbes_lawn_billing", "InvoiceLine")
        ItemModel = apps.get_model("django_ledger", "ItemModel")

        rows = self._load_invoice_report(csv_path, start, end)
        by_invoice_no = {r.invoice_number: r for r in rows if r.invoice_number}

        scanned = 0
        changed = 0
        skipped = 0
        missing = 0

        invoices_qs = (
            Invoice.objects.filter(invoice_date__gte=start, invoice_date__lt=end)
            .order_by("invoice_date", "invoice_number")
        )

        self.stdout.write(self.style.NOTICE(f"\nScope: {scope_label}  ({start} to {end} exclusive)"))
        self.stdout.write(self.style.NOTICE(f"DB invoices in scope: {invoices_qs.count()}"))
        self.stdout.write(self.style.NOTICE(f"CSV rows in scope: {len(rows)}"))
        self.stdout.write(self.style.NOTICE(f"MODE: {'COMMIT' if commit else 'DRY RUN'}\n"))

        ctx = transaction.atomic if commit else _noop_context

        with ctx():
            for inv in invoices_qs:
                scanned += 1

                if skip_paid and getattr(inv, "paid_in_full", False):
                    self.stdout.write(self.style.WARNING(f"[{inv.invoice_number}] SKIP paid_in_full"))
                    skipped += 1
                    continue

                inv_no = str(getattr(inv, "invoice_number", "")).strip()
                row = by_invoice_no.get(inv_no)
                if row is None:
                    missing += 1
                    continue

                # Backfill Job #s
                if row.job_numbers_raw and getattr(inv, "jobber_job_numbers_raw", "") != row.job_numbers_raw:
                    self.stdout.write(
                        f"[{inv_no}] job# backfill: {getattr(inv, 'jobber_job_numbers_raw', '')!r} -> {row.job_numbers_raw!r}"
                    )
                    if commit:
                        inv.jobber_job_numbers_raw = row.job_numbers_raw
                        inv.save(update_fields=["jobber_job_numbers_raw"])

                if unpost_only:
                    self._maybe_unpost(inv, commit=commit)
                    changed += 1
                    continue

                if repost and not overwrite_only:
                    self._maybe_unpost(inv, commit=commit)

                parsed_items = parse_line_items(row.line_items_text)

                # Fallback: if Jobber didn't parse into blocks, use a single line using pre-tax total
                if not parsed_items:
                    fallback_name = normalize_service_name(row.line_items_text) or "Service"
                    parsed_items = [{"name": fallback_name, "qty": Decimal("1.0"), "rate": row.pre_tax_total}]

                # Resolve item models per line
                resolved = []
                for li in parsed_items:
                    name = normalize_service_name(li["name"])
                    item_model = (
                        ItemModel.objects.filter(entity=inv.entity, name__iexact=name).first()
                        or ItemModel.objects.filter(entity=inv.entity, name__icontains=name).first()
                    )
                    resolved.append((name, li["qty"], li["rate"], item_model))

                # Debug summary
                names_only = [n for (n, _, _, _) in resolved]
                if len(names_only) > 1:
                    self.stdout.write(self.style.NOTICE(
                        f"[{inv_no}] split -> {names_only}  (sum={sum((r for (_, _, r, _) in resolved), Decimal('0.00'))})"
                    ))

                if commit:
                    InvoiceLine.objects.filter(invoice=inv).delete()

                    line_number = 1
                    for (name, qty, rate, item_model) in resolved:
                        if item_model is None:
                            self.stdout.write(self.style.WARNING(
                                f"[{inv_no}] ItemModel not found for {name!r}. "
                                f"Line will remain unclassified (posting may skip it)."
                            ))

                        line = InvoiceLine(
                            invoice=inv,
                            line_number=line_number,
                            item_model=item_model,
                            item_name=name,
                            description=name,   # clean description (your preference)
                            quantity=qty,
                            rate=rate,
                            taxable=True,       # retained; posting uses item_model + earnings_account, not this flag
                        )
                        line.recompute_amount()
                        line.save()
                        line_number += 1

                    # IMPORTANT: keep Jobber totals authoritative (matches your importer philosophy)
                    inv.subtotal = row.pre_tax_total
                    inv.tax_amount = row.tax_amount
                    inv.total = row.total
                    inv.save(update_fields=["subtotal", "tax_amount", "total"])

                if repost and not overwrite_only:
                    self._maybe_post(inv, commit=commit)

                changed += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDONE. scanned={scanned} changed={changed} missing_csv_match={missing} skipped={skipped}"
        ))
        if not commit:
            self.stdout.write(self.style.WARNING("Dry-run mode: no changes were written."))

    def _load_invoice_report(self, csv_path: Path, start: date, end: date) -> list[ReportRow]:
        rows: list[ReportRow] = []
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                raw = (r.get("Issued date") or "").strip()
                issued = parse_jobber_date(raw)
                if not issued:
                    continue
                if not (start <= issued < end):
                    continue

                invoice_no = (r.get("Invoice #") or "").strip()
                client = (r.get("Client name") or "").strip()
                job_numbers = (r.get("Job #s") or "").strip()
                line_items_text = (r.get("Line items") or "").strip()

                pre_tax_total = dec(r.get("Pre-tax total ($)") or "0")
                tax_amount = dec(r.get("Tax amount ($)") or "0")
                total = dec(r.get("Total ($)") or "0")

                rows.append(ReportRow(
                    invoice_number=invoice_no,
                    client_name=client,
                    issued_date=issued,
                    pre_tax_total=pre_tax_total,
                    tax_amount=tax_amount,
                    total=total,
                    job_numbers_raw=job_numbers,
                    line_items_text=line_items_text,
                ))
        return rows

    def _maybe_unpost(self, inv, commit: bool):
        if hasattr(inv, "unpost"):
            self.stdout.write(f"  - unpost invoice {inv.invoice_number}")
            if commit:
                inv.unpost()
        else:
            self.stdout.write(self.style.WARNING(
                f"  - invoice {inv.invoice_number}: no unpost() method found; skipping unpost"
            ))

    def _maybe_post(self, inv, commit: bool):
        if hasattr(inv, "post"):
            self.stdout.write(f"  - repost invoice {inv.invoice_number}")
            if commit:
                inv.post()
        else:
            self.stdout.write(self.style.WARNING(
                f"  - invoice {inv.invoice_number}: no post() method found; skipping post"
            ))


class _noop_context:
    def __enter__(self): return None
    def __exit__(self, exc_type, exc, tb): return False
