from datetime import date
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.models import Account, JournalEntry, JournalLine
from .models import Customer, Receipt, ReceiptItem, TransactionParty, Vendor


class ContactsAndReceiptsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="contacts_test", password="pass", is_staff=True
        )
        self.client.force_login(self.user)
        self.vendor = Vendor.objects.create(name="MPix", email="print@example.com")
        self.customer = Customer.objects.create(name="Jane Collector", email="jane@example.com")
        self.bank = Account.objects.create(number="1001", name="Checking", account_type="asset")
        self.expense = Account.objects.create(number="5004", name="Prints", account_type="cogs")
        self.entry = JournalEntry.objects.create(
            date=date(2027, 1, 5), description="Print restock", status="posted",
            payee="MPix"
        )
        JournalLine.objects.create(entry=self.entry, account=self.expense, debit=Decimal("45.50"))
        JournalLine.objects.create(entry=self.entry, account=self.bank, credit=Decimal("45.50"))

    def test_vendor_directory_create_edit_and_search(self):
        response = self.client.get(reverse("accounting:vendors"))
        self.assertContains(response, "MPix")
        response = self.client.get(reverse("accounting:vendors"), {"q": "no match"})
        self.assertNotContains(response, "MPix")
        response = self.client.post(reverse("accounting:vendor_new"), {
            "name": "Local Gallery", "email": "gallery@example.com",
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        added = Vendor.objects.get(name="Local Gallery")
        self.assertEqual(added.email, "gallery@example.com")
        self.assertContains(self.client.get(reverse("accounting:vendor_detail", args=[added.pk])), "Local Gallery")

    def test_customer_create_and_details(self):
        response = self.client.post(reverse("accounting:customer_new"), {
            "name": "Collective Studio", "kind": "organization",
            "email": "sales@studio.example", "is_active": "on"
        })
        self.assertEqual(response.status_code, 302)
        contact = Customer.objects.get(name="Collective Studio")
        self.assertEqual(contact.kind, "organization")
        self.assertContains(self.client.get(reverse("accounting:customers")), "Collective Studio")

    def test_link_existing_posted_transaction_to_vendor_without_affecting_ledger(self):
        url = reverse("accounting:transaction_party", args=[self.entry.pk])
        response = self.client.post(url, {
            "party_type": "vendor", "vendor": str(self.vendor.pk),
            "customer": "",
        })
        self.assertRedirects(response, reverse("accounting:transaction_list"))
        link = TransactionParty.objects.get(journal_entry_id=self.entry.pk)
        self.assertEqual(link.vendor, self.vendor)
        self.assertEqual(self.entry.audit_events.filter(action="contact_linked").count(), 1)
        self.assertEqual(JournalLine.objects.filter(entry=self.entry).count(), 2)
        self.assertEqual(JournalLine.objects.get(entry=self.entry, account=self.expense).debit, Decimal("45.50"))
        self.assertContains(self.client.get(reverse("accounting:vendor_detail", args=[self.vendor.pk])), "Print restock")

    def test_contact_link_can_be_changed_with_audit(self):
        url = reverse("accounting:transaction_party", args=[self.entry.pk])
        self.client.post(url, {"party_type": "vendor", "vendor": str(self.vendor.pk)})
        response = self.client.post(url, {"party_type": "customer", "customer": str(self.customer.pk)})
        self.assertEqual(response.status_code, 302)
        link = TransactionParty.objects.get(journal_entry_id=self.entry.pk)
        self.assertIsNone(link.vendor)
        self.assertEqual(link.customer, self.customer)
        self.assertEqual(self.entry.audit_events.filter(action="contact_linked").count(), 2)

    def test_manual_purchase_selects_vendor_as_it_posts(self):
        response = self.client.post(reverse("accounting:transaction_new"), {
            "kind": "expense", "date": "2027-01-12", "payee": "MPix",
            "description": "New print order", "amount": "25.00",
            "category_account": str(self.expense.pk),
            "payment_account": str(self.bank.pk),
            "vendor": str(self.vendor.pk),
            "save_action": "post",
        })
        self.assertEqual(response.status_code, 302)
        entry = JournalEntry.objects.get(description="New print order")
        party = TransactionParty.objects.get(journal_entry_id=entry.pk)
        self.assertEqual(party.vendor_id, self.vendor.pk)
        self.assertEqual(entry.status, "posted")

    def test_manual_income_selects_customer_as_it_posts(self):
        sales = Account.objects.create(number="4001", name="Artwork", account_type="income")
        response = self.client.post(reverse("accounting:transaction_new"), {
            "kind": "income", "date": "2027-01-12", "payee": "Jane Collector",
            "description": "Original sold", "amount": "250.00",
            "category_account": str(sales.pk),
            "payment_account": str(self.bank.pk),
            "customer": str(self.customer.pk),
            "save_action": "post",
        })
        self.assertEqual(response.status_code, 302)
        entry = JournalEntry.objects.get(description="Original sold")
        party = TransactionParty.objects.get(journal_entry_id=entry.pk)
        self.assertEqual(party.customer_id, self.customer.pk)
        self.assertEqual(entry.status, "posted")
        response = self.client.get(reverse("accounting:customer_detail", args=[self.customer.pk]))
        self.assertContains(response, "Original sold")
        self.assertContains(response, "250.00")

    def test_wrong_contact_type_is_rejected_for_sales(self):
        sales = Account.objects.create(number="4001", name="Artwork", account_type="income")
        response = self.client.post(reverse("accounting:transaction_new"), {
            "kind": "income", "date": "2027-01-12", "description": "Wrong contact",
            "amount": "75.00", "category_account": str(sales.pk),
            "payment_account": str(self.bank.pk),
            "vendor": str(self.vendor.pk), "save_action": "post",
        })
        self.assertContains(response, "Choose a vendor for purchases")
        self.assertFalse(JournalEntry.objects.filter(description="Wrong contact").exists())

    def test_invalid_contact_combination_rejected(self):
        response = self.client.post(
            reverse("accounting:transaction_party", args=[self.entry.pk]),
            {"party_type": "vendor", "customer": str(self.customer.pk)}
        )
        self.assertContains(response, "Choose a vendor")
        self.assertFalse(TransactionParty.objects.exists())

    def test_purchase_receipt_linked_to_vendor_and_transaction(self):
        response = self.client.post(reverse("accounting:receipt_new"), {
            "title": "MPix January", "receipt_type": "purchase", "date": "2027-01-05",
            "amount": "45.50", "vendor": str(self.vendor.pk),
            "journal_entry_id": str(self.entry.pk),
        })
        self.assertEqual(response.status_code, 302)
        receipt = Receipt.objects.get(title="MPix January")
        self.assertEqual(receipt.vendor, self.vendor)
        self.assertEqual(receipt.journal_entry_id, self.entry.pk)
        self.assertContains(self.client.get(reverse("accounting:receipts")), "MPix January")
        self.assertContains(self.client.get(reverse("accounting:receipt_detail", args=[receipt.pk])), "MPix")

    def test_receipt_auto_links_vendor_to_existing_journal(self):
        response = self.client.post(reverse("accounting:receipt_new"), {
            "title": "MPix receipt", "receipt_type": "purchase",
            "date": "2027-01-05", "amount": "45.50",
            "vendor": str(self.vendor.pk), "journal_entry_id": str(self.entry.pk),
        })
        self.assertEqual(response.status_code, 302)
        link = TransactionParty.objects.get(journal_entry_id=self.entry.pk)
        self.assertEqual(link.vendor_id, self.vendor.pk)
        self.assertEqual(self.entry.audit_events.filter(action="contact_linked").count(), 1)

    def test_receipt_does_not_silently_replace_existing_contact(self):
        other = Vendor.objects.create(name="Another vendor")
        TransactionParty.objects.create(journal_entry_id=self.entry.pk, vendor=other)
        response = self.client.post(reverse("accounting:receipt_new"), {
            "title": "Conflicting receipt", "receipt_type": "purchase",
            "date": "2027-01-05", "amount": "45.50",
            "vendor": str(self.vendor.pk), "journal_entry_id": str(self.entry.pk),
        })
        self.assertContains(response, "already linked to a different contact")
        self.assertFalse(Receipt.objects.filter(title="Conflicting receipt").exists())
        self.assertEqual(TransactionParty.objects.get(journal_entry_id=self.entry.pk).vendor_id, other.pk)

    def test_receipt_rejects_nonexistent_journal(self):
        response = self.client.post(reverse("accounting:receipt_new"), {
            "title": "Invalid", "receipt_type": "purchase", "date": "2027-01-05",
            "amount": "10.00", "vendor": str(self.vendor.pk),
            "journal_entry_id": "9999999",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Receipt.objects.exists())

    def test_receipt_cannot_assign_customer_to_purchase(self):
        response = self.client.post(reverse("accounting:receipt_new"), {
            "title": "Invalid receipt", "receipt_type": "purchase",
            "date": "2027-01-05", "amount": "10.00",
            "customer": str(self.customer.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Receipt.objects.exists())

    def test_file_validation_blocks_disguised_content(self):
        with TemporaryDirectory() as folder:
            with override_settings(MEDIA_ROOT=folder):
                response = self.client.post(reverse("accounting:receipt_new"), {
                    "title": "Invalid PDF", "receipt_type": "purchase", "date": "2027-01-05",
                    "amount": "45.50", "vendor": str(self.vendor.pk),
                    "attachment": SimpleUploadedFile("bad.pdf", b"not actually a PDF"),
                })
                self.assertContains(response, "contents do not match")
                self.assertFalse(Receipt.objects.exists())

    def test_attached_pdf_is_staff_only(self):
        with TemporaryDirectory() as folder:
            with override_settings(MEDIA_ROOT=folder):
                response = self.client.post(reverse("accounting:receipt_new"), {
                    "title": "Original PDF", "receipt_type": "purchase", "date": "2027-01-05",
                    "amount": "45.50", "vendor": str(self.vendor.pk),
                    "attachment": SimpleUploadedFile(
                        "original.pdf", b"%PDF-1.4\nPDF test receipt", content_type="application/pdf"
                    ),
                })
                self.assertEqual(response.status_code, 302)
                receipt = Receipt.objects.get()
                url = reverse("accounting:receipt_download", args=[receipt.pk])
                result = self.client.get(url)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(b"".join(result.streaming_content), b"%PDF-1.4\nPDF test receipt")
                result.close()
                self.client.logout()
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_reversal_inherits_original_vendor_and_nets_spending_to_zero(self):
        from .services import link_contact
        link_contact(self.entry, vendor=self.vendor, actor=self.user)
        result = self.client.post(
            reverse("accounting:transaction_reverse", args=[self.entry.pk]),
            {"date": "2027-01-06", "reason": "Duplicate purchase"},
        )
        self.assertEqual(result.status_code, 302)
        self.entry.refresh_from_db()
        reversal = self.entry.reversed_by_entry
        self.assertIsNotNone(reversal)
        self.assertEqual(reversal.status, "posted")
        self.assertEqual(
            TransactionParty.objects.get(journal_entry_id=reversal.pk).vendor_id,
            self.vendor.pk,
        )
        detail = self.client.get(reverse("accounting:vendor_detail", args=[self.vendor.pk]))
        self.assertContains(detail, "0.00")
        self.assertContains(detail, reversal.description)

    def test_artwork_items_save_and_show_in_customer_history(self):
        payload = {
            "title": "Gallery painting sale", "receipt_type": "sale",
            "date": "2027-01-05", "amount": "275.00",
            "customer": str(self.customer.pk),
            "items-TOTAL_FORMS": "3", "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "12",
            "items-0-artwork_title": "Prairie Sky",
            "items-0-item_type": "original", "items-0-size": "16x20",
            "items-0-quantity": "1", "items-0-unit_price": "250.00",
        }
        result = self.client.post(reverse("accounting:receipt_new"), payload)
        self.assertEqual(result.status_code, 302)
        receipt = Receipt.objects.get(title="Gallery painting sale")
        item = receipt.items.get()
        self.assertEqual(item.artwork_title, "Prairie Sky")
        self.assertEqual(item.line_total, Decimal("250.00"))
        self.assertContains(
            self.client.get(reverse("accounting:customer_detail", args=[self.customer.pk])),
            "Prairie Sky",
        )
        self.assertContains(
            self.client.get(reverse("accounting:receipt_detail", args=[receipt.pk])),
            "16x20",
        )
        self.assertEqual(JournalEntry.objects.count(), 1)

        payload.update({
            "items-0-artwork_title": "Prairie Sky Revisited",
            "items-0-unit_price": "260.00",
        })
        changed = self.client.post(reverse("accounting:receipt_edit", args=[receipt.pk]), payload)
        self.assertEqual(changed.status_code, 302)
        self.assertEqual(receipt.items.count(), 1)
        self.assertEqual(receipt.items.get().artwork_title, "Prairie Sky Revisited")

    def test_invalid_item_subtotal_does_not_create_receipt(self):
        result = self.client.post(reverse("accounting:receipt_new"), {
            "title": "Wrong total", "receipt_type": "sale",
            "date": "2027-01-05", "amount": "10.00",
            "customer": str(self.customer.pk),
            "items-TOTAL_FORMS": "3", "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "12",
            "items-0-artwork_title": "Test painting",
            "items-0-item_type": "original", "items-0-quantity": "1",
            "items-0-unit_price": "50.00",
        })
        self.assertContains(result, "subtotal exceeds receipt amount")
        self.assertFalse(Receipt.objects.exists())
        self.assertFalse(ReceiptItem.objects.exists())

    def test_purchase_receipt_rejects_artwork_sale_items(self):
        result = self.client.post(reverse("accounting:receipt_new"), {
            "title": "Wrong kind", "receipt_type": "purchase",
            "date": "2027-01-05", "amount": "50.00",
            "vendor": str(self.vendor.pk),
            "items-TOTAL_FORMS": "3", "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "12",
            "items-0-artwork_title": "Original",
            "items-0-item_type": "original", "items-0-quantity": "1",
            "items-0-unit_price": "50.00",
        })
        self.assertContains(result, "Artwork line items belong on sales receipts only")
        self.assertFalse(Receipt.objects.exists())

    def test_duplicate_manual_receipt_is_blocked_but_edit_is_allowed(self):
        payload = {
            "title": "Original Receipt", "receipt_type": "purchase",
            "date": "2027-01-05", "amount": "45.50",
            "vendor": str(self.vendor.pk),
        }
        self.assertEqual(self.client.post(reverse("accounting:receipt_new"), payload).status_code, 302)
        repeat = self.client.post(reverse("accounting:receipt_new"), payload)
        self.assertContains(repeat, "identical manual receipt already exists")
        self.assertEqual(Receipt.objects.count(), 1)
        receipt = Receipt.objects.get()
        self.assertEqual(
            self.client.post(reverse("accounting:receipt_edit", args=[receipt.pk]), payload).status_code,
            302,
        )

    def test_jpeg_and_png_document_uploads_are_accepted(self):
        for name, prefix in (
            ("sample.jpg", bytes.fromhex("ffd8ffe000104a46494600")),
            ("sample.png", bytes.fromhex("89504e470d0a1a0a0000")),
        ):
            with self.subTest(filename=name), TemporaryDirectory() as folder:
                with override_settings(MEDIA_ROOT=folder):
                    response = self.client.post(reverse("accounting:receipt_new"), {
                        "title": f"Test file {name}", "receipt_type": "purchase",
                        "date": "2027-01-05", "amount": "45.50",
                        "vendor": str(self.vendor.pk),
                        "attachment": SimpleUploadedFile(name, prefix + b"test"),
                    })
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(Receipt.objects.get(title=f"Test file {name}").attachment)

    def test_contact_modules_staff_only(self):
        self.client.logout()
        for path in (
            reverse("accounting:vendors"), reverse("accounting:customers"),
            reverse("accounting:receipts"),
            reverse("accounting:transaction_party", args=[self.entry.pk]),
        ):
            self.assertEqual(self.client.get(path).status_code, 302)
