"""Safely associate a contact with an existing journal entry.

Contact links never alter posted debit/credit lines; all changes are audited.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.models import AuditEvent, JournalEntry
from .models import Customer, TransactionParty, Vendor


@transaction.atomic
def link_contact(entry, *, vendor=None, customer=None, actor=None, allow_inactive=False):
    if bool(vendor) == bool(customer):
        raise ValidationError("Specify exactly one vendor or customer.")
    if not JournalEntry.objects.filter(pk=entry.pk).exists():
        raise ValidationError("Journal transaction does not exist.")
    if vendor is not None and (not isinstance(vendor, Vendor) or (not allow_inactive and not vendor.is_active)):
        raise ValidationError("Choose an active vendor.")
    if customer is not None and (not isinstance(customer, Customer) or (not allow_inactive and not customer.is_active)):
        raise ValidationError("Choose an active customer.")

    link, created = TransactionParty.objects.select_for_update().get_or_create(
        journal_entry_id=entry.pk, defaults={"vendor": vendor, "customer": customer}
    )
    if not created:
        link.vendor = vendor
        link.customer = customer
        link.full_clean()
        link.save(update_fields=("vendor", "customer"))
    AuditEvent.objects.create(
        entry=entry, actor=actor, action="contact_linked",
        note=f"Linked {'vendor' if vendor else 'customer'} #{vendor.pk if vendor else customer.pk}",
    )
    return link
