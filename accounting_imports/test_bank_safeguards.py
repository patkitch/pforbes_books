from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from accounting.import_preview import parse_csv_preview, eligible_import_accounts
from accounting.models import Account, JournalEntry
from .models import ImportBatch, ImportRow

# Synthetic fixtures only; no personal bank data.
CARD = b"Posted Date,Reference Number,Payee,Address,Amount\n11/18/2026,TEST123,Print shop,KS,-20.00\n11/18/2026,TEST123,Fee,KS,-2.00\n"
BANK = b"Description,,Summary Amt.\nBeginning balance as of 11/01/2026,,100.00\nTotal credits,,35.00\nTotal debits,,-18.00\nEnding balance as of 11/30/2026,,117.00\n\nDate,Description,Amount,Running Bal.\n11/01/2026,Beginning balance as of 11/01/2026,,100.00\n11/10/2026,Deposit Conf# ABC123,35.00,135.00\n11/20/2026,Purchase,-18.00,117.00\n"


class BankParserTests(SimpleTestCase):
    def test_card_preserves_reference_and_address(self):
        rows = parse_csv_preview(CARD)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["reference"], "TEST123")
        self.assertEqual(rows[0]["merchant_address"], "KS")
        self.assertEqual(rows[0]["amount"], Decimal("-20.00"))
        self.assertEqual(rows[0]["source_format"], "boa_card")

    def test_bank_totals_and_reference(self):
        rows = parse_csv_preview(BANK)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows.summary, {"beginning": "100.00", "credits": "35.00",
                                        "debits": "-18.00", "ending": "117.00"})
        self.assertEqual(rows[0]["reference"], "ABC123")
        self.assertEqual(rows[1]["running_balance"], "117.00")

    def test_invalid_summary_rejected(self):
        with self.assertRaisesRegex(ValueError, "summary does not balance"):
            parse_csv_preview(BANK.replace(b"117.00", b"118.00", 1))

    def test_invalid_running_balance_rejected(self):
        with self.assertRaisesRegex(ValueError, "running balance"):
            parse_csv_preview(BANK.replace(b"135.00", b"136.00"))

    def test_balanced_summary_but_wrong_totals_rejected(self):
        bad = BANK.replace(b"credits,,35.00", b"credits,,36.00").replace(b"debits,,-18.00", b"debits,,-19.00")
        with self.assertRaisesRegex(ValueError, "statement totals"):
            parse_csv_preview(bad)


class BankSafeguardTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="banktester", is_staff=True))
        self.checking = Account.objects.create(number="1002", name="Checking", account_type="asset", detail_type="Checking")
        self.savings = Account.objects.create(number="1003", name="Savings", account_type="asset", detail_type="Savings")
        self.card = Account.objects.create(number="2004", name="Visa (1111)", account_type="liability", detail_type="Credit Card")
        self.other_card = Account.objects.create(number="2003", name="Visa (2222)", account_type="liability", detail_type="Credit Card")

    def upload(self, account, data=CARD, name="currentTransaction_1111 (1).csv", endpoint="import_inbox"):
        return self.client.post(reverse("accounting:" + endpoint), {
            "account": account.pk, "file": SimpleUploadedFile(name, data),
        })

    def test_only_eligible_active_accounts(self):
        invalid = Account.objects.create(number="1005", name="Equipment", account_type="asset", detail_type="Fixed Assets")
        Account.objects.create(number="2005", name="Taxes payable", account_type="liability")
        Account.objects.create(number="1006", name="Old checking", account_type="asset", is_active=False)
        self.assertEqual(set(eligible_import_accounts()), {self.checking, self.savings, self.card, self.other_card})
        self.upload(invalid)
        self.assertFalse(ImportBatch.objects.exists())

    def test_card_into_bank_blocked(self):
        self.assertContains(self.upload(self.checking), "This is a credit card CSV")
        self.assertFalse(ImportBatch.objects.exists())

    def test_wrong_card_number_blocked(self):
        self.assertContains(self.upload(self.other_card), "selected account ends in 2222")
        self.assertFalse(ImportBatch.objects.exists())

    def test_bank_into_card_blocked(self):
        self.assertContains(self.upload(self.card, BANK, "stmt.csv"), "This is a bank statement CSV")
        self.assertFalse(ImportBatch.objects.exists())

    def test_card_same_reference_distinct_transactions_and_repeat(self):
        self.upload(self.card)
        self.assertEqual(ImportRow.objects.count(), 2)
        self.assertContains(self.upload(self.card), "2 already imported rows skipped")
        self.assertEqual(ImportRow.objects.count(), 2)
        self.assertFalse(JournalEntry.objects.exists())

    def test_cross_account_warning_does_not_discard(self):
        self.upload(self.savings, BANK, "stmt.csv")
        response = self.upload(self.checking, BANK, "stmt.csv")
        self.assertContains(response, "Possible cross-account duplicate")
        self.assertEqual(ImportRow.objects.count(), 4)
        self.assertFalse(JournalEntry.objects.exists())

    def test_preview_rejects_wrong_account_without_saving(self):
        response = self.upload(self.checking, endpoint="import_preview")
        self.assertIsNone(response.context["rows"])
        self.assertFalse(ImportBatch.objects.exists())

    def test_bad_statement_does_not_stage(self):
        self.upload(self.checking, BANK.replace(b"135.00", b"136.00"), "stmt.csv")
        self.assertFalse(ImportBatch.objects.exists())
        self.assertFalse(ImportRow.objects.exists())
