from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import csv
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from django_ledger.models import (
    ENTITY_RANDOM_SLUG_SUFFIX,
    EntityModel,
    CustomerModel,
    InvoiceModel,
    ItemModel,
)

# Slug of your Forbes Lawn Spraying entity in Django Ledger
ENTITY_SLUG_LAWN = "forbes-lawn-spraying-llc-vtcqxrcl"


# ------------------------
# Parsing helpers
# ------------------------

def parse_decimal(value: str, field_name: str = "") -> Decimal:
    """
    Safely parse numeric strings into Decimal.
    On bad input, logs a warning and returns Decimal('0').
    """
    if value is None:
        return Decimal("0")

    raw = value
    value = value.strip()

    if value in ("", "-", "—"):
        return Decimal("0")

    # Remove currency symbols / commas
    value = value.replace("$", "").replace(",", "")

    try:
        return Decimal(value)
    except InvalidOperation:
        print(f"[WARN] Could not parse decimal for field '{field_name}': {raw!r}. Using 0.")
        return Decimal("0")


def parse_date(value: str):
    """
    Jobber date format example: 'Nov 19, 2025'.
    Empty or '-' becomes None.
    """
    if not value or value.strip() in ("", "-"):
        return None
    return datetime.strptime(value.strip(), "%b %d, %Y").date()


def parse_line_items(line_items_str: str):
    """
    Example in CSV: '2025 Lawn Treatments (1, $64)'
    Returns a list of dicts with name, quantity, rate.
    """
    if not line_items_str:
        return []

    text = line_items_str.strip()
    if "(" in text and ")" in text:
        name_part, meta_part = text.split("(", 1)
        name = name_part.strip()
        meta_part = meta_part.rstrip(")")
        parts = [p.strip() for p in meta_part.split(",")]
        qty = Decimal("1")
        rate = Decimal("0")
        if len(parts) >= 1:
            try:
                qty = Decimal(parts[0])
            except Exception:
                pass
        if len(parts) >= 2:
            rate = parse_decimal(parts[1], "Line items rate")
        return [{
            "name": name,
            "quantity": qty,
            "rate": rate,
        }]
    else:
        # Fallback: treat entire string as a single item with qty=1
        return [{
            "name": text,
            "quantity": Decimal("1"),
            "rate": Decimal("0"),
        }]


def parse_tax_bundle(raw_tax_str: str):
    """
    Example raw string from CSV:
        'KS-Johnson-Prairie Village (8.975%)'

    Returns (bundle_name, combined_rate_decimal) like:
        ('KS-Johnson-Prairie Village', Decimal('0.08975'))
    """
    if not raw_tax_str:
        return None, Decimal("0")

    text = raw_tax_str.strip()
    if "(" in text and ")" in text:
        name_part, rate_part = text.split("(", 1)
        bundle_name = name_part.strip()
        rate_part = rate_part.rstrip(")")
        rate_part = rate_part.replace("%", "").strip()
        try:
            combined_rate = Decimal(rate_part) / Decimal("100")
        except Exception:
            combined_rate = Decimal("0")
        return bundle_name, combined_rate

    return text, Decimal("0")


def split_tax(pre_tax_total: Decimal, tax_amount: Decimal, bundle_name: str, combined_rate: Decimal):
    """
    Split tax into KS / Johnson County / City for Johnson County bundles.

    - Kansas: 6.5%
    - Johnson County: 1.475%
    - City: combined_rate - (6.5% + 1.475%)

    For non-Johnson bundles (or missing data), we return a single combined line.
    """
    if not bundle_name:
        return [("Unknown", tax_amount)]

    bundle_name = bundle_name.strip()

    if bundle_name.startswith("KS-Johnson-") and combined_rate > 0:
        state_label = "Kansas"
        county_label = "Johnson County"
        parts = bundle_name.split("-", 2)
        city_label = parts[2] if len(parts) == 3 else "City"

        state_rate = Decimal("0.065")    # 6.5%
        county_rate = Decimal("0.01475") # 1.475%
        city_rate = combined_rate - (state_rate + county_rate)

        if city_rate < 0:
            return [(bundle_name, tax_amount)]

        state_raw = pre_tax_total * state_rate
        county_raw = pre_tax_total * county_rate
        city_raw = pre_tax_total * city_rate

        def q(x: Decimal) -> Decimal:
            return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        state_tax = q(state_raw)
        county_tax = q(county_raw)
        city_tax = q(city_raw)

        # Fix rounding so parts == Jobber tax_amount
        sum_tax = state_tax + county_tax + city_tax
        diff = tax_amount - sum_tax
        city_tax += diff

        return [
            (f"{state_label} (6.5%)", state_tax),
            (f"{county_label} (1.475%)", county_tax),
            (f"{city_label}", city_tax),
        ]

    # Default: single combined line
    return [(bundle_name, tax_amount)]


