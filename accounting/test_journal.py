from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry
from .reporting import balance_sheet, profit_and_loss


class AdvancedManualJournalTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="journal_test", password="pass", is_staff=True)
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.card = Account.objects.create(number="2003", name="Card", account_type="liability")
        self.income = Account.objects.create(number="4001", name="Artwork", account_type="income")
        self.cogs = Account.objects.create(number="5004", name="Supplies", account_type="cogs")
        self.url = reverse("accounting:journal_new")

    def payload(self, action="post", **changes):
        data = {
            "date": "2027-02-04", "payee": "Test",
            "description": "Complex journal test", "memo": "", "save_action": action,
            "account_1": str(self.bank.pk), "debit_1": "150.00", "credit_1": "",
            "account_2": str(self.income.pk), "debit_2": "", "credit_2": "100.00",
            "account_3": str(self.card.pk), "debit_3": "", "credit_3": "50.00",
        }
        data.update(changes)
        return data

    def test_balanced_three_line_journal_posts_and_statements_balance(self):
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(response, reverse("accounting:transaction_list"))
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.lines.count(), 3)
        self.assertEqual(entry.lines.get(account=self.bank).debit, Decimal("150.00"))
        self.assertEqual(entry.lines.get(account=self.card).credit, Decimal("50.00"))
        self.assertEqual(entry.audit_events.filter(action="posted").count(), 1)
        self.assertEqual(profit_and_loss(date(2027, 2, 1), date(2027, 2, 28))["net_profit"], Decimal("100.00"))
        bs = balance_sheet(date(2027, 2, 28))
        self.assertTrue(bs["balanced"])

    def test_unbalanced_entry_is_rejected(self):
        response = self.client.post(self.url, self.payload(credit_3="40.00"))
        self.assertContains(response, "must balance exactly")
        self.assertFalse(JournalEntry.objects.exists())

    def test_two_sides_on_one_line_are_rejected(self):
        response = self.client.post(self.url, self.payload(credit_1="12.00"))
        self.assertContains(response, "positive debit OR credit")
        self.assertFalse(JournalEntry.objects.exists())

    def test_missing_account_and_incomplete_line_rejected(self):
        response = self.client.post(self.url, self.payload(account_3=""))
        self.assertContains(response, "Select an account for this line")
        self.assertFalse(JournalEntry.objects.exists())

    def test_draft_edit_and_post(self):
        self.client.post(self.url, self.payload(action="draft"))
        entry = JournalEntry.objects.get()
        edit = reverse("accounting:journal_edit", args=[entry.pk])
        self.assertEqual(self.client.get(edit).status_code, 200)
        response = self.client.post(edit, self.payload(action="post", description="Updated journal"))
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.description, "Updated journal")
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(self.client.get(edit).status_code, 404)

    def test_nonstaff_cannot_post_manual_journal(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        self.assertFalse(JournalEntry.objects.exists())

    def test_general_journal_link(self):
        self.assertContains(self.client.get(reverse("accounting:transaction_list")), "General journal")
