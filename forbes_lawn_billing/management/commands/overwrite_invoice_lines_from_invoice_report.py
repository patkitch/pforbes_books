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
    s = str(val).strip().replace("$", "")
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


def extract_service_names(line_items_text: str) -> list[str]:
    """
    Extract service names from Jobber 'Line items' like:
      '2025 Lawn Treatments (1, $58), Tip (1, $0)'
    Correctly keeps '(1, $58)' together while parsing.
    Removes the '(...)' chunk and ignores Tip.
    """
    if not line_items_text:
        return []

    # Find each "Name ( ... )" block safely, even though "(...)" contains commas.
    blocks = re.findall(r"([^()]+)\([^)]*\)", line_items_text)

    names = []
    for b in blocks:
        name = b.strip().rstrip(",").strip()
        if not name:
            continue
        if "tip" in name.lower():
            continue
        names.append(name)

    # de-dup preserving order
    seen = set()
    out = []
    for n in names:
        k = n.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out


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
        "Amount comes from Pre-tax total ($).\n"
        "Classification (ItemModel FK) comes from the first service name in Line items (Tip ignored).\n"
        "If multiple services exist, uses a 'Mixed Service - Taxable' ItemModel."
    )

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True, help="Path to Jobber INVOICE report CSV.")
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)

        parser.add_argument("--commit", action="store_true", help="Actually write changes. Default is dry-run.")
        parser.add_argument("--repost", action="store_true", help="Unpost/repost invoices after overwriting lines.")
        parser.add_argument("--unpost-only", action="store_true", help="Only unpost matching invoices; do not overwrite lines.")
        parser.add_argument("--overwrite-only", action="store_true", help="Overwrite lines but do not repost (useful if you unpost manually first).")

        parser.add_argument(
            "--mixed-item-name",
            default="Mixed Service - Taxable",
            help="ItemModel name to use when multiple services exist in Line items."
        )
        parser.add_argument("--skip-paid", action="store_true", help="Skip invoices marked paid_in_full.")

    def handle(self, *args, **opts):
        csv_path = Path(opts["csv"])
        if not csv_path.exists():
            raise CommandError(f"CSV not found: {csv_path}")

        year = opts["year"]
        month = opts["month"]
        start, end = month_range(year, month)

        commit = opts["commit"]
        repost = opts["repost"]
        unpost_only = opts["unpost_only"]
        overwrite_only = opts["overwrite_only"]
        mixed_item_name = normalize_service_name(opts["mixed_item_name"])
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

        invoices_qs = Invoice.objects.filter(
            invoice_date__gte=start,
            invoice_date__lt=end
        ).order_by("invoice_date", "invoice_number")

        self.stdout.write(self.style.NOTICE(f"\nMonth scope: {start} to {end} (exclusive)"))
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

                # Decide which ItemModel to attach
                service_names = [normalize_service_name(n) for n in extract_service_names(row.line_items_text)]
                service_names = [n for n in service_names if n]

                if len(service_names) == 0:
                    chosen_name = mixed_item_name
                    self.stdout.write(self.style.WARNING(
                        f"[{inv_no}] No service names found in Line items; using mixed item {mixed_item_name!r}"
                    ))
                elif len(service_names) == 1:
                    chosen_name = service_names[0]
                else:
                    chosen_name = mixed_item_name
                    self.stdout.write(self.style.WARNING(
                        f"[{inv_no}] Multiple services {service_names}; using mixed item {mixed_item_name!r}"
                    ))

                chosen_name = normalize_service_name(chosen_name)

                # Find ItemModel: exact match first, then a soft contains fallback
                item_model = (
                    ItemModel.objects.filter(entity=inv.entity, name__iexact=chosen_name).first()
                    or ItemModel.objects.filter(entity=inv.entity, name__icontains=chosen_name).first()
                )

                if item_model is None:
                    self.stdout.write(self.style.WARNING(
                        f"[{inv_no}] ItemModel not found for {chosen_name!r}. Leaving item_model NULL (posting may skip)."
                    ))

                pre_tax = row.pre_tax_total
                self.stdout.write(f"[{inv_no}] overwrite lines -> '{chosen_name}' @ {pre_tax}")

                if commit:
                    InvoiceLine.objects.filter(invoice=inv).delete()

                    line = InvoiceLine(
                        invoice=inv,
                        line_number=1,
                        item_model=item_model,
                        item_name=chosen_name,
                        description=chosen_name,  # keep clean (no confusing overwrite notes)
                        quantity=Decimal("1"),
                        rate=pre_tax,
                        taxable=True,  # keep True for now; your ItemModel mapping controls buckets
                    )
                    line.recompute_amount()
                    line.save()

                    if hasattr(inv, "recompute_totals"):
                        inv.recompute_totals()
                        inv.save()

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
