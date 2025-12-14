import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Sum

from django_ledger.models.entity import EntityModel
from forbes_lawn_billing.models import (
    Invoice,
    InvoicePayment,
    InvoiceStatus,
    PaymentMethod,
)


def map_jobber_payment_method(type_raw: str, paid_with_raw: str, paid_through_raw: str) -> str:
    """
    Map Jobber 'Type' / 'Paid with' / 'Paid through' text into our PaymentMethod enum.
    """
    t = (type_raw or "").lower()
    w = (paid_with_raw or "").lower()
    thru = (paid_through_raw or "").lower()

    # Most important signals first
    if "cash" in w or "cash" in t:
        return PaymentMethod.CASH

    if "check" in w or "cheque" in w or "check" in t:
        return PaymentMethod.CHECK

    if "credit" in w or "card" in w or "visa" in w or "mastercard" in w:
        return PaymentMethod.CARD

    if "bank" in w or "ach" in w or "bank payment" in t or "ach" in t:
        return PaymentMethod.ACH

    # Fallback
    return PaymentMethod.OTHER


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
                "%d-%b-%y",   # 3-Dec-25
                "%b %d, %Y",  # Dec 03, 2025 / Nov 19, 2025
                "%Y-%m-%d",   # 2025-12-03 (rare but possible)
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
                # --- BASIC FIELDS ---
                invoice_number = (row.get(COLUMN["invoice_number"]) or "").strip()
                if not invoice_number:
                    continue  # no invoice ref, nothing to attach

                client_name = (row.get(COLUMN["client_name"]) or "").strip()
                date_raw = row.get(COLUMN["date"]) or ""
                payment_date = parse_date(date_raw)
                if payment_date is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping row for invoice #{invoice_number}: "
                            f"could not parse date '{date_raw}'"
                        )
                    )
                    continue

                type_raw = (row.get(COLUMN["type"]) or "").strip()
                paid_with_raw = (row.get(COLUMN["paid_with"]) or "").strip()
                paid_through_raw = (row.get(COLUMN["paid_through"]) or "").strip()

                total_raw = row.get(COLUMN["total"]) or "0"
                raw_amount = parse_decimal(total_raw)
                amount = abs(raw_amount)  # Jobber exports negative for received money

                note = (row.get(COLUMN["note"]) or "").strip()
                card_last4 = (row.get(COLUMN["card_last4"]) or "").strip()
                card_type = (row.get(COLUMN["card_type"]) or "").strip()
                payout_id = (row.get(COLUMN["payout_id"]) or "").strip()

                # Determine payment method
                payment_method = map_jobber_payment_method(
                    type_raw,
                    paid_with_raw,
                    paid_through_raw,
                )

                # Lookup invoice by entity + invoice_number (which matches Jobber's Invoice #)
                invoice = (
                    Invoice.objects.filter(entity=entity, invoice_number=invoice_number)
                    .order_by("-invoice_date")
                    .first()
                )
                if invoice is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Invoice #{invoice_number} not found for payment row "
                            f"(client={client_name}, amount={amount})."
                        )
                    )
                    continue

                # Build a dedupe fingerprint: invoice + date + amount
                lookup = {
                    "invoice": invoice,
                    "payment_date": payment_date,
                    "amount": amount,
                }

                method_value = f"{paid_with_raw} via {paid_through_raw}".strip()

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
                            f"on {payment_date} amount {amount} "
                            f"method={payment_method} ({method_value})"
                        )
                    continue

                # --- CREATE / UPDATE PAYMENT ---
                payment, created = InvoicePayment.objects.get_or_create(
                    **lookup,
                    defaults={
                        "payment_method": payment_method,
                        "jobber_type": type_raw,
                        "jobber_paid_with": paid_with_raw,
                        "jobber_paid_through": paid_through_raw,
                        "jobber_payment_id": payout_id,
                        "reference": " | ".join([p for p in [
                            note,
                            (f"{card_type} {card_last4}".strip() if (card_type or card_last4) else ""),
                            (f"Payout {payout_id}".strip() if payout_id else ""),
                        ] if p]),
                    },
                    
                )

                if not created:
                    # Update method & raw fields in case they changed or were defaulted to CASH before
                    payment.payment_method = payment_method
                    payment.jobber_type = type_raw
                    payment.jobber_paid_with = paid_with_raw
                    payment.jobber_paid_through = paid_through_raw
                    #payment.note = note#
                    payment.jobber_payment_id = payout_id
                    payment.reference = " | ".join([p for p in [
                        note,
                        (f"{card_type} {card_last4}".strip() if (card_type or card_last4) else ""),
                        (f"Payout {payout_id}".strip() if payout_id else ""),
                    ] if p])
                    payment.save()

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
