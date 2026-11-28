"""Suggestions only; never changes source rows or posts entries."""
import re
from accounting.models import Account
from accounting_contacts.models import Vendor
from .models import ImportRow

EXPENSE_TYPES = ("expense", "cogs", "other_expense")


def merchant_key(description):
    normalized = " ".join(description.casefold().split())
    if re.match(r"^amazon\s+mktpl(?:\*|\s|$)", normalized):
        return "amazon marketplace"
    if re.match(r"^mpix(?:\s|$)", normalized):
        return "mpix"
    if re.match(r"^intuit\s*\*?\s*qbooks\s+online(?:\s|$)", normalized):
        return "intuit quickbooks online"
    return normalized


def suggest(row):
    if row.amount >= 0 or row.status != ImportRow.PENDING or row.review_data:
        return {}, ""
    key = merchant_key(row.description)
    matches = []
    for candidate in ImportRow.objects.filter(status=ImportRow.REVIEWED, amount__lt=0).exclude(pk=row.pk).iterator():
        saved = candidate.review_data
        if saved.get("classification") == "expense" and saved.get("vendor") and merchant_key(candidate.description) == key:
            matches.append((candidate, saved))
    ids = {s["vendor"] for _, s in matches}
    if len(ids) != 1:
        return {}, ""
    vendor = Vendor.objects.filter(pk=next(iter(ids)), is_active=True).first()
    if not vendor:
        return {}, ""
    initial = {"vendor": vendor.pk}
    # Conflicting observed categories suppress the category suggestion even
    # if one of the reviews explicitly authorized remembering it.
    categories = {s.get("category") for _, s in matches}
    authorized = any(s.get("remember") and (
        s.get("remember_scope") == "merchant" or (
            candidate.account_id == row.account_id
            and candidate.description.casefold() == row.description.casefold()
        )
    ) for candidate, s in matches)
    if len(categories) == 1 and authorized:
        category = Account.objects.filter(pk=next(iter(categories)), is_active=True,
                                          account_type__in=EXPENSE_TYPES).first()
        if category:
            initial.update(classification="expense", category=category.pk)
            return initial, f"Suggested vendor and category from prior reviews: {vendor.name}. Verify before saving."
    return initial, f"Suggested vendor: {vendor.name}. Choose whether this purchase is business or personal; no category was assumed."
