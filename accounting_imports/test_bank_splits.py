from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from accounting.models import Account, JournalEntry
from accounting_contacts.models import Vendor, Receipt
from .models import ImportRow
from .views import stage_rows


class BankSplitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="split_staff", is_staff=True)
        self.client.force_login(self.user)
        self.card = Account.objects.create(number="2004", name="Credit card", account_type="liability")
        self.cost = Account.objects.create(number="5004", name="Materials", account_type="cogs")
        self.office = Account.objects.create(number="6001", name="Office supplies", account_type="expense")
        self.income = Account.objects.create(number="4001", name="Sales", account_type="income")
        self.vendor = Vendor.objects.create(name="Test merchant")
        batch, _, _ = stage_rows(self.card, "test.csv", [
            {"date": date(2026, 11, 18), "description": "Test purchase", "amount": Decimal("-60.10")}
        ], self.user)
        self.row = batch.rows.get()
        self.url = reverse("accounting:bank_review", args=[self.row.pk])
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        settings = override_settings(MEDIA_ROOT=temp.name, STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        })
        settings.enable()
        self.addCleanup(settings.disable)

    def values(self, lines=None, **overrides):
        if lines is None:
            lines = [("business", self.cost.pk, "40.10", "Materials"),
                     ("personal", "", "20.00", "Personal item")]
        data = {"classification": "split", "vendor": self.vendor.pk, "memo": "Original memo",
                "splits-TOTAL_FORMS": len(lines), "splits-INITIAL_FORMS": 0}
        for index, line in enumerate(lines):
            for key, value in zip(("kind", "category", "amount", "memo"), line):
                data[f"splits-{index}-{key}"] = value
        data.update(overrides)
        return data

    def assert_rejected(self, data):
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(JournalEntry.objects.exists())

    def test_mixed_split_saves_and_reloads_exact_amounts(self):
        self.assertEqual(self.client.post(self.url, self.values()).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.REVIEWED)
        self.assertEqual(self.row.amount, Decimal("-60.10"))
        self.assertEqual(self.row.description, "Test purchase")
        self.assertEqual(self.row.review_data["business_amount"], "40.10")
        self.assertEqual(self.row.review_data["personal_amount"], "20.00")
        self.assertEqual(self.row.review_data["vendor"], self.vendor.pk)
        self.assertEqual(self.row.review_data["splits"][1]["memo"], "Personal item")
        response = self.client.get(self.url)
        self.assertEqual(response.context["split_formset"].initial, self.row.review_data["splits"])
        self.assertFalse(JournalEntry.objects.exists())

    def test_multiple_business_categories_edit_existing_split(self):
        self.client.post(self.url, self.values())
        data = self.values([("business", self.cost.pk, "40.10", "Materials"),
                            ("business", self.office.pk, "20.00", "Office")],
                           **{"splits-INITIAL_FORMS": 2})
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(Decimal(self.row.review_data["business_amount"]), Decimal("60.10"))
        self.assertEqual(Decimal(self.row.review_data["personal_amount"]), Decimal("0.00"))
        self.assertEqual(self.row.review_data["splits"][1]["category"], self.office.pk)

    def test_over_and_under_allocation_rejected(self):
        for amount in ("19.99", "20.01"):
            with self.subTest(amount=amount):
                self.assert_rejected(self.values([("business", self.cost.pk, "40.10", ""),
                                                  ("personal", "", amount, "")]))
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.PENDING)
        self.assertFalse(self.row.review_data)

    def test_invalid_or_missing_category(self):
        for category in ("", self.income.pk):
            with self.subTest(category=category):
                self.assert_rejected(self.values([("business", category, "40.10", ""),
                                                  ("personal", "", "20.00", "")]))

    def test_personal_line_cannot_have_category(self):
        self.assert_rejected(self.values([("business", self.cost.pk, "40.10", ""),
                                          ("personal", self.office.pk, "20.00", "")]))

    def test_negative_zero_and_fractional_cent_rejected(self):
        for amount in ("-20.00", "0.00", "20.001"):
            with self.subTest(amount=amount):
                self.assert_rejected(self.values([("business", self.cost.pk, "40.10", ""),
                                                  ("personal", "", amount, "")]))

    def test_invalid_edit_preserves_previous_review(self):
        self.client.post(self.url, self.values())
        self.row.refresh_from_db()
        previous = self.row.review_data.copy()
        self.assert_rejected(self.values([("business", self.cost.pk, "40.10", ""),
                                          ("personal", "", "21.00", "")],
                                         **{"splits-INITIAL_FORMS": 2}))
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_data, previous)

    def test_restore_standard_expense_clears_allocations(self):
        self.client.post(self.url, self.values())
        response = self.client.post(self.url, {"classification": "expense", "vendor": self.vendor.pk,
                                    "category": self.cost.pk, "memo": "Original memo"})
        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_data["classification"], "expense")
        self.assertEqual(self.row.review_data["category"], self.cost.pk)
        self.assertEqual(self.row.review_data["splits"], [])
        self.assertFalse(JournalEntry.objects.exists())

    def test_receipt_preserved_when_editing_allocations(self):
        response = self.client.post(self.url, self.values(attachment=SimpleUploadedFile(
            "invoice.pdf", b"%PDF-1.4\nSynthetic invoice\n%%EOF")))
        self.assertEqual(response.status_code, 302)
        receipt = Receipt.objects.get(source="bank_document")
        response = self.client.post(self.url, self.values([("business", self.cost.pk, "50.10", ""),
                                    ("personal", "", "10.00", "")], **{"splits-INITIAL_FORMS": 2}))
        self.assertEqual(response.status_code, 302)
        receipt.refresh_from_db()
        self.assertEqual(receipt.vendor_id, self.vendor.pk)
        self.assertEqual(receipt.amount, Decimal("60.10"))
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertFalse(JournalEntry.objects.exists())

    def test_all_personal_and_single_line_splits_rejected(self):
        self.assert_rejected(self.values([("personal", "", "40.10", ""),
                                          ("personal", "", "20.00", "")]))
        self.assert_rejected(self.values([("business", self.cost.pk, "60.10", "")]))
