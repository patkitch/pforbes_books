"""Explicitly create an internal receipt from a reviewed direct Stripe sale."""
from datetime import date
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction
from accounting_contacts.models import Customer, Receipt, ReceiptItem
from accounting.models import Account
from .models import StripePaymentImport
from .stripe_imports import classify


@transaction.atomic
def create_receipt(payment):
    payment = StripePaymentImport.objects.select_for_update().get(pk=payment.pk)
    if classify(payment)[0] != "Possible direct sale — review required" or payment.review_data.get("state") != "reviewed":
        raise ValidationError("Only a reviewed direct business sale can create a receipt.")
    data = payment.review_data
    existing = Receipt.objects.filter(source="stripe_direct",source_reference=payment.charge_id).first()
    if existing:
        return existing, False
    try:
        qty = int(data["quantity"])
        price, shipping, tax = (Decimal(data[k]) for k in ("unit_price","shipping","tax"))
        day = date.fromisoformat(data["sale_date"])
        if qty < 1 or any(not x.is_finite() or x<0 for x in (price,shipping,tax)) or qty*price+shipping+tax != payment.gross:
            raise ValueError
    except (KeyError,ValueError,TypeError,InvalidOperation) as exc:
        raise ValidationError("Saved sale allocation is invalid. Review the sale again.") from exc
    if not Account.objects.filter(pk=data.get("revenue"),is_active=True,account_type="income").exists():
        raise ValidationError("Revenue account is no longer active.")
    if shipping and not Account.objects.filter(pk=data.get("shipping_account"),is_active=True,account_type="income").exists():
        raise ValidationError("Shipping income account is no longer active.")
    if tax and (not data.get("jurisdiction") or not Account.objects.filter(pk=data.get("tax_account"),is_active=True,account_type="liability").exists()):
        raise ValidationError("Tax allocation is no longer valid.")
    email = data.get("customer_email","").strip()
    if payment.customer_email and email.casefold()!=payment.customer_email.casefold():
        raise ValidationError("Customer email must match the payment.")
    matches = list(Customer.objects.select_for_update().filter(email__iexact=email)[:2]) if email else []
    if len(matches)>1 or (matches and not matches[0].is_active):
        raise ValidationError("Resolve ambiguous or inactive customer matches before creating the receipt.")
    selected = data.get("customer")
    if selected and (not matches or matches[0].pk != selected):
        raise ValidationError("Selected customer no longer matches the verified email.")
    if not email and not selected:
        raise ValidationError("A verified customer email is required for direct Stripe receipt creation.")
    customer = matches[0] if matches else Customer.objects.create(
        name=data["customer_name"],email=email,**{k:data.get(k,"") for k in
        ("billing_address1","billing_city","billing_state","billing_postal_code","billing_country")})
    # Immutable receipt snapshot uses existing receipt display fields. No Woo order is fabricated.
    receipt=Receipt(title=f"Stripe direct sale — {data['artwork']}"[:200],receipt_type="sale",
        date=day,amount=payment.gross,customer=customer,source="stripe_direct",source_reference=payment.charge_id,
        notes="Internal sales receipt from a reviewed Stripe payment. No journal entry posted.",
        woo_snapshot={"currency":"USD","total":str(payment.gross),"total_tax":str(tax),"shipping_total":str(shipping),
            "payment_method_title":"Stripe direct payment","date_paid":day.isoformat(),"transaction_id":payment.charge_id,
            "billing":{"first_name":data["customer_name"],"email":email,"address_1":data.get("billing_address1",""),
                "city":data.get("billing_city",""),"state":data.get("billing_state",""),"postcode":data.get("billing_postal_code",""),
                "country":data.get("billing_country","")},
            "line_items":[{"name":data["artwork"],"quantity":qty,"subtotal":str(qty*price),"total":str(qty*price),
                "meta_data":[{"display_key":"Size","display_value":data.get("size","")}]}],
            "meta_data":[{"key":"_stripe_fee","value":str(payment.fee)},{"key":"_stripe_net","value":str(payment.gross-payment.fee)}]})
    receipt.full_clean()
    receipt.save()
    item=ReceiptItem(receipt=receipt,artwork_title=data["artwork"],item_type=data["item_type"],
        size=data.get("size",""),quantity=qty,unit_price=price)
    item.full_clean()
    item.save()
    return receipt,True
