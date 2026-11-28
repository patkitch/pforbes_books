from decimal import Decimal
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, JournalEntry, JournalLine


class FinancialExportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="report_export_test", password="test-password", is_staff=True
        )
        self.client.force_login(self.user)
        self.card = Account.objects.create(number="2003", name="Visa", account_type="liability")
        self.supplies = Account.objects.create(number="5004", name="Supplies & Materials", account_type="cogs")
        from datetime import date
        posted = JournalEntry.objects.create(date=date(2027, 1, 5), status="posted", description="Supplies test")
        JournalLine.objects.create(entry=posted, account=self.supplies, debit=Decimal("145.50"))
        JournalLine.objects.create(entry=posted, account=self.card, credit=Decimal("145.50"))
        draft = JournalEntry.objects.create(date=date(2027, 1, 6), status="draft", description="Draft ignored")
        JournalLine.objects.create(entry=draft, account=self.supplies, debit=Decimal("999.00"))
        JournalLine.objects.create(entry=draft, account=self.card, credit=Decimal("999.00"))

    def url(self, kind, format):
        return reverse("accounting:report_download", args=[kind, format])

    def test_pl_excel_has_numeric_amounts_and_correct_dates(self):
        response = self.client.get(self.url("pl", "xlsx"), {
            "start": "2027-01-01", "end": "2027-01-31",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        with ZipFile(BytesIO(response.content)) as z:
            xml = z.read("xl/worksheets/sheet1.xml")
            self.assertIn(b"145.50", xml)
            self.assertNotIn(b"999.00", xml)
            root = ElementTree.fromstring(xml)
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            numbers = [v.text for v in root.findall(".//x:c/x:v", ns)]
            self.assertIn("145.50", numbers)
            self.assertIn("-145.50", numbers)
            self.assertIn(b"2027-01-31", xml)

    def test_balance_sheet_excel_has_matching_totals(self):
        response = self.client.get(self.url("bs", "xlsx"))
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as z:
            xml = z.read("xl/worksheets/sheet1.xml")
        self.assertIn(b"Accumulated earnings", xml)
        self.assertIn(b"-145.50", xml)
        self.assertIn(b"Balance Sheet balances", xml)

    def test_both_pdf_downloads_are_valid_pdf_bytes(self):
        for kind in ["pl", "bs"]:
            with self.subTest(kind=kind):
                response = self.client.get(self.url(kind, "pdf"))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertTrue(response.content.startswith(b"%PDF-"))
                self.assertGreater(len(response.content), 1200)

    def test_invalid_dates_and_formats_cannot_export(self):
        self.assertEqual(self.client.get(self.url("pl", "xlsx"), {
            "start": "2027-02-01", "end": "2027-01-01"
        }).status_code, 400)
        self.assertEqual(self.client.get(self.url("bs", "pdf"), {
            "as_of": "2025-12-31"
        }).status_code, 400)
        self.assertEqual(self.client.get(self.url("bs", "txt")).status_code, 400)

    def test_only_staff_may_download(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url("pl", "xlsx")).status_code, 302)
        self.client.force_login(self.user)
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        self.assertEqual(self.client.get(self.url("bs", "pdf")).status_code, 302)

    def test_report_screens_show_export_links(self):
        self.assertContains(self.client.get(reverse("accounting:profit_loss")), "Download Excel")
        self.assertContains(self.client.get(reverse("accounting:balance_sheet")), "Download PDF")
