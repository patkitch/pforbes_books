# forbes_lawn_billing/management/commands/post_forbes_lawn_2025_invoices.py

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from django_ledger.models import EntityModel, LedgerModel

from forbes_lawn_billing.models import Invoice, InvoiceStatus, InvoicePayment
from forbes_lawn_billing.ledger_posting import (
    post_open_invoice_to_ledger,
    post_invoice_payment_to_ledger,
)


class Command(BaseCommand):
    help = "Post Forbes Lawn 2025 invoices & payments into Django Ledger (beta/local)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--entity-slug",
            required=True,
            help="Entity slug for Forbes Lawn (e.g. 'forbes-lawn-llc').",
        )
        parser.add_argument(
            "--ledger-xid",
            required=True,
            help="LedgerExternalID (ledger_xid) for the AR ledger (e.g. 'forbes-lawn-2025-ar').",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=2025,
            help="Year to filter invoices & payments by invoice_date/payment_date.",
        )

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

        # 1) Post OPEN invoices that haven't been posted to AR yet
        invoices_qs = Invoice.objects.filter(
            entity=entity,
            invoice_date__year=year,
            status__in=[InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID],
            ar_journal_entry__isnull=True,
        )

        inv_count = 0
        for inv in invoices_qs:
            post_open_invoice_to_ledger(inv, ledger)
            inv_count += 1

        # 2) Post payments (invoice payments) that haven't been posted yet
        payments_qs = InvoicePayment.objects.filter(
            invoice__entity=entity,
            payment_date__year=year,
            payment_journal_entry__isnull=True,
        )

        pay_count = 0
        for pay in payments_qs:
            post_invoice_payment_to_ledger(pay, ledger)
            pay_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Posted {inv_count} invoice(s) and {pay_count} payment(s) into ledger '{ledger_xid}'."
        ))
