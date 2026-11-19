from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry, JournalLine
from .trial_reporting import trial_balance


class TrialBalanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="trial_test", password="pass", is_staff=True
        )
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.sales = Account.objects.create(number="4001", name="Sales", account_type="income")
        self.parent = Account.objects.create(number="5001", name="COGS parent", account_type="cogs")
        self.supplies = Account.objects.create(
            number="5004", name="Supplies", account_type="cogs", parent=self.parent
        )

    def entry(self, day, status, lines):
        entry = JournalEntry.objects.create(
            date=date(2027, 1, day), description="Trial test", status=status
        )
        for account, debit, credit in lines:
            JournalLine.objects.create(
                entry=entry, account=account,
                debit=Decimal(debit), credit=Decimal(credit),
            )

    def test_trial_balance_uses_posted_lines_and_direct_accounts(self):
        self.entry(2, "posted", [
            (self.bank, "200", "0"), (self.sales, "0", "200")
        ])
        self.entry(3, "posted", [
            (self.supplies, "50", "0"), (self.bank, "0", "50")
        ])
        self.entry(4, "draft", [
            (self.supplies, "500", "0"), (self.bank, "0", "500")
        ])
        report = trial_balance(date(2027, 1, 31))
        self.assertTrue(report["balanced"])
        self.assertEqual(report["debits"], Decimal("200"))
        self.assertEqual(report["credits"], Decimal("200"))
        amounts = {row["account"].number: row for row in report["rows"]}
        self.assertEqual(amounts["1001"]["debit"], Decimal("150"))
        self.assertEqual(amounts["5004"]["debit"], Decimal("50"))
        self.assertNotIn("5001", amounts)
        self.assertEqual(trial_balance(date(2027, 1, 2))["debits"], Decimal("200"))

    def test_screen_renders_and_csv_exports_same_balances(self):
        self.entry(2, "posted", [
            (self.bank, "100", "0"), (self.sales, "0", "100")
        ])
        response = self.client.get(reverse("accounting:trial_balance"))
        self.assertContains(response, "Trial Balance balances")
        self.assertContains(response, "100.00")
        response = self.client.get(reverse("accounting:trial_balance_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(b"100.00", response.content)
        self.assertIn(b"Total", response.content)
        self.assertIn(b"1001", response.content)

    def test_invalid_as_of_rejected(self):
        url = reverse("accounting:trial_balance_csv")
        self.assertEqual(
            self.client.get(url, {"as_of": "2025-12-31"}).status_code, 400
        )

    def test_unapproved_user_cannot_export(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(
            self.client.get(reverse("accounting:trial_balance")).status_code, 302
        )
        self.assertEqual(
            self.client.get(reverse("accounting:trial_balance_csv")).status_code, 302
        )
