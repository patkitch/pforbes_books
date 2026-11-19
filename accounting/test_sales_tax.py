"""Quarterly tax payment workflow, including a zero cash payment."""
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry, JournalLine, SalesTaxPayment, SalesTaxRecord
from .sales_tax import quarterly_summary, record_tax_payment


class SalesTaxTests(TestCase):
    def setUp(self):
        self.ks = Account.objects.create(
            number="2007", name="Kansas Department of Revenue Payable",
            account_type="liability",
        )
        self.mo = Account.objects.create(
            number="2010", name="Missouri Department of Revenue Payable",
            account_type="liability",
        )
        self.cash = Account.objects.create(
            number="1011", name="Cash", account_type="asset"
        )
        self.bank = Account.objects.create(
            number="1001", name="Checking", account_type="asset"
        )
        self.user = get_user_model().objects.create_user(
            username="tax_tester", password="pass", is_staff=True
        )
        self.client.force_login(self.user)

    def test_zero_cash_payment_saves_history_without_journal(self):
        data = {
            "authority": self.ks, "year": 2026, "quarter": "4",
            "amount": Decimal("0.00"), "paid_on": date(2026, 11, 19),
            "bank_account": self.cash, "memo": "Zero tax filed",
        }
        record = record_tax_payment(data, actor=self.user)
        self.assertEqual(record.amount, Decimal("0.00"))
        self.assertEqual(record.bank_account, self.cash)
        self.assertIsNone(record.journal_entry)
        self.assertFalse(JournalEntry.objects.exists())
        self.assertEqual(
            quarterly_summary(year=2026, quarter=4, authority=self.ks)["paid"],
            Decimal("0.00"),
        )

    def test_positive_tax_payment_posts_liability_debit_cash_credit(self):
        record = record_tax_payment({
            "authority": self.ks, "year": 2026, "quarter": "4",
            "amount": Decimal("6.22"), "paid_on": date(2026, 11, 19),
            "bank_account": self.bank, "memo": "State payment",
        }, actor=self.user)
        self.assertIsNotNone(record.journal_entry_id)
        self.assertEqual(record.journal_entry.status, "posted")
        self.assertEqual(
            JournalLine.objects.get(entry=record.journal_entry, account=self.ks).debit,
            Decimal("6.22"),
        )
        self.assertEqual(
            JournalLine.objects.get(entry=record.journal_entry, account=self.bank).credit,
            Decimal("6.22"),
        )
        self.assertEqual(
            quarterly_summary(year=2026, quarter=4, authority=self.ks)["paid"],
            Decimal("6.22"),
        )

    def test_payment_screen_allows_zero_using_cash(self):
        response = self.client.post(reverse("accounting:sales_tax"), {
            "authority": self.ks.pk, "year": "2026", "quarter": "4",
            "amount": "0.00", "paid_on": "2026-11-19",
            "bank_account": self.cash.pk, "memo": "No tax due",
        })
        self.assertEqual(response.status_code, 302)
        record = SalesTaxPayment.objects.get()
        self.assertEqual(record.amount, Decimal("0.00"))
        self.assertEqual(record.bank_account_id, self.cash.pk)
        self.assertIsNone(record.journal_entry_id)
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_quarterly_report_shows_sales_not_gallery_tax(self):
        sale = SalesTaxRecord.objects.create(
            sale_date=date(2026, 11, 10), source="stripe",
            authority=self.ks, sale_amount=Decimal("510.00"),
            taxable_amount=Decimal("60.00"), tax_collected=Decimal("6.22"),
        )
        summary = quarterly_summary(year=2026, quarter=4, authority=self.ks)
        self.assertEqual(summary["total_sales"], Decimal("510.00"))
        self.assertEqual(summary["nontaxable_sales"], Decimal("450.00"))
        self.assertEqual(summary["taxable_sales"], Decimal("60.00"))
        self.assertEqual(summary["tax_collected"], Decimal("6.22"))
        self.assertEqual(summary["remaining"], Decimal("6.22"))
        self.assertEqual(quarterly_summary(year=2026, quarter=4, authority=self.mo)["tax_collected"], Decimal("0.00"))

    def test_gallery_cannot_record_own_collected_tax(self):
        record = SalesTaxRecord(
            sale_date=date(2026, 11, 1), source="gallery",
            sale_amount=Decimal("100"), taxable_amount=Decimal("100"),
            tax_collected=Decimal("9.00"), authority=self.ks,
        )
        with self.assertRaises(ValidationError):
            record.full_clean()
