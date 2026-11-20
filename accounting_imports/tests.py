from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounting.models import Account, JournalEntry
from .models import ImportBatch, ImportRow


class InboxTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="inbox", password="testing", is_staff=True,
        )
        self.client.force_login(self.user)
        self.account = Account.objects.create(
            number="2003", name="Credit card", account_type="liability",
        )

    def upload(self, data):
        return self.client.post(reverse("accounting:import_inbox"), {
            "account": str(self.account.pk),
            "file": SimpleUploadedFile("statement.csv", data, content_type="text/csv"),
        })

    def test_import_stages_without_posting_and_repeat_skips(self):
        data = b"Date,Description,Amount\n2026-10-04,MPix,-45.50\n2026-10-05,Payment,45.50\n"
        self.assertEqual(self.upload(data).status_code, 200)
        self.assertEqual(ImportRow.objects.count(), 2)
        self.assertTrue(all(x.status == "pending" for x in ImportRow.objects.all()))
        self.assertFalse(JournalEntry.objects.exists())
        response = self.upload(data)
        self.assertContains(response, "2 already imported rows skipped")
        self.assertEqual(ImportRow.objects.count(), 2)
        self.assertEqual(ImportBatch.objects.count(), 2)
        self.assertFalse(JournalEntry.objects.exists())

    def test_duplicate_identical_lines_in_same_file_preserved_once(self):
        data = b"Date,Description,Amount\n2026-10-04,Coffee,-5.00\n2026-10-04,Coffee,-5.00\n"
        self.upload(data)
        self.assertEqual(ImportRow.objects.count(), 2)
        self.upload(data)
        self.assertEqual(ImportRow.objects.count(), 2)

    def test_exclude_and_restore_are_not_ledger_entries(self):
        self.upload(b"Date,Description,Amount\n2026-10-04,Groceries,-50.00\n")
        row = ImportRow.objects.get()
        url = reverse("accounting:import_status", args=[row.pk])
        self.assertEqual(self.client.post(url, {"status": "excluded"}).status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, "excluded")
        self.client.post(url, {"status": "pending"})
        row.refresh_from_db()
        self.assertEqual(row.status, "pending")
        self.assertFalse(JournalEntry.objects.exists())

    def test_rejects_bad_csv_without_staging(self):
        self.upload(b"Date,Description,Amount\n2026-10-04,MPix,NaN\n")
        self.assertFalse(ImportRow.objects.exists())
        self.assertFalse(ImportBatch.objects.exists())

    def test_requires_staff_and_post_for_status_changes(self):
        self.upload(b"Date,Description,Amount\n2026-10-04,MPix,-10.00\n")
        row = ImportRow.objects.get()
        self.assertEqual(self.client.get(reverse("accounting:import_status", args=[row.pk])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounting:import_inbox")).status_code, 302)
        self.assertEqual(self.client.post(reverse("accounting:import_status", args=[row.pk]), {"status": "excluded"}).status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, "pending")
