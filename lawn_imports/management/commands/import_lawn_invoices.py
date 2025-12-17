# lawn_imports/management/commands/import_jobber_invoices.py

import csv
import re
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from django_ledger.models.entity import EntityModel
from django_ledger.models import CustomerModel

from forbes_lawn_billing.models import Invoice, InvoiceLine, InvoiceStatus
from lawn_imports.utils import get_or_create_dl_customer_for_jobber


def normalize_service_name(name: str) -> str:
    """
    Normalize Jobber/DB service names so they match ItemModel.name reliably.
    Fixes:
      - leading commas
      - repeated whitespace
      - trailing hyphen/dash patterns like ' -'
    """
    s = (name or "").strip()
    s = s.lstrip(",").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*-\s*$", "", s)
    return s.strip()


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
        self.stdout.write(self.style.NOTICE(">>> RUNNING NEW V4 IMPORTER <<<"))
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

        ItemModel = apps.get_model("django_ledger", "ItemModel")

        COLUMN = {
            "invoice_number": "Invoice #",
            "customer_name": "Client name",
            "client_email": "Client email",
            "client_phone": "Client phone",
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
            if not raw_status:
                return InvoiceStatus.DRAFT
            s = raw_status.strip().lower()
            if "paid" in s:
                return InvoiceStatus.PAID
            if "draft" in s:
                return InvoiceStatus.DRAFT
            if "void" in s or "canceled" in s:
                return InvoiceStatus.VOID
            return InvoiceStatus.OPEN

        def parse_line_items(text: str, tax_rate_percent: Decimal, subtotal: Decimal):
            """
            Parse Jobber's 'Line items' column into a list of dicts.

            Keeps splits exactly as Jobber lists them.
            Ignores zero-dollar lines (e.g. Tip (1, $0)).
            Normalizes service names so ItemModel lookup works (Aeration dash issue).
            """
            items = []
            if not text:
                return items

            taxable_flag = tax_rate_percent > 0

            pattern = re.compile(
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

            for m in pattern.finditer(text):
                raw_name = m.group("name")
                name = normalize_service_name(raw_name).rstrip(",")

                qty = Decimal(m.group("qty"))
                rate = Decimal(m.group("rate"))

                if rate == 0:
                    continue

                if "tip" in name.lower():
                    name = "Tip"

                items.append({"name": name or "Service", "qty": qty, "rate": rate, "taxable": taxable_flag})

            if not items and subtotal:
                items.append(
                    {"name": normalize_service_name(text.strip()) or "Service", "qty": Decimal("1.0"), "rate": subtotal, "taxable": taxable_flag}
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
                    continue

                customer_name = (row.get(COLUMN["customer_name"]) or "").strip()
                client_email = (row.get(COLUMN["client_email"]) or "").strip()
                client_phone = (row.get(COLUMN["client_phone"]) or "").strip()

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
                tip_amount_csv = parse_decimal(row.get(COLUMN["tip"]))

                raw_line_items_text = row.get(COLUMN["line_items"]) or ""
                line_items = parse_line_items(raw_line_items_text, tax_rate_percent, subtotal_csv)

                self.stdout.write(
                    self.style.NOTICE(
                        f"[DEBUG] invoice #{invoice_number} raw_line_items={raw_line_items_text!r} -> parsed={line_items!r}"
                    )
                )

                customer_action_label = "N/A"
                dl_customer = None
                created_customer = False

                if dry_run:
                    qs = CustomerModel.objects.filter(entity_model=entity, customer_name=customer_name)
                    if client_email:
                        qs = qs.filter(email__iexact=client_email)

                    customer_action_label = "EXISTING CUSTOMER" if qs.exists() else "WOULD CREATE CUSTOMER"
                else:
                    dl_customer, created_customer = get_or_create_dl_customer_for_jobber(
                        entity=entity,
                        client_name=customer_name,
                        client_email=client_email,
                        client_phone=client_phone,
                    )
                    customer_action_label = "NEW CUSTOMER" if created_customer else "EXISTING CUSTOMER"

                jobber_invoice_id = invoice_number

                invoice = Invoice.objects.filter(entity=entity, jobber_invoice_id=jobber_invoice_id).first()

                created = False
                if invoice is None:
                    invoice = Invoice(entity=entity, jobber_invoice_id=jobber_invoice_id)
                    created = True

                if not dry_run:
                    invoice.customer = dl_customer

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

                invoice.discount_amount = discount_csv
                invoice.deposit_amount = deposit_csv
                invoice.tax_rate_percent = tax_rate_percent

                if dry_run:
                    action = "CREATE" if created else "UPDATE"
                    self.stdout.write(
                        f"[DRY RUN] {action} invoice #{invoice_number} for {customer_name} "
                        f"({customer_action_label}, subtotal={subtotal_csv}, total={total_csv}, tax%={tax_rate_percent}, tip={tip_amount_csv})"
                    )
                    continue

                invoice.save()

                if created:
                    created_invoices += 1
                    action = "CREATED"
                else:
                    updated_invoices += 1
                    action = "UPDATED"

                self.stdout.write(f"[{action}] Invoice {invoice.invoice_number} ({customer_name}) [{customer_action_label}]")

                invoice.lines.all().delete()

                line_number = 1
                for li in line_items:
                    item_name = normalize_service_name(li["name"])

                    item_model = ItemModel.objects.filter(entity=entity, name__iexact=item_name).first()
                    if item_model is None:
                        self.stdout.write(self.style.WARNING(
                            f"[DEBUG] No ItemModel found. item_name={item_name!r} (entity={entity.slug})"
                        ))

                    line = InvoiceLine(
                        invoice=invoice,
                        line_number=line_number,
                        item_model=item_model,
                        item_name=item_name,
                        description="",
                        quantity=li["qty"],
                        rate=li["rate"],
                        taxable=li["taxable"],
                    )
                    line.recompute_amount()
                    line.save()
                    created_lines += 1
                    line_number += 1

                # Trust Jobber totals
                invoice.subtotal = subtotal_csv
                invoice.tax_amount = tax_amount_csv
                invoice.total = total_csv
                invoice.tax_rate_percent = tax_rate_percent
                invoice.discount_amount = discount_csv
                invoice.deposit_amount = deposit_csv

                invoice.balance_due = balance_csv
                invoice.amount_paid = (invoice.total or Decimal("0.00")) - invoice.balance_due

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

        mode = "DRY RUN" if dry_run else "COMMIT"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] Finished reading CSV. "
                f"Invoices created/updated (not counted in dry-run): created={created_invoices}, updated={updated_invoices}, lines_created={created_lines}"
            )
        )
