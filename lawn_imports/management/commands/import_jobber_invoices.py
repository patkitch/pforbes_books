# lawn_imports/management/commands/import_jobber_invoices.py

import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from django_ledger.models.entity import EntityModel
from forbes_lawn_billing.models import Invoice, InvoiceLine, InvoiceStatus

import csv
import re
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from django_ledger.models.entity import EntityModel
from forbes_lawn_billing.models import Invoice, InvoiceLine, InvoiceStatus


class Command(BaseCommand):
    help = "Import Jobber invoice CSV into Forbes Lawn Invoice/InvoiceLine models."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to Jobber invoice CSV file")
        parser.add_argument(
            "--entity",
            type=str,
            default="Forbes Lawn Spraying LLC",
            help="Name of the Django Ledger Entity to attach invoices to.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the import without saving any changes.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        entity_name = options["entity"]
        dry_run = options["dry_run"]

        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        try:
            entity = EntityModel.objects.get(name=entity_name)
        except EntityModel.DoesNotExist:
            raise CommandError(f"Entity with name '{entity_name}' not found.")

        self.stdout.write(self.style.NOTICE(f"Using entity: {entity_name}"))
        self.stdout.write(self.style.NOTICE(f"CSV: {csv_path}"))
        self.stdout.write(self.style.NOTICE(f"Mode: {'DRY RUN' if dry_run else 'COMMIT'}"))

        # Map our internal keys to your actual CSV header names
        COLUMN = {
            "invoice_number": "Invoice #",
            "customer_name": "Client name",
            "client_email": "Client email",
            "bill_to_line1": "Billing street",
            "bill_to_city": "Billing city",
            "bill_to_state": "Billing province",
            "bill_to_zip": "Billing ZIP",
            "invoice_date": "Created date",
            "issued_date": "Issued date",
            "due_date": "Due date",
            "status": "Status",
            "line_items": "Line items",
            "subtotal": "Pre-tax total ($)",
            "total": "Total ($)",
            "tip": "Tip ($)",
            "balance": "Balance ($)",
            "tax_percent": "Tax (%)",
            "deposit": "Deposit $",
            "discount": "Discount ($)",
            "tax_amount": "Tax amount ($)",
        }

        def parse_decimal(value: str) -> Decimal:
            if value is None:
                return Decimal("0.00")
            v = value.strip()
            if not v:
                return Decimal("0.00")
            # Strip $ and commas
            v = v.replace("$", "").replace(",", "")
            return Decimal(v)

        def parse_date(value: str):
            """
    Jobber actual format: 'Nov 19, 2025'
            """
            if not value:
                return None
            v = value.strip()
            if not v or v == "-":
                return None
            try:
                return timezone.datetime.strptime(v, "%b %d, %Y").date()
            except ValueError:
                # Try alternate format seen in some exports (19-Nov-25)
                try:
                    return timezone.datetime.strptime(v, "%d-%b-%y").date()
                except ValueError:
                    raise ValueError(f"Unrecognized date format: {value}")

        def parse_tax_rate_percent(value: str) -> Decimal:
            """
            e.g. "KS-Johnson-Prairie Village (8.975%)" -> Decimal("8.975")
            or "-" or "" -> Decimal("0.0")
            """
            if not value:
                return Decimal("0.0")
            m = re.search(r"([\d.]+)\s*%", value)
            if m:
                return Decimal(m.group(1))
            return Decimal("0.0")

        def parse_status(raw_status: str) -> str:
            """
            Map Jobber's Status column into our InvoiceStatus enum.
            """
            if not raw_status:
                return InvoiceStatus.DRAFT
            s = raw_status.strip().lower()
            if "paid" in s:
                return InvoiceStatus.PAID
            if "draft" in s:
                return InvoiceStatus.DRAFT
            if "void" in s or "canceled" in s:
                return InvoiceStatus.VOID
            # Sent, Awaiting payment, etc. -> treat as OPEN
            return InvoiceStatus.OPEN

        def parse_line_items(text: str, tax_rate_percent: Decimal, subtotal: Decimal):
            """
            Parse the 'Line items' string into a list of dicts:
            [
                {"name": ..., "qty": Decimal, "rate": Decimal, "taxable": bool},
                ...
            ]
            Expected format like: "2025 Lawn Treatments (1, $64)"
            If multiple exist, assume separation with ';' or '|'.
            """
            items = []
            if not text:
                return items

            # Split on ; or | if present
            segments = re.split(r"\s*[;|]\s*", text.strip())
            segments = [seg for seg in segments if seg]

            taxable_flag = tax_rate_percent > 0

            pattern = re.compile(
                r"^(?P<name>.+?)\s*\(\s*(?P<qty>[\d.]+)\s*,\s*\$(?P<rate>[\d.]+)\s*\)\s*$"
            )

            for seg in segments:
                m = pattern.match(seg)
                if m:
                    name = m.group("name").strip()
                    qty = Decimal(m.group("qty"))
                    rate = Decimal(m.group("rate"))
                else:
                    # Fallback: use full text as name, qty=1, rate based on subtotal split
                    name = seg.strip()
                    qty = Decimal("1.0")
                    # If subtotal present and multiple segments, split roughly evenly
                    if subtotal and len(segments) > 0:
                        rate = (subtotal / len(segments)).quantize(Decimal("0.01"))
                    else:
                        rate = Decimal("0.00")

                items.append(
                    {
                        "name": name or "Service",
                        "qty": qty,
                        "rate": rate,
                        "taxable": taxable_flag,
                    }
                )

            return items

        created_invoices = 0
        updated_invoices = 0
        created_lines = 0

        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                invoice_number = (row.get(COLUMN["invoice_number"]) or "").strip()
                if not invoice_number:
                    # Skip rows without an invoice number
                    continue

                customer_name = (row.get(COLUMN["customer_name"]) or "").strip()
                client_email = (row.get(COLUMN["client_email"]) or "").strip()

                bill_to_line1 = (row.get(COLUMN["bill_to_line1"]) or "").strip()
                bill_to_city = (row.get(COLUMN["bill_to_city"]) or "").strip()
                bill_to_state = (row.get(COLUMN["bill_to_state"]) or "").strip()
                bill_to_zip = (row.get(COLUMN["bill_to_zip"]) or "").strip()

                invoice_date = parse_date(row.get(COLUMN["invoice_date"]))
                due_date = parse_date(row.get(COLUMN["due_date"]))
                status_raw = (row.get(COLUMN["status"]) or "").strip()
                status = parse_status(status_raw)

                subtotal_csv = parse_decimal(row.get(COLUMN["subtotal"]))
                total_csv = parse_decimal(row.get(COLUMN["total"]))
                balance_csv = parse_decimal(row.get(COLUMN["balance"]))
                deposit_csv = parse_decimal(row.get(COLUMN["deposit"]))
                discount_csv = parse_decimal(row.get(COLUMN["discount"]))
                tax_amount_csv = parse_decimal(row.get(COLUMN["tax_amount"]))
                tax_rate_percent = parse_tax_rate_percent(row.get(COLUMN["tax_percent"]))

                line_items_text = row.get(COLUMN["line_items"]) or ""
                line_items = parse_line_items(
                    line_items_text, tax_rate_percent, subtotal_csv
                )

                # Get or create invoice by (entity, jobber_invoice_id)
                # jobber_invoice_id = Invoice # in your CSV
                jobber_invoice_id = invoice_number

                invoice = Invoice.objects.filter(
                    entity=entity, jobber_invoice_id=jobber_invoice_id
                ).first()

                created = False
                if invoice is None:
                    invoice = Invoice(
                        entity=entity,
                        jobber_invoice_id=jobber_invoice_id,
                    )
                    created = True

                # Header fields
                invoice.invoice_number = invoice_number
                invoice.customer_name = customer_name
                invoice.email_to = client_email

                invoice.bill_to_name = customer_name
                invoice.bill_to_line1 = bill_to_line1
                invoice.bill_to_city = bill_to_city
                invoice.bill_to_state = bill_to_state
                invoice.bill_to_zip = bill_to_zip

                invoice.invoice_date = invoice_date or invoice.invoice_date or timezone.localdate()
                invoice.due_date = due_date or invoice.due_date

                invoice.status = status

                # Discount & tax info: let recompute use these
                invoice.discount_amount = discount_csv
                invoice.deposit_amount = deposit_csv
                invoice.tax_rate_percent = tax_rate_percent

                if dry_run:
                    action = "CREATE" if created else "UPDATE"
                    self.stdout.write(
                        f"[DRY RUN] {action} invoice #{invoice_number} for {customer_name} "
                        f"(subtotal={subtotal_csv}, total={total_csv}, tax%={tax_rate_percent})"
                    )
                    # We don't touch DB in dry run
                    continue

                # Save the invoice header first so we have an ID
                invoice.save()

                if created:
                    created_invoices += 1
                    action = "CREATED"
                else:
                    updated_invoices += 1
                    action = "UPDATED"

                self.stdout.write(
                    f"[{action}] Invoice {invoice.invoice_number} ({customer_name})"
                )

                # Clear existing lines and recreate from CSV
                invoice.lines.all().delete()

                line_number = 1
                for li in line_items:
                    line = InvoiceLine(
                        invoice=invoice,
                        line_number=line_number,
                        item_name=li["name"],
                        description="",
                        quantity=li["qty"],
                        rate=li["rate"],
                        taxable=li["taxable"],
                    )
                    line.recompute_amount()
                    line.save()
                    created_lines += 1
                    line_number += 1

                # After creating all InvoiceLine rows...

                # TRUST JOBBER TOTALS INSTEAD OF RECOMPUTING FROM LINES
                invoice.subtotal = subtotal_csv
                invoice.tax_amount = tax_amount_csv
                invoice.total = total_csv
                invoice.tax_rate_percent = tax_rate_percent
                invoice.discount_amount = discount_csv
                invoice.deposit_amount = deposit_csv

                # Derive amount_paid / balance from Jobber's balance column
                invoice.balance_due = balance_csv
                invoice.amount_paid = (invoice.total or Decimal("0.00")) - invoice.balance_due

                # Status based on balance
                if invoice.balance_due <= Decimal("0.00"):
                    invoice.status = InvoiceStatus.PAID
                    invoice.paid_in_full = True
                elif invoice.amount_paid > Decimal("0.00"):
                    invoice.status = InvoiceStatus.PARTIALLY_PAID
                    invoice.paid_in_full = False
                else:
                    invoice.status = InvoiceStatus.OPEN
                    invoice.paid_in_full = False

                invoice.save()
             

                # If Jobber's balance is 0, mark as paid
                if balance_csv <= Decimal("0.00"):
                    invoice.status = InvoiceStatus.PAID
                    invoice.paid_in_full = True
                invoice.save()

        mode = "DRY RUN" if dry_run else "COMMIT"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] Finished reading CSV. "
                f"Invoices created/updated (not counted in dry-run): "
                f"created={created_invoices}, updated={updated_invoices}, lines_created={created_lines}"
            )
        )




class _noop_context:
    """Context manager that does nothing, used to mimic transaction.atomic in dry-run."""
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
