from datetime import date
from decimal import Decimal
from django.test import TestCase
from accounting.models import Account, JournalEntry
from accounting_contacts.models import Vendor
from .models import ImportRow
from .views import stage_rows
from .merchant_recognition import merchant_key, suggest


class MerchantRecognitionTests(TestCase):
    def setUp(self):
        self.card = Account.objects.create(number="2004", name="Visa", account_type="liability")
        self.other = Account.objects.create(number="2003", name="Other Visa", account_type="liability")
        self.cost = Account.objects.create(number="5004", name="Materials", account_type="cogs")
        self.expense = Account.objects.create(number="6001", name="Office supplies", account_type="expense")
        self.vendor = Vendor.objects.create(name="Amazon")
        self.old = self.row("AMAZON MKTPL*ABC123")
        self.new = self.row("Amazon Mktpl*DEF456", self.other)
        self.old.status = ImportRow.REVIEWED
        self.old.review_data = {"classification": "expense", "vendor": self.vendor.pk,
                                "category": self.cost.pk, "remember": False}
        self.old.save()

    def row(self, description, account=None, amount="-20.00"):
        batch, _, _ = stage_rows(account or self.card, "test.csv", [
            {"date": date(2026, 11, 18), "description": description, "amount": Decimal(amount)}
        ])
        return batch.rows.get()

    def test_vendor_without_category_consent(self):
        initial, message = suggest(self.new)
        self.assertEqual(initial, {"vendor": self.vendor.pk})
        self.assertIn("no category was assumed", message)
        self.new.refresh_from_db()
        self.assertEqual(self.new.status, ImportRow.PENDING)
        self.assertFalse(self.new.review_data)
        self.assertFalse(JournalEntry.objects.exists())

    def test_explicit_merchant_category_consent(self):
        self.old.review_data.update(remember=True, remember_scope="merchant")
        self.old.save()
        self.assertEqual(suggest(self.new)[0], {"vendor": self.vendor.pk,
            "classification": "expense", "category": self.cost.pk})

    def test_legacy_permission_does_not_expand(self):
        self.old.review_data["remember"] = True
        self.old.save()
        self.assertEqual(suggest(self.new)[0], {"vendor": self.vendor.pk})

    def test_conflicting_categories_suppress_category(self):
        self.old.review_data.update(remember=True, remember_scope="merchant")
        self.old.save()
        conflicting = self.row("AMAZON MKTPL*OTHER")
        conflicting.status = ImportRow.REVIEWED
        conflicting.review_data = {"classification": "expense", "vendor": self.vendor.pk,
                                   "category": self.expense.pk}
        conflicting.save()
        self.assertEqual(suggest(self.new)[0], {"vendor": self.vendor.pk})

    def test_conflicting_vendors_suppress_suggestions(self):
        conflicting = self.row("AMAZON MKTPL*OTHER")
        conflicting.status = ImportRow.REVIEWED
        conflicting.review_data = {"classification": "expense",
                                   "vendor": Vendor.objects.create(name="Other merchant").pk,
                                   "category": self.cost.pk}
        conflicting.save()
        self.assertEqual(suggest(self.new)[0], {})

    def test_inactive_vendor_not_suggested(self):
        self.vendor.is_active = False
        self.vendor.save()
        self.assertEqual(suggest(self.new)[0], {})

    def test_merchant_keys_keep_unrelated_services_separate(self):
        self.assertEqual(merchant_key("AMAZON MKTPL*123"), merchant_key("amazon mktpl*456"))
        self.assertNotEqual(merchant_key("Amazon Prime"), merchant_key("AMAZON MKTPL*123"))
        self.assertNotEqual(merchant_key("MPixies"), merchant_key("MPIX 123 KS"))

    def test_positive_amount_and_excluded_row_not_suggested(self):
        credit = self.row("AMAZON MKTPL*REFUND", amount="20.00")
        self.assertEqual(suggest(credit)[0], {})
        self.new.status = ImportRow.EXCLUDED
        self.new.save()
        self.assertEqual(suggest(self.new)[0], {})