# ------------------------
# Django Ledger helpers
# ------------------------




def get_or_create_lawn_customer(row, entity: EntityModel) -> CustomerModel:
    """
    Ensure we have a Django Ledger CustomerModel for this Jobber client,
    attached to the Forbes Lawn Spraying entity.
    """
    name = (row.get("Client name") or "").strip()
    email = (row.get("Client email") or "").strip()
    phone = (row.get("Client phone") or "").strip()

    if not name:
        raise CommandError("Row missing 'Client name' – cannot create customer.")

    # Try to find an existing customer by name on this entity.
    customer_qs = CustomerModel.objects.filter(
        entity_model=entity,
        customer_name=name,
    )

    if customer_qs.exists():
        customer = customer_qs.first()
        changed = False

        if email and customer.email != email:
            customer.email = email
            changed = True
        if phone and customer.phone != phone:
            customer.phone = phone
            changed = True

        if changed:
            customer.save()
            print(
                f"    [CUSTOMER] Updated contact info for existing customer '{customer.customer_name}'."
            )
        else:
            print(
                f"    [CUSTOMER] Reused existing customer '{customer.customer_name}'."
            )

        return customer

    # No existing customer – create a new one via the Entity API.
    billing_city = (row.get("Billing city") or "").strip()
    billing_state = (row.get("Billing province") or "").strip()
    description_parts = []
    billing_city = (row.get("Billing city") or "").strip()
    billing_state = (row.get("Billing province") or "").strip()
    if billing_city or billing_state:
        description_parts.append(
            f"Lawn spraying customer in {billing_city}, {billing_state}".strip(", ")
        )
    description = " ".join(description_parts) or "Forbes Lawn Spraying customer"

    customer_kwargs = {
        "customer_name": name,
        "description": description,
        "email": email,
        "phone": phone,
    }

    customer: CustomerModel = entity.create_customer(customer_model_kwargs=customer_kwargs)

    print(
        f"    [CUSTOMER] Created new customer '{customer.customer_name}' "
        f"for entity '{entity.name}'."
    )
    return customer



def get_or_create_service_item(entity: EntityModel, uom_unit, service_name: str):
    """
    Ensure there's a Service Item for the given name.
    """
    name = (service_name or "").strip() or "Lawn Treatment"

    services_qs = entity.get_items_services().filter(name=name)
    if services_qs.exists():
        return services_qs.first(), False

    service_model: ItemModel = entity.create_item_service(
        name=name,
        uom_model=uom_unit,
    )
    return service_model, True


# ------------------------
# Management Command
# ------------------------

