"""Review-only WooCommerce order staging, independent from payment settlement.

Accepts supplied order data. No network calls, secrets, or journal posting.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import WooOrderImport

PAID_STATUSES = {"processing", "completed"}
MAX_ORDERS = 200


def _money(raw, field):
    try:
        value = Decimal(str(raw))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValidationError(f"Invalid {field} amount.") from exc
    if not value.is_finite() or value < 0 or value.as_tuple().exponent < -2:
        raise ValidationError(f"Invalid {field} amount.")
    return value


def normalize_order(order):
    if not isinstance(order, dict):
        raise ValidationError("Each WooCommerce order must be a JSON object.")
    try:
        order_id = int(order["id"])
        date_text = str(order["date_created"])
        created_date = datetime.fromisoformat(date_text.replace("Z", "+00:00")).date()
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise ValidationError("Order must have a valid ID and creation date.") from exc
    if order_id <= 0:
        raise ValidationError("Order ID must be positive.")
    status = str(order.get("status") or "").lower().strip()
    if status not in {"pending", "on-hold", "processing", "completed", "cancelled", "failed", "refunded"}:
        raise ValidationError(f"Order {order_id}: unknown order status.")
    # A WooCommerce "completed" status alone is not proof of collected funds.
    # Preserve date_paid for explicit review before creating a sales receipt.
    paid_date = order.get("date_paid") or order.get("date_paid_gmt")
    if paid_date:
        try:
            datetime.fromisoformat(str(paid_date).replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            raise ValidationError(f"Order {order_id}: invalid payment date.") from exc
    payment_method = str(order.get("payment_method_title") or order.get("payment_method") or "")
    order_total = _money(order.get("total"), "order total")
    tax = _money(order.get("total_tax", "0"), "tax")
    shipping = _money(order.get("shipping_total", "0"), "shipping")
    if tax + shipping > order_total:
        raise ValidationError(f"Order {order_id}: shipping and tax exceed total.")
    billing = order.get("billing") or {}
    if not isinstance(billing, dict):
        raise ValidationError(f"Order {order_id}: billing must be an object.")
    name = " ".join(str(billing.get(k) or "").strip() for k in ("first_name", "last_name")).strip()
    if not name:
        name = str(billing.get("company") or "").strip()
    lines = order.get("line_items") or []
    if not isinstance(lines, list):
        raise ValidationError(f"Order {order_id}: line_items must be a list.")
    for line in lines:
        if not isinstance(line, dict):
            raise ValidationError(f"Order {order_id}: item must be an object.")
        try:
            quantity = int(line.get("quantity", 1))
        except (ValueError, TypeError) as exc:
            raise ValidationError(f"Order {order_id}: invalid item quantity.") from exc
        if quantity < 1:
            raise ValidationError(f"Order {order_id}: item quantity must be positive.")
        _money(line.get("total", "0"), "item total")
    return {
        "source_order_id": order_id,
        "order_date": created_date,
        "woo_status": status,
        "customer_name": name[:200],
        "payment_method": payment_method[:120],
        "payment_reference": str(order.get("transaction_id") or "")[:180],
        "total": order_total,
        "tax_total": tax,
        "shipping_total": shipping,
    }


@transaction.atomic
def stage_orders(orders):
    """Stage new IDs once. Never overwrite an already reviewed order."""
    if not isinstance(orders, list) or not 1 <= len(orders) <= MAX_ORDERS:
        raise ValidationError("Supply 1 to 200 WooCommerce orders.")
    normalized = []
    ids = set()
    for order in orders:
        fields = normalize_order(order)
        identifier = fields["source_order_id"]
        if identifier in ids:
            raise ValidationError(f"Order {identifier} appears twice in this upload.")
        ids.add(identifier)
        normalized.append((fields, order))
    added = skipped = 0
    for fields, order in normalized:
        _, created = WooOrderImport.objects.get_or_create(
            source_order_id=fields["source_order_id"],
            defaults={**fields, "payload": order},
        )
        if created:
            added += 1
        else:
            skipped += 1
    return added, skipped


@transaction.atomic
def create_reviewed_receipt(record):
    """No journal entry. Explicit reviewer action is required."""
    from accounting_contacts.woo_receipts import stage_woo_order_receipt
    from accounting_contacts.models import ReceiptItem
    from django.utils import timezone

    record = WooOrderImport.objects.select_for_update().get(pk=record.pk)
    if record.review_status != WooOrderImport.PENDING:
        raise ValidationError("Only pending orders can be reviewed for a receipt.")
    if record.woo_status not in PAID_STATUSES or not (
        record.payload.get("date_paid") or record.payload.get("date_paid_gmt")
    ):
        raise ValidationError("A processing/completed order must have a recorded payment date before creating a sales receipt.")
    if not record.payload:
        raise ValidationError("Original order metadata is unavailable.")
    _, receipt, created = stage_woo_order_receipt(record.payload)
    if created:
        for position, line in enumerate(record.payload.get("line_items") or [], start=1):
            name = str(line.get("name") or "Unspecified item")[:200]
            quantity = int(line.get("quantity", 1))
            amount = _money(line.get("total", "0"), "item total")
            option = ""
            for meta in line.get("meta_data") or []:
                if not isinstance(meta, dict):
                    continue
                key = str(meta.get("display_key") or meta.get("key") or "").lower().replace("_", " ").replace("-", " ")
                if key in ("print option", "pa print option"):
                    option = str(meta.get("display_value") or meta.get("value") or "")[:80]
                    break
            label = name.casefold()
            kind = "print" if option or "giclée" in label or "giclee" in label or "fine art print" in label else "original" if "original artwork" in label or "original painting" in label else "other"
            product = ReceiptItem(
                receipt=receipt, position=position,
                artwork_title=name,
                item_type=kind, size=option, quantity=quantity,
                unit_price=(amount / quantity).quantize(Decimal("0.01")),
            )
            product.full_clean()
            product.save()
    record.review_status = WooOrderImport.RECEIPTED
    record.receipt_id = receipt.pk
    record.reviewed_at = timezone.now()
    record.save(update_fields=["review_status", "receipt_id", "reviewed_at"])
    return receipt, created
