from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, AuditEvent, JournalEntry, JournalLine
from .reporting import balance_sheet, profit_and_loss
from .services import post_entry


class PostedReversalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reversal_test", password="pass", is_staff=True
        )
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.sales = Account.objects.create(number="4001", name="Sales", account_type="income")
        self.entry = JournalEntry.objects.create(
            date=date(2027, 1, 5), description="Sale to reverse",
            source="manual", created_by=self.user,
        )
        JournalLine.objects.create(entry=self.entry, account=self.bank, debit=Decimal("175.00"))
        JournalLine.objects.create(entry=self.entry, account=self.sales, credit=Decimal("175.00"))
        post_entry(self.entry.pk, actor=self.user)
        self.url = reverse("accounting:transaction_reverse", args=[self.entry.pk])

    def reverse(self, **changes):
        data = {"date": "2027-01-12", "reason": "Incorrect amount; will replace"}
        data.update(changes)
        return self.client.post(self.url, data)

    def test_reversal_is_separate_balanced_posted_entry_and_preserves_original(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.reverse()
        self.assertRedirects(response, reverse("accounting:transaction_list"))
        self.assertEqual(JournalEntry.objects.count(), 2)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "posted")
        self.assertIsNotNone(self.entry.reversed_by_entry_id)
        reversed_entry = self.entry.reversed_by_entry
        self.assertEqual(reversed_entry.status, "posted")
        self.assertEqual(reversed_entry.source, "manual_reversal")
        self.assertEqual(reversed_entry.lines.get(account=self.bank).credit, Decimal("175.00"))
        self.assertEqual(reversed_entry.lines.get(account=self.sales).debit, Decimal("175.00"))
        self.assertEqual(self.entry.lines.get(account=self.bank).debit, Decimal("175.00"))
        self.assertEqual(self.entry.audit_events.filter(action="reversed").count(), 1)
        self.assertEqual(reversed_entry.audit_events.filter(action="posted").count(), 1)
        self.assertEqual(
            profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))["net_profit"],
            Decimal("0.00"),
        )
        self.assertTrue(balance_sheet(date(2027, 1, 31))["balanced"])

    def test_reports_show_original_until_reversal_date(self):
        self.reverse()
        before = profit_and_loss(date(2027, 1, 1), date(2027, 1, 10))
        after = profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))
        self.assertEqual(before["net_profit"], Decimal("175.00"))
        self.assertEqual(after["net_profit"], Decimal("0.00"))

    def test_cannot_reverse_twice_or_reverse_reversal(self):
        self.reverse()
        self.entry.refresh_from_db()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.reverse().status_code, 404)
        self.assertEqual(
            self.client.get(reverse("accounting:transaction_reverse", args=[self.entry.reversed_by_entry_id])).status_code,
            404,
        )
        self.assertEqual(JournalEntry.objects.count(), 2)

    def test_reversal_cannot_predate_original_and_needs_reason(self):
        response = self.reverse(date="2027-01-02")
        self.assertContains(response, "cannot predate")
        response = self.reverse(reason="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_reversal_is_staff_only(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.reverse().status_code, 302)
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_non_posted_entry_cannot_be_reversed(self):
        draft = JournalEntry.objects.create(date=date(2027, 1, 7), source="manual")
        self.assertEqual(
            self.client.get(reverse("accounting:transaction_reverse", args=[draft.pk])).status_code,
            404,
        )
