import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum, Case, When, Value, DecimalField, F
from django_ledger.models.entity import EntityModel

from forbes_lawn_billing.models import Invoice, InvoiceLine, InvoicePayment


class Command(BaseCommand):
    help = "Export Forbes Lawn reports (Payments to Deposit + Revenue taxable/non-taxable) to CSV."

    def add_arguments(self, parser):
        parser.add_argument("--entity-slug", required=True, type=str)
        parser.add_argument("--year", default=2025, type=int)
        parser.add_argument("--out-dir", default="/tmp", type=str)

    def handle(self, *args, **opts):
        entity_slug = opts["entity_slug"]
        year = opts["year"]
        out_dir = Path(opts["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            entity = EntityModel.objects.get(slug=entity_slug)
        except EntityModel.DoesNotExist:
            raise CommandError(f"Entity not found: {entity_slug}")

        # ----------------------------
        # 1) Payments to Deposit detail
        # ----------------------------
        payments_path = out_dir / f"payments_to_deposit_{year}.csv"

        pay_qs = (
            InvoicePayment.objects
            .filter(invoice__entity=entity, payment_date__year=year)
            .select_related("invoice", "invoice__customer", "payment_journal_entry")
            .order_by("payment_date", "id")
        )

        with payments_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "payment_id",
                "payment_date",
                "customer_name",
                "customer_uuid",
                "invoice_number",
                "amount",
                "payment_method",
                "posted_to_ledger",
                "payment_je_number",
            ])

            for p in pay_qs:
                cust = getattr(p.invoice, "customer", None)
                w.writerow([
                    p.id,
                    p.payment_date,
                    (cust.customer_name if cust else p.invoice.customer_name),
                    (str(cust.uuid) if cust else ""),
                    p.invoice.invoice_number,
                    f"{p.amount:.2f}",
                    p.payment_method,
                    bool(p.payment_journal_entry_id),
                    (p.payment_journal_entry.je_number if p.payment_journal_entry_id else ""),
                ])

        # ---------------------------------------
        # 2) Revenue taxable vs non-taxable detail
        # ---------------------------------------
        revenue_path = out_dir / f"revenue_taxable_split_{year}.csv"

        # Line-level aggregation per invoice
        # taxable_revenue = sum(line_amount where taxable=True)
        # nontaxable_revenue = sum(line_amount where taxable=False)
        line_sums = (
            InvoiceLine.objects
            .filter(invoice__entity=entity, invoice__invoice_date__year=year)
            .values("invoice_id")
            .annotate(
                taxable_revenue=Sum(
                    Case(
                        When(taxable=True, then=F("line_amount")),
                        default=Value(Decimal("0.00")),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                ),
                nontaxable_revenue=Sum(
                    Case(
                        When(taxable=False, then=F("line_amount")),
                        default=Value(Decimal("0.00")),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                ),
            )
        )

        sums_by_invoice = {row["invoice_id"]: row for row in line_sums}

        inv_qs = (
            Invoice.objects
            .filter(entity=entity, invoice_date__year=year)
            .select_related("customer")
            .order_by("invoice_date", "invoice_number", "id")
        )

        with revenue_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "invoice_id",
                "invoice_number",
                "invoice_date",
                "customer_name",
                "customer_uuid",
                "taxable_revenue",
                "nontaxable_revenue",
                "tax_amount",
                "discount_amount",
                "total",
                "ar_je_number",
            ])

            for inv in inv_qs:
                s = sums_by_invoice.get(inv.id, {})
                taxable_rev = (s.get("taxable_revenue") or Decimal("0.00"))
                nontaxable_rev = (s.get("nontaxable_revenue") or Decimal("0.00"))

                cust = inv.customer
                w.writerow([
                    inv.id,
                    inv.invoice_number,
                    inv.invoice_date,
                    (cust.customer_name if cust else inv.customer_name),
                    (str(cust.uuid) if cust else ""),
                    f"{taxable_rev:.2f}",
                    f"{nontaxable_rev:.2f}",
                    f"{(inv.tax_amount or Decimal('0.00')):.2f}",
                    f"{(inv.discount_amount or Decimal('0.00')):.2f}",
                    f"{(inv.total or Decimal('0.00')):.2f}",
                    (inv.ar_journal_entry.je_number if inv.ar_journal_entry_id else ""),
                ])

        self.stdout.write(self.style.SUCCESS(f"Wrote: {payments_path}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote: {revenue_path}"))
