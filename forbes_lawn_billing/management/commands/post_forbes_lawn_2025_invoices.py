# forbes_lawn_billing/management/commands/post_forbes_lawn_2025_invoices.py

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from django_ledger.models import EntityModel, LedgerModel

from forbes_lawn_billing.models import Invoice, InvoiceStatus, InvoicePayment
from forbes_lawn_billing.ledger_posting import (
    post_open_invoice_to_ledger,
    post_invoice_payment_to_ledger,
)


class Command(BaseCommand):
    help = "Post Forbes Lawn invoices & payments into Django Ledger (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--entity-slug", required=True)
        parser.add_argument("--ledger-xid", required=True)
        parser.add_argument("--year", type=int, default=2025)

    def handle(self, *args, **options):
        entity_slug = options["entity_slug"]
        ledger_xid = options["ledger_xid"]
        year = options["year"]

        try:
            entity = EntityModel.objects.get(slug=entity_slug)
        except EntityModel.DoesNotExist:
            raise CommandError(f"Entity with slug '{entity_slug}' not found.")

        try:
            ledger = LedgerModel.objects.for_entity(entity).get(ledger_xid=ledger_xid)
        except LedgerModel.DoesNotExist:
            raise CommandError(
                f"Ledger with ledger_xid='{ledger_xid}' for entity '{entity_slug}' not found."
            )

        self.stdout.write(self.style.NOTICE(
            f"Posting invoices & payments for entity={entity_slug}, ledger_xid={ledger_xid}, year={year}"
        ))

        # -------------------------
        # 1) INVOICES (only ones not yet linked to a JE)
        # -------------------------
        invoices_qs = (
            Invoice.objects
            .filter(
                entity=entity,
                invoice_date__year=year,
                status__in=[InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID],
                ar_journal_entry__isnull=True,
            )
            .order_by("invoice_date", "id")
        )

        inv_posted = 0
        inv_skipped = 0
        inv_errors = 0

        for inv in invoices_qs:
            try:
                with transaction.atomic():
                    inv_locked = (
                        Invoice.objects
                        .select_for_update()
                        .get(pk=inv.pk)
                    )

                    # Re-check under lock
                    if inv_locked.ar_journal_entry_id is not None:
                        inv_skipped += 1
                        continue

                    je = post_open_invoice_to_ledger(inv_locked, ledger)

                    # post_open_invoice_to_ledger already sets inv_locked.ar_journal_entry.
                    # But if it returned None (nothing to post), treat as skipped.
                    if je is None:
                        inv_skipped += 1
                        continue

                    inv_posted += 1

            except Exception as e:
                inv_errors += 1
                self.stdout.write(self.style.ERROR(
                    f"[INVOICE ERROR] Invoice #{inv.invoice_number} failed: {e}"
                ))

        # -------------------------
        # 2) PAYMENTS (only ones not yet linked to a JE)
        # -------------------------
        payments_qs = (
            InvoicePayment.objects
            .filter(
                invoice__entity=entity,
                payment_date__year=year,
                payment_journal_entry__isnull=True,
            )
            .select_related("invoice")
            .order_by("payment_date", "id")
        )

        pay_posted = 0
        pay_skipped = 0
        pay_errors = 0

        for pay in payments_qs:
            try:
                with transaction.atomic():
                    pay_locked = (
                        InvoicePayment.objects
                        .select_for_update()
                        .select_related("invoice")
                        .get(pk=pay.pk)
                    )

                    # Re-check under lock
                    if pay_locked.payment_journal_entry_id is not None:
                        pay_skipped += 1
                        continue

                    je = post_invoice_payment_to_ledger(pay_locked, ledger)

                    # post_invoice_payment_to_ledger always returns a JE and sets payment_journal_entry.
                    if je is None:
                        # ultra-defensive: shouldn't happen
                        pay_skipped += 1
                        continue

                    pay_posted += 1

            except Exception as e:
                pay_errors += 1
                self.stdout.write(self.style.ERROR(
                    f"[PAYMENT ERROR] Payment id={pay.pk} (invoice #{pay.invoice.invoice_number}) failed: {e}"
                ))

        self.stdout.write(self.style.SUCCESS(
            f"Done. Invoices: posted={inv_posted}, skipped={inv_skipped}, errors={inv_errors}. "
            f"Payments: posted={pay_posted}, skipped={pay_skipped}, errors={pay_errors}. "
            f"Ledger='{ledger_xid}'."
        ))
