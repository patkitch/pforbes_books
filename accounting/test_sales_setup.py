"""Sales-only COA migration: preserve history, protect conflicts, and rerun safely."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import Account, JournalEntry, JournalLine
from .sales_setup import organize_sales_income
from .reporting import profit_and_loss


class SalesAccountSetupTests(TestCase):
    def setUp(self):
        self.unrelated = Account.objects.create(
            number="4001", name="Billable Expense Income", account_type="income"
        )
        self.discount = Account.objects.create(
            number="4002", name="Discounts given", account_type="income",
            normal_balance="debit",
        )
        self.gallery = Account.objects.create(
            number="4003", name="Gallery Commission", account_type="income"
        )
        self.art = Account.objects.create(
            number="4005", name="Original Art Sales", account_type="income"
        )
        self.prints = Account.objects.create(
            number="4006", name="Print Sales", account_type="income"
        )
        self.bank = Account.objects.create(
            number="1001", name="Bank", account_type="asset"
        )

    def test_existing_ids_and_posted_lines_preserved_and_repeatable(self):
        entry = JournalEntry.objects.create(
            date=date(2026, 8, 4), status="posted", description="Gallery sale"
        )
        line = JournalLine.objects.create(
            entry=entry, account=self.gallery, credit=Decimal("250.00")
        )
        JournalLine.objects.create(
            entry=entry, account=self.bank, debit=Decimal("250.00")
        )
        before = profit_and_loss(date(2026, 1, 1), date(2026, 12, 31))
        changes = organize_sales_income()
        self.assertTrue(changes)
        self.assertEqual(organize_sales_income(), [])
        self.gallery.refresh_from_db()
        self.art.refresh_from_db()
        self.prints.refresh_from_db()
        self.assertEqual(self.gallery.number, "4013")
        self.assertEqual(self.art.number, "4011")
        self.assertEqual(self.prints.number, "4012")
        parent = Account.objects.get(number="4010")
        self.assertEqual(parent.name, "Sales Income")
        self.assertEqual(parent.children.count(), 5)
        self.assertEqual(self.gallery.parent_id, parent.pk)
        self.assertEqual(line.account_id, self.gallery.pk)
        line.refresh_from_db()
        self.assertEqual(line.account_id, self.gallery.pk)
        self.assertEqual(Account.objects.get(number="4001").pk, self.unrelated.pk)
        self.assertEqual(Account.objects.get(number="4002").normal_side, "debit")
        after = profit_and_loss(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(after["totals"]["income"], before["totals"]["income"])
        income_group = next(g for g in after["groups"] if g["key"] == "income")
        subtotals = [row for row in income_group["rows"] if row.get("is_subtotal")]
        self.assertEqual(len(subtotals), 1)
        self.assertEqual(subtotals[0]["account"].number, "4010")
        self.assertEqual(subtotals[0]["amount"], Decimal("250.00"))
        self.assertEqual(after["net_profit"], Decimal("250.00"))

    def test_new_sales_channels_are_individual_subaccounts(self):
        organize_sales_income()
        for number, name in [
            ("4014", "Website Sales"), ("4015", "Commissioned Artwork Sales")
        ]:
            account = Account.objects.get(number=number)
            self.assertEqual(account.name, name)
            self.assertEqual(account.parent.number, "4010")
            self.assertEqual(account.normal_side, "credit")
        user = get_user_model().objects.create_user(
            username="test_sales_chart", password="pass", is_staff=True
        )
        self.client.force_login(user)
        page = self.client.get(reverse("accounting:chart_of_accounts"))
        self.assertContains(page, "Sales Income")
        self.assertContains(page, "Website Sales")
        self.assertContains(page, "Commissioned Artwork Sales")

    def test_sales_parent_cannot_be_posted_to_directly(self):
        from django.core.exceptions import ValidationError
        from .services import post_entry
        organize_sales_income()
        parent = Account.objects.get(number="4010")
        entry = JournalEntry.objects.create(date=date(2026, 8, 5))
        JournalLine.objects.create(entry=entry, account=self.bank, debit=Decimal("10"))
        JournalLine.objects.create(entry=entry, account=parent, credit=Decimal("10"))
        with self.assertRaisesMessage(ValidationError, "Post sales to a 4011-4015 subaccount"):
            post_entry(entry.pk)
        entry.refresh_from_db()
        self.assertEqual(entry.status, "draft")

    def test_unrelated_number_collision_aborts_everything(self):
        Account.objects.create(
            number="4014", name="Different Income Account", account_type="income"
        )
        with self.assertRaises(ValidationError):
            organize_sales_income()
        self.assertEqual(Account.objects.get(pk=self.gallery.pk).number, "4003")
        self.assertFalse(Account.objects.filter(number="4010").exists())

    def test_wrong_existing_account_name_aborts_everything(self):
        self.art.name = "Changed manually"
        self.art.save(update_fields=["name"])
        with self.assertRaises(ValidationError):
            organize_sales_income()
        self.assertFalse(Account.objects.filter(number="4010").exists())

    def test_existing_sales_parent_conflict_aborts(self):
        other_parent = Account.objects.create(
            number="4090", name="Different parent", account_type="income"
        )
        self.gallery.parent = other_parent
        self.gallery.save(update_fields=["parent"])
        with self.assertRaises(ValidationError):
            organize_sales_income()
        self.assertFalse(Account.objects.filter(number="4010").exists())
