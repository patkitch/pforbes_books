"""Simple accounting posting lock independent of database schema.

ACCOUNTING_LOCK_THROUGH_DATE may be an ISO date string (YYYY-MM-DD) or
a datetime.date in Django settings. Later the admin interface can manage this
through a secured and audited workflow.
"""
from datetime import date

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError


def locked_through():
    configured = getattr(settings, "ACCOUNTING_LOCK_THROUGH_DATE", None)
    if not configured:
        return None
    if isinstance(configured, date):
        return configured
    try:
        return date.fromisoformat(configured)
    except (ValueError, TypeError):
        raise ImproperlyConfigured(
            "ACCOUNTING_LOCK_THROUGH_DATE must be YYYY-MM-DD or a date."
        )


def period_is_locked(transaction_date):
    cutoff = locked_through()
    return cutoff is not None and transaction_date <= cutoff


def ensure_open_period(transaction_date):
    cutoff = locked_through()
    if cutoff is not None and transaction_date <= cutoff:
        raise ValidationError(
            f"Accounting period through {cutoff.isoformat()} is locked."
        )
