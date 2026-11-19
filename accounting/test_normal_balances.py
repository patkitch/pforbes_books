"""Account normal-side selection and contra-account financial behavior."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import AccountForm
from .models import Account, JournalEntry, JournalLine
from .reporting import balance_sheet, profit_and_loss
from .trial_reporting import trial_balance


class NormalBalanceTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="normal_balance_tester", password="secret", is_staff=True
        )
        self.client.force_login(user)

    def test_each_account_type_has_correct_standard_balance(self):
        expected = {
            "asset": "debit", "liability": "credit", "equity": "credit",
            "income": "credit", "cogs": "debit", "expense": "debit",
            "other_income": "credit", "other_expense": "debit",
        }
        self.assertEqual(Account.DEFAULT_BALANCES, expected)
        for kind, side in expected.items():
            with self.subTest(kind=kind):
                account = Account(account_type=kind)
                self.assertEqual(account.normal_side, side)
        self.assertEqual(Account(account_type="income", normal_balance="debit").normal_side, "debit")
        self.assertEqual(Account(account_type="asset", normal_balance="credit").normal_side, "credit")

    def test_account_editor_shows_category_hints_and_normal_balance(self):
        account = Account.objects.create(
            number="4010", name="Sales Income", account_type="income"
        )
        response = self.client.get(reverse("accounting:account_edit", args=[account.pk]))
        self.assertContains(response, "Income — Credit")
        self.assertContains(response, "Asset — Debit")
        self.assertContains(response, "Normal Balance")
        self.assertContains(response, "id_normal_balance")
        self.assertEqual(response.context["form"].initial["normal_balance"], "credit")
        self.assertContains(
            response, '<option value="credit" selected>Credit</option>', html=False
        )
        self.assertNotContains(
            response, '<option value="debit" selected>Debit</option>', html=False
        )
        response = self.client.post(reverse("accounting:account_edit", args=[account.pk]), {
            "number": "4010", "name": "Sales Income",
            "account_type": "income", "normal_balance": "debit",
        })
        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        self.assertEqual(account.normal_balance, "debit")

    def test_existing_accounts_default_to_correct_normal_balance_in_html(self):
        for index, (kind, expected_side) in enumerate(Account.DEFAULT_BALANCES.items(), start=1):
            with self.subTest(kind=kind):
                account = Account.objects.create(
                    number=f"{index}001", name=f"Existing {kind}", account_type=kind
                )
                response = self.client.get(
                    reverse("accounting:account_edit", args=[account.pk])
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context["form"].initial["normal_balance"], expected_side
                )
                self.assertContains(
                    response,
                    f'<option value="{expected_side}" selected>{expected_side.title()}</option>',
                )

    def test_new_account_defaults_to_standard_side_without_field(self):
        form = AccountForm(data={
            "number": "2001", "name": "Credit card", "account_type": "liability",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().normal_side, "credit")

    def test_contra_revenue_reduces_net_sales_and_preserves_trial_balance(self):
        bank = Account.objects.create(number="1001", name="Bank", account_type="asset")
        sales = Account.objects.create(number="4011", name="Artwork", account_type="income")
        discount = Account.objects.create(
            number="4020", name="Discounts Given", account_type="income",
            normal_balance="debit",
        )
        entry = JournalEntry.objects.create(date=date(2026, 11, 19), status="posted")
        JournalLine.objects.create(entry=entry, account=bank, debit=Decimal("450"))
        JournalLine.objects.create(entry=entry, account=discount, debit=Decimal("50"))
        JournalLine.objects.create(entry=entry, account=sales, credit=Decimal("500"))
        pl = profit_and_loss(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(pl["totals"]["income"], Decimal("450"))
        self.assertEqual(pl["net_profit"], Decimal("450"))
        discounts = [r for g in pl["groups"] for r in g["rows"] if r["account"].pk == discount.pk]
        self.assertEqual(discounts[0]["amount"], Decimal("-50"))
        bs = balance_sheet(date(2026, 12, 31))
        self.assertTrue(bs["balanced"])
        self.assertEqual(bs["totals"]["asset"], Decimal("450"))
        trial = trial_balance(date(2026, 12, 31))
        self.assertTrue(trial["balanced"])
        self.assertEqual(trial["debits"], Decimal("500"))
        self.assertEqual(trial["credits"], Decimal("500"))

    def test_credit_normal_contra_asset_reduces_total_assets(self):
        bank = Account.objects.create(number="1001", name="Bank", account_type="asset")
        equipment = Account.objects.create(number="1010", name="Equipment", account_type="asset")
        accumulated = Account.objects.create(
            number="1012", name="Accumulated depreciation",
            account_type="asset", normal_balance="credit",
        )
        equity = Account.objects.create(number="3001", name="Equity", account_type="equity")
        entry = JournalEntry.objects.create(date=date(2026, 5, 1), status="posted")
        JournalLine.objects.create(entry=entry, account=equipment, debit=Decimal("1000"))
        JournalLine.objects.create(entry=entry, account=accumulated, credit=Decimal("100"))
        JournalLine.objects.create(entry=entry, account=equity, credit=Decimal("900"))
        bs = balance_sheet(date(2026, 12, 31))
        self.assertEqual(bs["totals"]["asset"], Decimal("900"))
        self.assertTrue(bs["balanced"])
        rows = [r for g in bs["groups"] for r in g["rows"] if r["account"].pk == accumulated.pk]
        self.assertEqual(rows[0]["amount"], Decimal("-100"))
