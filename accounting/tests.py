from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Account, JournalEntry, JournalLine
from .services import post_entry


class PostingTests(TestCase):
    def setUp(self):
        self.supplies = Account.objects.create(number="6100", name="Supplies", account_type="expense")
        self.visa = Account.objects.create(number="2100", name="Visa business portion", account_type="liability")

    def make_entry(self, debit, credit):
        entry = JournalEntry.objects.create(date=date(2027, 1, 5), description="Materials")
        JournalLine.objects.create(entry=entry, account=self.supplies, debit=debit)
        JournalLine.objects.create(entry=entry, account=self.visa, credit=credit)
        return entry

    def test_balanced_entry_posts_once(self):
        entry = self.make_entry(Decimal("45.50"), Decimal("45.50"))
        post_entry(entry.pk)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.audit_events.count(), 1)
        with self.assertRaises(ValidationError):
            post_entry(entry.pk)

    def test_unbalanced_entry_rejected(self):
        entry = self.make_entry(Decimal("45.50"), Decimal("45.51"))
        with self.assertRaises(ValidationError):
            post_entry(entry.pk)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")

    def test_inactive_account_rejected(self):
        entry = self.make_entry(Decimal("45.50"), Decimal("45.50"))
        self.visa.is_active = False
        self.visa.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            post_entry(entry.pk)

    def test_invalid_account_number(self):
        account = Account(number="600", name="Bad", account_type="expense")
        with self.assertRaises(ValidationError):
            account.full_clean()
