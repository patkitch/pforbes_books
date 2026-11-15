from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry


class SimpleTransactionScreenTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ledger_test", password="test-password", is_staff=True
        )
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1001", name="Bank", account_type="asset")
        self.card = Account.objects.create(number="2003", name="Credit card", account_type="liability")
        self.expense = Account.objects.create(number="6100", name="Supplies", account_type="expense")
        self.income = Account.objects.create(number="4100", name="Artwork sales", account_type="income")
        self.url = reverse("accounting:transaction_new")

    def payload(self, kind="expense", action="post", **overrides):
        data = {
            "kind": kind, "date": "2027-01-05", "payee": "Test payee",
            "description": "Test purchase", "amount": "45.50",
            "category_account": str(self.expense.pk if kind == "expense" else self.income.pk),
            "payment_account": str(self.card.pk if kind == "expense" else self.bank.pk),
            "memo": "", "save_action": action,
        }
        data.update(overrides)
        return data

    def test_expense_on_credit_card_posts_balanced_entry(self):
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(response, reverse("accounting:transaction_list"))
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.lines.count(), 2)
        self.assertEqual(entry.lines.get(account=self.expense).debit, Decimal("45.50"))
        self.assertEqual(entry.lines.get(account=self.card).credit, Decimal("45.50"))
        self.assertEqual(entry.audit_events.count(), 1)

    def test_income_into_bank_posts_balanced_entry(self):
        response = self.client.post(self.url, self.payload(kind="income"))
        self.assertEqual(response.status_code, 302)
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.lines.get(account=self.bank).debit, Decimal("45.50"))
        self.assertEqual(entry.lines.get(account=self.income).credit, Decimal("45.50"))

    def test_draft_saved_without_posting(self):
        response = self.client.post(self.url, self.payload(action="draft"))
        self.assertEqual(response.status_code, 302)
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.status, "draft")
        self.assertEqual(entry.audit_events.count(), 0)

    def test_income_cannot_use_expense_category(self):
        response = self.client.post(self.url, self.payload(kind="income", category_account=str(self.expense.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "matches the transaction type")
        self.assertFalse(JournalEntry.objects.exists())

    def test_inactive_card_is_not_accepted(self):
        self.card.is_active = False
        self.card.save(update_fields=["is_active"])
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(JournalEntry.objects.exists())

    def test_pre_2027_transaction_rejected(self):
        response = self.client.post(self.url, self.payload(date="2026-12-31"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "begins January 1, 2027")
        self.assertFalse(JournalEntry.objects.exists())

    def test_non_staff_cannot_enter_transaction(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(JournalEntry.objects.exists())

    def test_register_shows_entry(self):
        self.client.post(self.url, self.payload())
        response = self.client.get(reverse("accounting:transaction_list"))
        self.assertContains(response, "Test purchase")
        self.assertContains(response, "Posted")

    def test_existing_draft_can_be_posted_without_duplicate(self):
        self.client.post(self.url, self.payload(action="draft"))
        entry = JournalEntry.objects.get()
        edit_url = reverse("accounting:transaction_edit", args=[entry.pk])
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(edit_url, self.payload(action="post", description="Updated purchase"))
        self.assertRedirects(response, reverse("accounting:transaction_list"))
        self.assertEqual(JournalEntry.objects.count(), 1)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.description, "Updated purchase")
        self.assertEqual(entry.lines.count(), 2)
        self.assertEqual(entry.audit_events.filter(action="posted").count(), 1)

    def test_existing_draft_can_be_edited_without_posting(self):
        self.client.post(self.url, self.payload(action="draft"))
        entry = JournalEntry.objects.get()
        response = self.client.post(
            reverse("accounting:transaction_edit", args=[entry.pk]),
            self.payload(action="draft", amount="19.75"),
        )
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")
        self.assertEqual(entry.lines.get(account=self.expense).debit, Decimal("19.75"))
        self.assertEqual(entry.audit_events.count(), 0)

    def test_posted_entry_cannot_be_edited(self):
        self.client.post(self.url, self.payload(action="post"))
        entry = JournalEntry.objects.get()
        edit_url = reverse("accounting:transaction_edit", args=[entry.pk])
        self.assertEqual(self.client.get(edit_url).status_code, 404)
        self.assertEqual(
            self.client.post(edit_url, self.payload(action="draft", amount="1.00")).status_code,
            404,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.lines.get(account=self.expense).debit, Decimal("45.50"))

    def test_invalid_draft_edit_does_not_change_entry(self):
        self.client.post(self.url, self.payload(action="draft"))
        entry = JournalEntry.objects.get()
        response = self.client.post(
            reverse("accounting:transaction_edit", args=[entry.pk]),
            self.payload(action="post", amount="0"),
        )
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")
        self.assertEqual(entry.lines.get(account=self.expense).debit, Decimal("45.50"))
