"""Idempotent WooCommerce order-to-customer and sales-receipt preparation.

This receives already-fetched WooCommerce order dictionaries. It makes no
network requests and deliberately DOES NOT create or post accounting entries.
The actual import inbox/approval process will use it in the later import phase.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Customer, Receipt


def receipt_snapshot(order):
    # Explicit allowlist: do not copy IP addresses or unrelated order metadata.
    fields = ('id', 'date_created', 'date_paid', 'date_paid_gmt', 'currency',
              'total', 'total_tax', 'shipping_total', 'discount_total',
              'payment_method_title', 'payment_method', 'transaction_id',
              'billing', 'shipping', 'line_items', 'shipping_lines', 'fee_lines',
              'coupon_lines', 'customer_note')
    result = {key: order[key] for key in fields if key in order}
    result['meta_data'] = [m for m in (order.get('meta_data') or [])
                           if isinstance(m, dict) and m.get('key') in
                           ('_stripe_fee', '_stripe_net', 'Stripe Fee', 'Stripe Payout')]
    return result


def _name(billing, order_id):
    first = str(billing.get("first_name") or "").strip()
    last = str(billing.get("last_name") or "").strip()
    company = str(billing.get("company") or "").strip()
    return company or " ".join(p for p in (first, last) if p) or f"WooCommerce customer (order {order_id})"


@transaction.atomic
def stage_woo_order_receipt(order):
    """Create/match customer and order receipt; never make a journal entry.

    Registered customers are matched by WooCommerce customer ID. Guests are
    matched by a unique case-insensitive billing email when available.
    """
    try:
        order_id = int(order["id"])
        customer_id = int(order.get("customer_id") or 0)
        amount = Decimal(str(order["total"]))
        date_string = str(order["date_created"])
        order_date = datetime.fromisoformat(date_string.replace("Z", "+00:00")).date()
    except (KeyError, ValueError, TypeError, InvalidOperation, OverflowError) as exc:
        raise ValidationError("WooCommerce order has missing or invalid ID, date, or amount.") from exc
    if order_id <= 0 or customer_id < 0 or not amount.is_finite() or amount < 0:
        raise ValidationError("WooCommerce order ID, customer ID, or amount is invalid.")
    billing = order.get("billing") or {}
    shipping = order.get("shipping") or {}
    if not isinstance(billing, dict) or not isinstance(shipping, dict):
        raise ValidationError("WooCommerce billing and shipping details must be objects.")
    reference = f"order:{order_id}"
    existing = Receipt.objects.select_for_update().filter(
        source="woocommerce", source_reference=reference
    ).first()
    if existing:
        # Do not overwrite historical receipt or relink a previously reviewed customer.
        return existing.customer, existing, False

    values = {
        "name": _name(billing, order_id)[:200],
        "email": str(billing.get("email") or "")[:254],
        "phone": str(billing.get("phone") or "")[:40],
        "billing_address1": str(billing.get("address_1") or "")[:200],
        "billing_address2": str(billing.get("address_2") or "")[:200],
        "billing_city": str(billing.get("city") or "")[:100],
        "billing_state": str(billing.get("state") or "")[:100],
        "billing_postal_code": str(billing.get("postcode") or "")[:24],
        "billing_country": str(billing.get("country") or "")[:80],
        "shipping_address1": str(shipping.get("address_1") or "")[:200],
        "shipping_address2": str(shipping.get("address_2") or "")[:200],
        "shipping_city": str(shipping.get("city") or "")[:100],
        "shipping_state": str(shipping.get("state") or "")[:100],
        "shipping_postal_code": str(shipping.get("postcode") or "")[:24],
        "shipping_country": str(shipping.get("country") or "")[:80],
    }
    if customer_id:
        customer, _ = Customer.objects.get_or_create(
            woo_customer_id=customer_id, defaults=values
        )
    else:
        email = values["email"].strip()
        matches = list(Customer.objects.select_for_update().filter(email__iexact=email)[:2]) if email else []
        if len(matches) > 1 or (matches and not matches[0].is_active):
            raise ValidationError("Customer email has ambiguous or inactive matches. Review the customer directory before creating this receipt.")
        customer = matches[0] if matches else Customer.objects.create(**values)
    receipt = Receipt(
        title=f"WooCommerce order #{order_id}",
        receipt_type="sale", date=order_date, amount=amount,
        customer=customer, source="woocommerce", source_reference=reference,
        notes="Imported order metadata only; no journal entry has been posted.",
        woo_snapshot=receipt_snapshot(order),
    )
    receipt.full_clean()
    receipt.save()
    return customer, receipt, True
