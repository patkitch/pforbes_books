from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Account, JournalEntry, JournalLine
from .services import post_entry


class LockedPeriodTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="lock_test", password="pass", is_staff=True
        )
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1001", name="Bank", account_type="asset")
        self.sales = Account.objects.create(number="4001", name="Sales", account_type="income")
        self.entry = JournalEntry.objects.create(
            date=date(2027, 1, 5), description="Locked draft", status="draft"
        )
        JournalLine.objects.create(entry=self.entry, account=self.bank, debit=Decimal("15"))
        JournalLine.objects.create(entry=self.entry, account=self.sales, credit=Decimal("15"))

    @override_settings(ACCOUNTING_LOCK_THROUGH_DATE="2027-01-31")
    def test_locked_draft_cannot_be_posted_even_through_service(self):
        with self.assertRaises(ValidationError):
            post_entry(self.entry.pk, actor=self.user)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "draft")
        self.assertFalse(self.entry.audit_events.exists())

    @override_settings(ACCOUNTING_LOCK_THROUGH_DATE="2027-01-31")
    def test_locked_date_rejected_on_simple_and_journal_forms(self):
        response = self.client.post(reverse("accounting:transaction_new"), {
            "kind": "income", "date": "2027-01-10", "description": "Invalid closed sale",
            "amount": "10", "payment_account": str(self.bank.pk),
            "category_account": str(self.sales.pk), "save_action": "post",
        })
        self.assertContains(response, "accounting period is locked")
        response = self.client.post(reverse("accounting:journal_new"), {
            "date": "2027-01-11", "description": "Invalid adjustment",
            "account_1": str(self.bank.pk), "debit_1": "10",
            "account_2": str(self.sales.pk), "credit_2": "10",
            "save_action": "post",
        })
        self.assertContains(response, "accounting period is locked")
        self.assertEqual(JournalEntry.objects.count(), 1)

    @override_settings(ACCOUNTING_LOCK_THROUGH_DATE="2027-01-31")
    def test_new_february_transaction_is_allowed(self):
        self.entry.date = date(2027, 2, 1)
        self.entry.save(update_fields=["date"])
        post_entry(self.entry.pk, actor=self.user)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "posted")

    def test_default_settings_do_not_lock_periods(self):
        post_entry(self.entry.pk, actor=self.user)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "posted")
