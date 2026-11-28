"""Read-only CSV preview for credit-card and bank statements."""
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from .import_preview import parse_csv_preview
from .models import Account, JournalEntry
from accounting_contacts.models import Vendor


class PreviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="preview_tester", password="pass", is_staff=True
        )
        self.client.force_login(self.user)
        self.card = Account.objects.create(
            number="2003", name="Business credit card", account_type="liability"
        )
        self.owner = Account.objects.create(
            number="3004", name="Owner Investments", account_type="equity"
        )

    def upload(self, contents, account=None):
        return self.client.post(reverse("accounting:import_preview"), {
            "account": str(account or self.card.pk),
            "file": SimpleUploadedFile("statement.csv", contents, content_type="text/csv"),
        })

    def test_credit_card_statement_preview_never_posts_or_creates_vendor(self):
        response = self.upload(
            b"Date,Description,Amount\n2026-10-04,MPix print order,-45.50\n2026-10-16,Card payment,45.50\n"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MPix print order")
        self.assertContains(response, "Card payment")
        self.assertContains(response, "-45.50")
        self.assertContains(response, "does not save or post transactions")
        self.assertFalse(JournalEntry.objects.exists())
        self.assertFalse(Vendor.objects.exists())
        self.assertEqual(Account.objects.count(), 2)

    def test_debit_credit_csv_columns_are_parsed_without_posting(self):
        rows = parse_csv_preview(
            b"Date,Description,Debit,Credit\n10/04/2026,MPix,45.50,\n10/05/2026,Card Payment,,45.50\n"
        )
        self.assertEqual([str(row["amount"]) for row in rows], ["-45.50", "45.50"])

    def test_invalid_input_rejected_without_side_effects(self):
        for data in (
            b"Date,Description,Amount\n2026-10-04,MPix,not-a-number\n",
            b"Date,Description,Amount\nnot-a-date,MPix,10.00\n",
            b"Date,Description,Amount\n2026-10-04,,10.00\n",
            b"Date,Description,Debit,Credit\n2026-10-04,MPix,10.00,20.00\n",
            b"Date,Description,Amount\n2026-10-04,MPix,NaN\n",
            b"Date,Description,Amount\n2026-10-04,MPix,3.456\n",
        ):
            with self.subTest(data=data):
                response = self.upload(data)
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.context["rows"])
        self.assertFalse(JournalEntry.objects.exists())

    def test_preview_requires_staff(self):
        self.client.logout()
        response = self.client.get(reverse("accounting:import_preview"))
        self.assertEqual(response.status_code, 302)
