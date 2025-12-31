import re
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from django_ledger.models.entity import EntityModel
from django_ledger.models.customer import CustomerModel  # if this import fails, use apps.get_model

from forbes_lawn_billing.models import Invoice


def norm_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    # light normalization (optional)
    s = s.replace("&", "and")
    return s


class Command(BaseCommand):
    help = "Backfill Invoice.customer (DL CustomerModel) for Forbes Lawn invoices."

    def add_arguments(self, parser):
        parser.add_argument("--entity-slug", required=True, type=str)
        parser.add_argument("--year", default=2025, type=int)

        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--create-missing", action="store_true")

    def handle(self, *args, **opts):
        entity_slug = opts["entity_slug"]
        year = opts["year"]
        dry_run = opts["dry_run"]
        create_missing = opts["create_missing"]

        try:
            entity = EntityModel.objects.get(slug=entity_slug)
        except EntityModel.DoesNotExist:
            raise CommandError(f"Entity not found: {entity_slug}")

        qs = Invoice.objects.filter(entity=entity, invoice_date__year=year).order_by("invoice_date", "id")

        self.stdout.write(self.style.NOTICE(
            f"Backfill customers for {qs.count()} invoice(s) "
            f"entity={entity_slug} year={year} mode={'DRY RUN' if dry_run else 'COMMIT'}"
        ))

        updated = 0
        skipped_has_customer = 0
        skipped_no_match = 0
        created_customers = 0

        # preload customers for faster fallback matching
        customers = list(CustomerModel.objects.filter(entity_model=entity).only("uuid", "customer_name", "email"))
        by_norm_name = {norm_name(c.customer_name): c for c in customers if c.customer_name}

        for inv in qs.iterator(chunk_size=500):
            if inv.customer_id:
                skipped_has_customer += 1
                continue

            email = (inv.email_to or "").strip()
            name = (inv.customer_name or "").strip()

            customer = None

            # 1) email match (strong)
            if email:
                customer = CustomerModel.objects.filter(
                    entity_model=entity,
                    email__iexact=email,
                ).first()

            # 2) exact name match
            if customer is None and name:
                customer = CustomerModel.objects.filter(
                    entity_model=entity,
                    customer_name__iexact=name,
                ).first()

            # 3) normalized name fallback (fast, local dict)
            if customer is None and name:
                customer = by_norm_name.get(norm_name(name))

            # 4) create missing (optional)
            if customer is None and create_missing and name:
                if dry_run:
                    self.stdout.write(f"[DRY RUN] WOULD CREATE CustomerModel(name={name!r}, email={email!r})")
                    created_customers += 1
                    skipped_no_match += 1
                    continue

                customer = CustomerModel.objects.create(
                    entity_model=entity,
                    customer_name=name,
                    email=email or "",
                )
                created_customers += 1
                by_norm_name[norm_name(name)] = customer

            if customer is None:
                skipped_no_match += 1
                self.stdout.write(self.style.WARNING(
                    f"[NO MATCH] invoice #{inv.invoice_number} name={name!r} email={email!r}"
                ))
                continue

            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] LINK invoice #{inv.invoice_number} -> {customer.customer_name} ({customer.uuid})"
                )
                updated += 1
                continue

            # lock + update so reruns don't double-set in weird concurrency
            with transaction.atomic():
                inv_locked = Invoice.objects.select_for_update().get(pk=inv.pk)
                if inv_locked.customer_id:
                    skipped_has_customer += 1
                    continue

                inv_locked.customer = customer
                # keep snapshot aligned if blank
                if not inv_locked.customer_name:
                    inv_locked.customer_name = customer.customer_name

                inv_locked.save(update_fields=["customer", "customer_name"])
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. updated={updated}, skipped_has_customer={skipped_has_customer}, "
            f"skipped_no_match={skipped_no_match}, created_customers={created_customers}"
        ))
