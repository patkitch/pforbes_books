from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry, JournalLine


class SplitTransactionTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="split_test", password="test-password", is_staff=True
        )
        self.user = user
        self.client.force_login(user)
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.card = Account.objects.create(number="2003", name="Visa", account_type="liability")
        self.paint = Account.objects.create(number="5004", name="Paint", account_type="cogs")
        self.packaging = Account.objects.create(number="6100", name="Packaging", account_type="expense")
        self.sales = Account.objects.create(number="4001", name="Artwork sales", account_type="income")
        self.commission = Account.objects.create(number="4002", name="Commission revenue", account_type="income")
        self.url = reverse("accounting:split_new")

    def payload(self, *, kind="expense", action="post", **updates):
        income = kind == "income"
        result = {
            "kind": kind, "date": "2027-02-01", "payee": "Test store",
            "description": "Split test", "memo": "", "save_action": action,
            "payment_account": str(self.bank.pk if income else self.card.pk),
            "category_1": str(self.sales.pk if income else self.paint.pk),
            "amount_1": "60.00",
            "category_2": str(self.commission.pk if income else self.packaging.pk),
            "amount_2": "40.00",
        }
        result.update(updates)
        return result

    def test_expense_split_creates_three_balanced_lines(self):
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(response, reverse("accounting:transaction_list"))
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.lines.count(), 3)
        self.assertEqual(entry.lines.get(account=self.paint).debit, Decimal("60.00"))
        self.assertEqual(entry.lines.get(account=self.packaging).debit, Decimal("40.00"))
        self.assertEqual(entry.lines.get(account=self.card).credit, Decimal("100.00"))
        self.assertEqual(entry.audit_events.filter(action="posted").count(), 1)

    def test_income_split_credits_income_categories(self):
        response = self.client.post(self.url, self.payload(kind="income"))
        self.assertEqual(response.status_code, 302)
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.lines.get(account=self.bank).debit, Decimal("100.00"))
        self.assertEqual(entry.lines.get(account=self.sales).credit, Decimal("60.00"))
        self.assertEqual(entry.lines.get(account=self.commission).credit, Decimal("40.00"))

    def test_split_draft_edit_and_post_reuses_same_entry(self):
        self.client.post(self.url, self.payload(action="draft"))
        entry = JournalEntry.objects.get()
        url = reverse("accounting:split_edit", args=[entry.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, self.payload(action="post", amount_2="50.00"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(JournalEntry.objects.count(), 1)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.lines.get(account=self.card).credit, Decimal("110.00"))

    def test_cannot_edit_posted_split(self):
        self.client.post(self.url, self.payload())
        entry = JournalEntry.objects.get()
        url = reverse("accounting:split_edit", args=[entry.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload(action="draft")).status_code, 404)

    def test_at_least_two_categories_required(self):
        response = self.client.post(self.url, self.payload(category_2="", amount_2=""))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "at least two complete split categories")
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_partial_category_row_rejected(self):
        response = self.client.post(self.url, self.payload(category_2="", amount_2="40.00"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter both the account and amount")
        self.assertFalse(JournalEntry.objects.exists())

    def test_wrong_category_type_rejected(self):
        response = self.client.post(self.url, self.payload(category_2=str(self.sales.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Category does not match transaction kind")
        self.assertFalse(JournalEntry.objects.exists())

    def test_non_staff_cannot_save_split(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(JournalEntry.objects.exists())

    def test_split_form_has_account_search_controls(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "account-filter")
        self.assertContains(response, "Type account number or name")
