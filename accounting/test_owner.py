from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry
from .reporting import balance_sheet, profit_and_loss


class OwnerContributionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="owner_test", password="pass", is_staff=True
        )
        self.client.force_login(self.user)
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.card = Account.objects.create(number="2003", name="Card", account_type="liability")
        self.equity = Account.objects.create(number="3100", name="Owner contribution", account_type="equity")
        self.cogs = Account.objects.create(number="5004", name="Supplies", account_type="cogs")
        self.sales = Account.objects.create(number="4001", name="Sales", account_type="income")

    def payload(self, kind="cash", action="post", **kwargs):
        data = {
            "kind": kind, "date": "2027-01-10", "payee": "Owner",
            "description": "Owner funds", "amount": "125.00",
            "contribution_account": str(self.equity.pk),
            "destination_account": str(self.bank.pk if kind == "cash" else self.cogs.pk),
            "memo": "", "save_action": action,
        }
        data.update(kwargs)
        return data

    def test_cash_owner_contribution_is_equity_not_income(self):
        response = self.client.post(reverse("accounting:owner_new"), self.payload())
        self.assertRedirects(response, reverse("accounting:transaction_list"))
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.lines.get(account=self.bank).debit, Decimal("125.00"))
        self.assertEqual(entry.lines.get(account=self.equity).credit, Decimal("125.00"))
        self.assertEqual(entry.audit_events.filter(action="posted").count(), 1)
        self.assertEqual(profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))["net_profit"], 0)
        bs = balance_sheet(date(2027, 1, 31))
        self.assertEqual(bs["totals"]["asset"], Decimal("125.00"))
        self.assertEqual(bs["totals"]["equity"], Decimal("125.00"))
        self.assertTrue(bs["balanced"])

    def test_personally_paid_supplies_record_one_business_expense(self):
        self.client.post(reverse("accounting:owner_new"), self.payload(kind="personal_expense"))
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.lines.get(account=self.cogs).debit, Decimal("125.00"))
        self.assertEqual(entry.lines.get(account=self.equity).credit, Decimal("125.00"))
        self.assertEqual(entry.lines.count(), 2)
        self.assertEqual(profit_and_loss(date(2027, 1, 1), date(2027, 1, 31))["net_profit"], Decimal("-125.00"))
        bs = balance_sheet(date(2027, 1, 31))
        self.assertEqual(bs["totals"]["liability"], Decimal("0.00"))
        self.assertTrue(bs["balanced"])

    def test_draft_edit_post_without_duplicate(self):
        self.client.post(reverse("accounting:owner_new"), self.payload(action="draft"))
        entry = JournalEntry.objects.get()
        edit = reverse("accounting:owner_edit", args=[entry.pk])
        self.assertEqual(self.client.get(edit).status_code, 200)
        self.client.post(edit, self.payload(action="post", amount="150.25"))
        entry.refresh_from_db()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.lines.get(account=self.bank).debit, Decimal("150.25"))
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(self.client.get(edit).status_code, 404)

    def test_wrong_account_type_and_pre_2026_rejected(self):
        url = reverse("accounting:owner_new")
        response = self.client.post(url, self.payload(destination_account=str(self.cogs.pk)))
        self.assertContains(response, "Choose a bank account")
        response = self.client.post(url, self.payload(kind="personal_expense", destination_account=str(self.bank.pk)))
        self.assertContains(response, "Choose a bank account")
        response = self.client.post(url, self.payload(contribution_account=str(self.card.pk)))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(url, self.payload(date="2025-12-31"))
        self.assertContains(response, "begins January 1, 2026")
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_nonstaff_cannot_use_owner_form(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        response = self.client.post(reverse("accounting:owner_new"), self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(JournalEntry.objects.exists())

    def test_owner_draft_link_on_register(self):
        self.client.post(reverse("accounting:owner_new"), self.payload(action="draft"))
        self.assertContains(self.client.get(reverse("accounting:transaction_list")), "Edit contribution / Post")