class Command(BaseCommand):
    help = (
        "Import Jobber invoice CSV for Forbes Lawn Spraying. "
        "Default is DRY RUN (log only). Use --commit to create "
        "Customers, Service Items, and Invoices in Django Ledger."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            type=str,
            help="Path to the Jobber invoice CSV export.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually create customers/items/invoices in Django Ledger.",
        )
        parser.add_argument(
            "--only-invoice",
            type=str,
            help="Optional: only process a single invoice number (e.g. '749') for testing.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        commit = options["commit"]
        only_invoice = options.get("only_invoice")

        mode = "COMMIT" if commit else "DRY RUN"
        self.stdout.write(self.style.WARNING(
            f"[{mode}] Starting lawn invoice import from {csv_path}"
        ))

        # Get Forbes Lawn Spraying entity
        try:
            entity: EntityModel = EntityModel.objects.get(slug=ENTITY_SLUG_LAWN)
        except EntityModel.DoesNotExist:
            raise CommandError(
                f"Entity with slug '{ENTITY_SLUG_LAWN}' not found. "
                f"Check Django Ledger admin → Entities."
            )

        # Get default "unit" UOM for services
        uom_qs = entity.get_uom_all()
        try:
            uom_unit = uom_qs.get(unit_abbr__exact="unit")
        except Exception:
            raise CommandError(
                "Could not find UOM with unit_abbr='unit'. "
                "Create one in Django Ledger (Unit of Measures)."
            )

        count_rows = 0
        created_customers = 0
        reused_customers = 0
        created_items = 0
        created_invoices = 0

        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    invoice_no = (row.get("Invoice #") or "").strip()
                    if not invoice_no:
                        continue

                    if only_invoice and invoice_no != only_invoice:
                        continue

                    client_name = (row.get("Client name") or "").strip()
                    status = (row.get("Status") or "").strip()

                    issued_date = parse_date(row.get("Issued date", ""))
                    due_date = parse_date(row.get("Due date", ""))
                    marked_paid_date = parse_date(row.get("Marked paid date", ""))

                    pre_tax = parse_decimal(row.get("Pre-tax total ($)", "0"), "Pre-tax total ($)")
                    total = parse_decimal(row.get("Total ($)", "0"), "Total ($)")
                    balance = parse_decimal(row.get("Balance ($)", "0"), "Balance ($)")
                    tax_amount = parse_decimal(row.get("Tax amount ($)", "0"), "Tax amount ($)")

                    line_items_str = row.get("Line items", "")
                    line_items = parse_line_items(line_items_str)

                    tax_str = row.get("Tax (%)", "")
                    bundle_name, combined_rate = parse_tax_bundle(tax_str)
                    tax_splits = split_tax(pre_tax, tax_amount, bundle_name, combined_rate)

                    payment_amount = total - balance

                    # --- Logging ---
                    self.stdout.write(
                        self.style.MIGRATE_HEADING(
                            f"\nInvoice #{invoice_no} | Client: {client_name}"
                        )
                    )
                    self.stdout.write(
                        f"  Status: {status} | Issued: {issued_date} | Due: {due_date} | Paid date: {marked_paid_date}"
                    )
                    self.stdout.write(
                        f"  Pre-tax: {pre_tax} | Tax: {tax_amount} | Total: {total} | "
                        f"Balance: {balance} | Payment (derived): {payment_amount}"
                    )

                    if line_items:
                        self.stdout.write("  Line items:")
                        for li in line_items:
                            self.stdout.write(
                                f"    - {li['name']} | qty={li['quantity']} | rate={li['rate']}"
                            )
                    else:
                        self.stdout.write("  Line items: [none parsed]")

                    self.stdout.write(
                        f"  Tax bundle raw: '{tax_str}' → name='{bundle_name}', combined_rate={combined_rate * 100}%"
                    )
                    self.stdout.write("  Tax breakdown (amounts):")
                    for label, amt in tax_splits:
                        self.stdout.write(f"    - {label}: {amt}")

                    lawn_sqft = (row.get("Lawn square footage") or "").strip()
                    products_today = (row.get("Products applied Today") or "").strip()
                    area_treated = (row.get("Area treated") or "").strip()
                    target_pest = (row.get("Target Pest") or "").strip()

                    if lawn_sqft or products_today or area_treated or target_pest:
                        self.stdout.write("  Lawn / Treatment details:")
                        if lawn_sqft:
                            self.stdout.write(f"    - Lawn square footage: {lawn_sqft}")
                        if products_today:
                            self.stdout.write(f"    - Products applied Today: {products_today}")
                        if area_treated:
                            self.stdout.write(f"    - Area treated: {area_treated}")
                        if target_pest:
                            self.stdout.write(f"    - Target Pest: {target_pest}")

                    # --- COMMIT MODE: create customer, item, invoice ---
                self.stdout.write(self.style.SUCCESS(
                    f"\n[DRY RUN COMPLETE] Processed {count_rows} invoice row(s)."
                    f" MODE = {'COMMIT' if commit else 'DRY RUN'}."
                ))

                if commit:
                    # IMPORTANT:
                    # We just looped over all rows; 'row' now holds the *last* processed row.
                    # For COMMIT runs you’ll typically either:
                    #   - use --only-invoice to do one at a time, or
                    #   - later refactor the commit logic into the per-row loop.
                    #
                    # For now we support committing a *single* invoice via --only-invoice.
                    if not only_invoice:
                        raise CommandError(
                            "For COMMIT mode, use --only-invoice=<number> so we only create one invoice at a time."
                        )

                    # Re-open the CSV and locate just that one invoice row so we can commit it.
                    with open(csv_path, newline="", encoding="utf-8-sig") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            invoice_no = (row.get("Invoice #") or "").strip()
                            if not invoice_no:
                                continue
                            if invoice_no != only_invoice:
                                continue

                            # ---- Re-parse key fields for this one invoice ----
                            client_name = (row.get("Client name") or "").strip()
                            status = (row.get("Status") or "").strip()

                            issued_date = parse_date(row.get("Issued date", ""))
                            due_date = parse_date(row.get("Due date", ""))
                            marked_paid_date = parse_date(row.get("Marked paid date", ""))

                            pre_tax = parse_decimal(row.get("Pre-tax total ($)", "0"), "Pre-tax total ($)")
                            total = parse_decimal(row.get("Total ($)", "0"), "Total ($)")
                            balance = parse_decimal(row.get("Balance ($)", "0"), "Balance ($)")
                            tax_amount = parse_decimal(row.get("Tax amount ($)", "0"), "Tax amount ($)")

                            line_items_str = row.get("Line items", "")
                            line_items = parse_line_items(line_items_str)

                            tax_str = row.get("Tax (%)", "")
                            bundle_name, combined_rate = parse_tax_bundle(tax_str)
                            tax_splits = split_tax(pre_tax, tax_amount, bundle_name, combined_rate)

                            payment_amount = total - balance

                            # 1) Ensure customer exists (or is reused) for this entity
                            customer = get_or_create_lawn_customer(row, entity)

                            # 2) Ensure service ItemModel exists for the line item
                            #    (For now we assume a single line item per invoice.)
                            if line_items:
                                li = line_items[0]
                                item_name = li["name"]

                                service_item, created_item = ItemModel.objects.get_or_create(
                                    entity=entity,
                                    name=item_name,
                                    defaults={
                                    # Keep it simple: let Django Ledger use its own defaults
                                    # for role/type; we just tell it this is a sellable service.
                                    "default_amount": li["rate"],
                                    "sold_as_unit": True,
                                    "is_product_or_service": True,
                                    },
                                )

                                if created_item:
                                    self.stdout.write(
                                        self.style.SUCCESS(
                                            f"  [ITEM] Created service item '{service_item.name}'."
                                        )
                                    )
                                else:
                                    self.stdout.write(
                                        f"  [ITEM] Reused existing service item '{service_item.name}'."
                                    )

                            else:
                                raise CommandError(
                                    f"Invoice #{invoice_no} has no parsed line items; cannot create invoice."
                                )

                            # 3) Create the Invoice via Entity API.
                            #    Django Ledger’s EntityModelAbstract.create_invoice(...)
                            #    expects 'terms' as a first argument and then keyword args.
                            #
                            # We’ll keep terms as a simple string the system understands,
                            # e.g. 'DUE_ON_RECEIPT'. If your UI uses different labels, you can
                            # later change this to match.
                            #
                            # NOTE: we’re not auto-posting; invoice will start as a draft.
                            invoice: InvoiceModel = entity.create_invoice(
                                customer_model=customer,
                                terms="on_receipt",
                                date_draft=issued_date,
                                additional_info={
                                    "source": "jobber_csv",
                                    "jobber_invoice_no": invoice_no,
                                    "jobber_status": status,
                                    "jobber_due_date": str(due_date) if due_date else None,
                                    "jobber_marked_paid_date": str(marked_paid_date) if marked_paid_date else None,
                                    "jobber_pre_tax_total": str(pre_tax),
                                    "jobber_tax_amount": str(tax_amount),
                                    "jobber_total": str(total),
                                    "jobber_balance": str(balance),
                                    "jobber_payment_derived": str(payment_amount),
                                 },
                                commit=True,
                            )

                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  [INVOICE] Created Django Ledger invoice #{invoice.get_invoice_number()} "
                                    f"for {client_name} (Jobber #{invoice_no})."
                                )
                            )
                            

                            # 3a) Add invoice line items from Jobber
                            # For now we assume one line item per invoice (your parse_line_items already does that).
                            li = line_items[0]

                            # Build the itemtxs dict Django Ledger expects:
                            invoice_itemtxs = {
                                service_item.item_number: {
                                    # Django Ledger examples use 'unit_cost' for invoices.
                                    # We'll treat the Jobber rate as the unit price here.
                                    "unit_cost": float(li["rate"]),
                                    "quantity": float(li["quantity"]),
                                    "total_amount": None,  # let Django Ledger compute quantity * unit_cost
                                }
                            }

                            invoice.migrate_itemtxs(
                                itemtxs=invoice_itemtxs,
                                commit=True,
                                operation=InvoiceModel.ITEMIZE_REPLACE,
                            )

                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  [INVOICE ITEMS] Added {li['quantity']} x {li['name']} @ {li['rate']} "
                                    f"to invoice #{invoice.invoice_number}."
                            )
)


                            # 4) (Optional next step) create a Receipt/Payment tying to bank,
                            #    but we’ll do that in a later phase.
                            created_invoices += 1
                            break  # stop after the one invoice

                    self.stdout.write(self.style.SUCCESS(
                        f"[COMMIT SUMMARY] Invoices created: {created_invoices}."
                    ))


                    count_rows += 1

        except FileNotFoundError:
            raise CommandError(f"File not found: {csv_path}")
        except Exception as e:
            raise CommandError(str(e))

        # --- Summary ---
        if not commit:
            self.stdout.write(self.style.SUCCESS(
                f"\n[DRY RUN COMPLETE] Processed {count_rows} invoice row(s). "
                f"No database changes were made."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n[COMMIT COMPLETE] Processed {count_rows} invoice row(s). "
                f"Customers created: {created_customers}, reused: {reused_customers}. "
                f"Service items created: {created_items}. "
                f"Invoices created: {created_invoices}."
            ))
