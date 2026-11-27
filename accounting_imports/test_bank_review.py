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


class BankReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="reviewtester", is_staff=True)
        self.client.force_login(self.user)
        self.card = Account.objects.create(number="2004", name="Credit card", account_type="liability")
        self.cost = Account.objects.create(number="5004", name="Materials", account_type="cogs")
        self.income = Account.objects.create(number="4001", name="Sales", account_type="income")
        batch, _, _ = stage_rows(self.card, "test.csv", [
            {"date": date(2026, 11, day), "description": "Print shop", "amount": Decimal("-20.00")}
            for day in (17, 18)], self.user)
        self.row, self.next_row = list(batch.rows.order_by("pk"))
        self.url = reverse("accounting:bank_review", args=[self.row.pk])
        self.vendor = Vendor.objects.create(name="Print shop")
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        settings = override_settings(MEDIA_ROOT=temp.name, STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        })
        settings.enable()
        self.addCleanup(settings.disable)

    def values(self, **overrides):
        return dict({"classification": "expense", "vendor": self.vendor.pk,
                     "category": self.cost.pk, "memo": "Print fulfillment"}, **overrides)

    def test_save_review_and_reload_original_preserved(self):
        self.assertEqual(self.client.post(self.url, self.values()).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.REVIEWED)
        self.assertEqual(self.row.description, "Print shop")
        self.assertEqual(self.row.amount, Decimal("-20.00"))
        self.assertEqual(self.row.review_data["vendor"], self.vendor.pk)
        self.assertEqual(self.row.review_data["category"], self.cost.pk)
        form = self.client.get(self.url).context["form"]
        self.assertEqual(form.initial["memo"], "Print fulfillment")
        self.assertFalse(JournalEntry.objects.exists())

    def test_create_vendor_and_reject_duplicate_name(self):
        self.client.post(self.url, self.values(vendor="", new_vendor="New printer"))
        vendor = Vendor.objects.get(name="New printer")
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_data["vendor"], vendor.pk)
        response = self.client.post(self.url, self.values(vendor="", new_vendor="new PRINTER"))
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Vendor.objects.filter(name__iexact="new printer").count(), 1)

    def test_remember_exact_description_not_memo(self):
        self.client.post(self.url, self.values(remember="on"))
        response = self.client.get(reverse("accounting:bank_review", args=[self.next_row.pk]))
        form = response.context["form"]
        self.assertEqual(form.initial["vendor"], self.vendor.pk)
        self.assertEqual(form.initial["category"], self.cost.pk)
        self.assertFalse(form.initial.get("memo"))
        self.next_row.refresh_from_db()
        self.assertEqual(self.next_row.status, ImportRow.PENDING)

    def test_wrong_category_rejected(self):
        response = self.client.post(self.url, self.values(category=self.income.pk))
        self.assertTrue(response.context["form"].errors)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.PENDING)

    def test_personal_review_does_not_post(self):
        self.client.post(self.url, {"classification": "personal"})
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.EXCLUDED)
        self.assertFalse(JournalEntry.objects.exists())

    def test_upload_download_and_deduplicate_document(self):
        payload = b"%PDF-1.4\nSynthetic test document\n%%EOF"
        for name in ("invoice.pdf", "copy.pdf"):
            response = self.client.post(self.url, self.values(
                attachment=SimpleUploadedFile(name, payload, content_type="application/pdf")))
            self.assertEqual(response.status_code, 302)
        receipt = Receipt.objects.get(source="bank_document")
        self.assertEqual(receipt.vendor_id, self.vendor.pk)
        self.assertEqual(receipt.amount, Decimal("20.00"))
        self.assertEqual(receipt.date, self.row.transaction_date)
        self.assertTrue(receipt.source_reference.startswith(f"{self.row.pk}:"))
        response = self.client.get(reverse("accounting:receipt_download", args=[receipt.pk]))
        self.assertEqual(b"".join(response.streaming_content), payload)
        response.close()
        self.assertFalse(JournalEntry.objects.exists())
        self.assertContains(self.client.get(self.url), "invoice.pdf")
        self.assertNotContains(self.client.get(reverse("accounting:bank_review", args=[self.next_row.pk])), "invoice.pdf")

    def test_invalid_document_rejected(self):
        response = self.client.post(self.url, self.values(
            attachment=SimpleUploadedFile("fake.pdf", b"not a pdf")))
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Receipt.objects.exists())
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.PENDING)

    def test_nonstaff_cannot_review(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.values()).status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, ImportRow.PENDING)
