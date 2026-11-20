"""Taxable sales: cash calculation, gross Stripe settlement and gallery proceeds."""
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry, JournalLine, SalesTaxRecord
from .sales_tax import quarterly_summary


class SalesTaxSaleTests(TestCase):
    def setUp(self):
        self.ks = Account.objects.create(number="2007", name="Kansas Tax", account_type="liability")
        self.mo = Account.objects.create(number="2010", name="Missouri Tax", account_type="liability")
        self.cash = Account.objects.create(number="1011", name="Cash", account_type="asset")
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.art = Account.objects.create(number="4011", name="Original Art Sales", account_type="income")
        self.gallery = Account.objects.create(number="4013", name="Gallery Commission", account_type="income")
        self.parent = Account.objects.create(number="4010", name="Sales Income", account_type="income")
        self.fee = Account.objects.create(number="6001", name="Stripe Fees", account_type="expense")
        user = get_user_model().objects.create_user(username="sales_tax_sales_tester", password="pass", is_staff=True)
        self.client.force_login(user)

    def data(self, **extra):
        basic = {
            "source": "cash", "sale_date": "2026-11-19",
            "description": "Original artwork", "revenue_account": str(self.art.pk),
            "deposit_account": str(self.cash.pk), "sale_amount": "100.00",
            "taxable_amount": "100.00", "authority": str(self.ks.pk),
            "tax_rate": "9.1000", "tax_collected": "", "processor_fee": "",
            "fee_account": "", "jurisdiction": "Customer pickup, Overland Park",
            "reference": "cash-100", "memo": "",
        }
        basic.update(extra)
        return basic

    def test_cash_sale_calculates_tax_and_posts_four_sides_balanced(self):
        response = self.client.post(reverse("accounting:sales_tax_sale_new"), self.data())
        self.assertEqual(response.status_code, 302, response.content.decode()[:500])
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.status, "posted")
        self.assertEqual(entry.lines.get(account=self.cash).debit, Decimal("109.10"))
        self.assertEqual(entry.lines.get(account=self.art).credit, Decimal("100.00"))
        self.assertEqual(entry.lines.get(account=self.ks).credit, Decimal("9.10"))
        record = SalesTaxRecord.objects.get()
        self.assertEqual(record.tax_collected, Decimal("9.10"))
        self.assertEqual(
            quarterly_summary(year=2026, quarter=4, authority=self.ks)["tax_collected"],
            Decimal("9.10"),
        )

    def test_stripe_fee_reconciles_gross_and_net(self):
        response = self.client.post(reverse("accounting:sales_tax_sale_new"), self.data(
            source="stripe", reference="pi_123", tax_rate="", tax_collected="8.75",
            processor_fee="3.50", fee_account=str(self.fee.pk),
        ))
        self.assertEqual(response.status_code, 302, response.content.decode()[:600])
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.lines.get(account=self.cash).debit, Decimal("105.25"))
        self.assertEqual(entry.lines.get(account=self.fee).debit, Decimal("3.50"))
        self.assertEqual(entry.lines.get(account=self.art).credit, Decimal("100.00"))
        self.assertEqual(entry.lines.get(account=self.ks).credit, Decimal("8.75"))
        self.assertEqual(sum(l.debit for l in entry.lines.all()), Decimal("108.75"))
        self.assertEqual(sum(l.credit for l in entry.lines.all()), Decimal("108.75"))

    def test_duplicate_reference_does_not_double_post(self):
        response = self.client.post(reverse("accounting:sales_tax_sale_new"), self.data())
        self.assertEqual(response.status_code, 302)
        again = self.client.post(reverse("accounting:sales_tax_sale_new"), self.data())
        self.assertEqual(again.status_code, 200)
        self.assertContains(again, "already recorded")
        self.assertEqual(JournalEntry.objects.count(), 1)

    def test_gallery_sale_does_not_create_tax_liability(self):
        response = self.client.post(reverse("accounting:sales_tax_sale_new"), self.data(
            source="gallery", revenue_account=str(self.gallery.pk),
            sale_amount="85.00", taxable_amount="0.00", authority="",
            tax_rate="", tax_collected="", reference="gallery-100",
            jurisdiction="Images Art Gallery",
        ))
        self.assertEqual(response.status_code, 302, response.content.decode()[:600])
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.lines.count(), 2)
        self.assertEqual(entry.lines.get(account=self.cash).debit, Decimal("85.00"))
        self.assertEqual(entry.lines.get(account=self.gallery).credit, Decimal("85.00"))
        self.assertEqual(SalesTaxRecord.objects.get().tax_collected, Decimal("0.00"))
        self.assertEqual(
            quarterly_summary(year=2026, quarter=4, authority=self.ks)["tax_collected"],
            Decimal("0.00"),
        )

    def test_invalid_rate_or_missing_fee_account_does_not_post(self):
        for kwargs in (
            {"tax_rate": "", "reference": "invalid1"},
            {"tax_rate": "9.0", "processor_fee": "3", "reference": "invalid2"},
            {"source": "stripe", "tax_rate": "", "tax_collected": "", "reference": "invalid3"},
        ):
            response = self.client.post(reverse("accounting:sales_tax_sale_new"), self.data(**kwargs))
            self.assertEqual(response.status_code, 200)
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_parent_income_account_rejected(self):
        response = self.client.post(reverse("accounting:sales_tax_sale_new"), self.data(revenue_account=str(self.parent.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(JournalEntry.objects.count(), 0)
