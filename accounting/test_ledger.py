from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry, JournalLine


class AccountLedgerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="ledger_view_test", password="test-password", is_staff=True)
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.visa = Account.objects.create(number="2003", name="Visa", account_type="liability")
        self.supplies = Account.objects.create(number="5004", name="Supplies", account_type="cogs")
        self.sales = Account.objects.create(number="4001", name="Art sales", account_type="income")

    def entry(self, date_value, debit, credit, amount, status="posted"):
        j = JournalEntry.objects.create(date=date_value, description="Ledger test", status=status)
        JournalLine.objects.create(entry=j, account=debit, debit=Decimal(amount))
        JournalLine.objects.create(entry=j, account=credit, credit=Decimal(amount))
        return j

    def test_credit_card_balance_increases_with_credit(self):
        self.entry(date(2027, 1, 2), self.supplies, self.visa, "45.50")
        response = self.client.get(reverse("accounting:account_ledger", args=[self.visa.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["balance"], Decimal("45.50"))
        self.assertEqual(response.context["total_debits"], Decimal("0.00"))
        self.assertContains(response, "Ledger test")

    def test_draft_excluded_from_balances(self):
        self.entry(date(2027, 1, 2), self.supplies, self.visa, "45.50", status="draft")
        response = self.client.get(reverse("accounting:account_ledger", args=[self.visa.pk]))
        self.assertEqual(response.context["balance"], Decimal("0.00"))
        self.assertEqual(response.context["rows"], [])
        self.assertContains(response, "No posted transactions")

    def test_income_and_asset_use_opposite_normal_sides(self):
        self.entry(date(2027, 1, 5), self.bank, self.sales, "200.00")
        bank_page = self.client.get(reverse("accounting:account_ledger", args=[self.bank.pk]))
        income_page = self.client.get(reverse("accounting:account_ledger", args=[self.sales.pk]))
        self.assertEqual(bank_page.context["balance"], Decimal("200.00"))
        self.assertEqual(income_page.context["balance"], Decimal("200.00"))
        self.assertEqual(bank_page.context["normal_side"], "Debit")
        self.assertEqual(income_page.context["normal_side"], "Credit")

    def test_chronological_running_balance(self):
        self.entry(date(2027, 1, 9), self.supplies, self.visa, "20.00")
        self.entry(date(2027, 1, 2), self.supplies, self.visa, "45.50")
        response = self.client.get(reverse("accounting:account_ledger", args=[self.visa.pk]))
        self.assertEqual([row["balance"] for row in response.context["rows"]], [Decimal("45.50"), Decimal("65.50")])
        self.assertEqual(response.context["balance"], Decimal("65.50"))

    def test_account_register_requires_staff(self):
        self.client.logout()
        url = reverse("accounting:account_ledger", args=[self.bank.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_parent_account_does_not_double_count_child(self):
        self.supplies.parent = Account.objects.create(number="5001", name="Parent COGS", account_type="cogs")
        self.supplies.save(update_fields=["parent"])
        self.entry(date(2027, 1, 3), self.supplies, self.visa, "45.50")
        response = self.client.get(reverse("accounting:account_ledger", args=[self.supplies.parent_id]))
        self.assertEqual(response.context["balance"], Decimal("0.00"))
        self.assertEqual(len(response.context["rows"]), 0)
