import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Sum

from django_ledger.models.entity import EntityModel
from forbes_lawn_billing.models import Invoice, InvoicePayment, InvoiceStatus


class Command(BaseCommand):
    help = "Import Jobber payment CSV and attach payments to Forbes Lawn invoices."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to Jobber payment CSV file")
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

        COLUMN = {
            "client_name": "Client name",
            "date": "Date",
            "time": "Time",
            "type": "Type",
            "paid_with": "Paid with",
            "paid_through": "Paid through",
            "total": "Total $",
            "tip": "Tip $",
            "fee": "Fee $",
            "note": "Note",
            "card_last4": "Card ending #",
            "card_type": "Card type",
            "invoice_number": "Invoice #",
            "quote_number": "Quote #",
            "payout_id": "Payout #",
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
            Handles all known Jobber date formats:
            - 3-Dec-25
            - 29-Nov-25
            - Dec 03, 2025
            - Nov 19, 2025
            - 2025-12-03 (just in case)
            """
            if not value:
                return None
            v = value.strip()
            if not v or v == "-":
                return None

            FORMATS = [
                "%d-%b-%y",      # 3-Dec-25
                "%b %d, %Y",     # Dec 03, 2025  / Nov 19, 2025
                "%Y-%m-%d",      # 2025-12-03 (rare but possible)
        ]

            for fmt in FORMATS:
                try:
                    return timezone.datetime.strptime(v, fmt).date()
                except ValueError:
                    continue

            raise ValueError(f"Unrecognized Jobber date format: {value!r}")

        def recompute_invoice_payment_state(invoice: Invoice):
            """
            After payments change, recalc amount_paid, balance_due, and status.
            """
            agg = invoice.payments.aggregate(total=Sum("amount"))
            amount_paid = agg["total"] or Decimal("0.00")

            invoice.amount_paid = amount_paid
            invoice.balance_due = (invoice.total or Decimal("0.00")) - amount_paid

            if invoice.balance_due <= Decimal("0.00"):
                invoice.status = InvoiceStatus.PAID
                invoice.paid_in_full = True
            elif amount_paid > Decimal("0.00"):
                invoice.status = InvoiceStatus.PARTIALLY_PAID
                invoice.paid_in_full = False
            else:
                # No payments -> leave OPEN or DRAFT as-is, but not PAID
                if invoice.status == InvoiceStatus.PAID:
                    invoice.status = InvoiceStatus.OPEN
                invoice.paid_in_full = False

            invoice.save()

        created_payments = 0
        skipped_existing = 0
        invoices_touched = set()

        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                invoice_number = (row.get(COLUMN["invoice_number"]) or "").strip()
                if not invoice_number:
                    continue  # no invoice ref, nothing to attach

                client_name = (row.get(COLUMN["client_name"]) or "").strip()
                date_raw = row.get(COLUMN["date"]) or ""
                time_raw = row.get(COLUMN["time"]) or ""
                paid_with = (row.get(COLUMN["paid_with"]) or "").strip()
                paid_through = (row.get(COLUMN["paid_through"]) or "").strip()
                total_raw = row.get(COLUMN["total"]) or ""
                note = (row.get(COLUMN["note"]) or "").strip()
                card_last4 = (row.get(COLUMN["card_last4"]) or "").strip()
                card_type = (row.get(COLUMN["card_type"]) or "").strip()
                payout_id = (row.get(COLUMN["payout_id"]) or "").strip()

                payment_date = parse_date(date_raw)
                if payment_date is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping row for invoice #{invoice_number}: could not parse date '{date_raw}'"
                        )
                    )
                    continue

                raw_amount = parse_decimal(total_raw)
                amount = abs(raw_amount)  # Jobber exports negative for money you receive

                # Lookup invoice by entity + invoice_number (which matches Jobber's Invoice #)
                invoice = (
                    Invoice.objects.filter(entity=entity, invoice_number=invoice_number)
                    .order_by("-invoice_date")
                    .first()
                )
                if invoice is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Invoice #{invoice_number} not found for payment row (client={client_name}, amount={amount})."
                        )
                    )
                    continue

                # Build a dedupe fingerprint: invoice + date + amount
                lookup = {
                    "invoice": invoice,
                    "date": payment_date,
                    "amount": amount,
                }

                # Extra info if your model has method/reference
                payment_kwargs = {}
                method_value = f"{paid_with} via {paid_through}".strip()
               
                #reference_parts = []
                #if note:
                    #reference_parts.append(note)
                #if card_type or card_last4:
                    #reference_parts.append(f"{card_type} {card_last4}".strip())
                #if payout_id:
                    #reference_parts.append(f"Payout {payout_id}")
                #reference_value = " | ".join(part for part in reference_parts if part)

                #if hasattr(InvoicePayment, "method"):
                    #payment_kwargs["method"] = method_value
                #if hasattr(InvoicePayment, "reference"):
                    #payment_kwargs["reference"] = reference_value

                if dry_run:
                    # Check if this payment already exists
                    exists = InvoicePayment.objects.filter(**lookup).exists()
                    if exists:
                        skipped_existing += 1
                        self.stdout.write(
                            f"[DRY RUN] SKIP existing payment for invoice #{invoice_number} "
                            f"on {payment_date} amount {amount}"
                        )
                    else:
                        self.stdout.write(
                            f"[DRY RUN] CREATE payment for invoice #{invoice_number} "
                            f"on {payment_date} amount {amount} ({method_value})"
                        )
                    continue

                payment, created = InvoicePayment.objects.get_or_create(
                    defaults=payment_kwargs,
                    **lookup,
                )

                if created:
                    created_payments += 1
                    invoices_touched.add(invoice.pk)
                    self.stdout.write(
                        f"[CREATE] Payment for invoice #{invoice_number} on {payment_date} "
                        f"amount {amount} ({method_value})"
                    )
                else:
                    skipped_existing += 1
                    self.stdout.write(
                        f"[SKIP] Existing payment for invoice #{invoice_number} "
                        f"on {payment_date} amount {amount}"
                    )

        # After all payments, recompute invoice balances & status (non-dry-run only)
        if not dry_run and invoices_touched:
            self.stdout.write(self.style.NOTICE("Recomputing balances for touched invoices..."))
            for invoice_id in invoices_touched:
                try:
                    inv = Invoice.objects.get(pk=invoice_id)
                except Invoice.DoesNotExist:
                    continue
                recompute_invoice_payment_state(inv)

        mode = "DRY RUN" if dry_run else "COMMIT"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] Payment import complete. "
                f"Created {created_payments} payment(s), skipped {skipped_existing} existing."
            )
        )
