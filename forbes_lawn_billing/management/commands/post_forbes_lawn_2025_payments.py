# lawn_imports/management/commands/post_forbes_lawn_2025_payments.py

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from django_ledger.models.entity import EntityModel

from forbes_lawn_billing.models import InvoicePayment
from forbes_lawn_billing.ledger_posting import post_payment_to_ledger


class Command(BaseCommand):
    help = "Post Forbes Lawn 2025 Jobber payments into Django Ledger."

    def add_arguments(self, parser):
        parser.add_argument(
            "--entity-slug",
            type=str,
            required=True,
            help="Slug of the Django Ledger Entity (e.g. forbes-lawn-spraying-llc-elg3zg1u)",
        )
        parser.add_argument(
            "--ledger-xid",
            type=str,
            required=True,
            help="Target ledger XID to post payments into "
                 "(e.g. Invoices-I-posting invoice and payments)",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=2025,
            help="Year of payments to post (defaults to 2025).",
        )

    def handle(self, *args, **options):
        entity_slug = options["entity_slug"]
        ledger_xid = options["ledger_xid"]
        year = options["year"]

        try:
            entity = EntityModel.objects.get(slug=entity_slug)
        except EntityModel.DoesNotExist:
            raise CommandError(f"Entity with slug '{entity_slug}' not found.")

        qs = InvoicePayment.objects.filter(
            invoice__entity=entity,
            payment_date__year=year,
        ).order_by("payment_date", "id")

        # If you have a posted flag, filter it out here:
        if hasattr(InvoicePayment, "posted_to_ledger"):
            qs = qs.filter(posted_to_ledger=False)

        count = qs.count()
        if count == 0:
            self.stdout.write(
                self.style.WARNING(
                    f"No payments found for entity={entity_slug}, year={year}."
                )
            )
            return

        self.stdout.write(
            self.style.NOTICE(
                f"Posting {count} payment(s) for entity={entity_slug}, "
                f"ledger_xid={ledger_xid}, year={year}"
            )
        )

        posted = 0
        for payment in qs:
            post_payment_to_ledger(
                payment=payment,
                entity=entity,
                ledger_xid=ledger_xid,
            )
            posted += 1
            self.stdout.write(
                f"  [POSTED] Payment {payment.id} "
                f"for invoice {payment.invoice.invoice_number} "
                f"amount={payment.amount} on {payment.payment_date}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Posted {posted} payment(s) into ledger '{ledger_xid}'."
            )
        )
