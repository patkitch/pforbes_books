"""Transaction-level posting controls. No bank or WooCommerce imports yet."""
from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, JournalEntry, JournalLine
from .period_controls import ensure_open_period


@transaction.atomic
def post_entry(entry_id, *, actor=None):
    """Post an existing draft only when it is complete and balanced.

    Journal lines should be entered/edited only while the entry is a draft.
    Other callers must not update posted lines directly; service/API permissions
    and immutable-posted-entry enforcement remain before production.
    """
    entry = JournalEntry.objects.select_for_update().get(pk=entry_id)
    if entry.status != "draft":
        raise ValidationError("Only draft entries can be posted.")
    if entry.date < date(2027, 1, 1):
        raise ValidationError("This ledger begins January 1, 2027.")
    ensure_open_period(entry.date)
    lines = list(entry.lines.select_related("account").order_by("pk"))
    if len(lines) < 2:
        raise ValidationError("A journal entry needs at least two lines.")
    debit = Decimal("0.00")
    credit = Decimal("0.00")
    for line in lines:
        line.full_clean()
        if not line.account.is_active:
            raise ValidationError(f"Account {line.account.number} is inactive.")
        debit += line.debit
        credit += line.credit
    if debit <= 0 or debit != credit:
        raise ValidationError("Total debits must equal total credits and be positive.")
    entry.status = "posted"
    entry.posted_at = timezone.now()
    entry.save(update_fields=["status", "posted_at"])
    AuditEvent.objects.create(entry=entry, action="posted", actor=actor)
    return entry
