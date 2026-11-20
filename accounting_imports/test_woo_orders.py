from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
import json

from accounting.models import JournalEntry
from accounting_contacts.models import Customer, Receipt, ReceiptItem
from .models import WooOrderImport
from .woo_orders import stage_orders, create_reviewed_receipt
from django.core.exceptions import ValidationError


def example(order_id=101, status="processing", customer_id=55):
    return {
        "id": order_id, "status": status, "customer_id": customer_id,
        "date_created": "2027-02-01T10:15:00",
        "date_paid": "2027-02-01T10:16:00",
        "total": "126.00", "total_tax": "9.00", "shipping_total": "7.00",
        "payment_method": "stripe", "transaction_id": "pi_example",
        "billing": {"first_name": "Jane", "last_name": "Collector", "email": "jane@example.com"},
        "shipping": {},
        "line_items": [{"name": "Prairie Painting", "quantity": 1, "total": "110.00"}],
    }


class WooOrderReviewTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="woo_staff", password="test", is_staff=True,
        )
        self.client.force_login(self.staff)

    def test_stages_without_creating_receipts_or_ledger_entries(self):
        self.assertEqual(stage_orders([example()]), (1, 0))
        self.assertEqual(stage_orders([example()]), (0, 1))
        self.assertEqual(WooOrderImport.objects.count(), 1)
        self.assertFalse(Receipt.objects.exists())
        self.assertFalse(JournalEntry.objects.exists())

    def test_review_creates_receipt_once_and_itemizes(self):
        stage_orders([example()])
        staged = WooOrderImport.objects.get()
        receipt, created = create_reviewed_receipt(staged)
        self.assertTrue(created)
        self.assertEqual(receipt.amount, Decimal("126.00"))
        self.assertEqual(receipt.items.count(), 1)
        self.assertEqual(receipt.items.first().artwork_title, "Prairie Painting")
        self.assertEqual(Customer.objects.count(), 1)
        self.assertFalse(JournalEntry.objects.exists())
        with self.assertRaises(ValidationError):
            create_reviewed_receipt(staged)
        self.assertEqual(Receipt.objects.count(), 1)

    def test_on_hold_cannot_be_receipted(self):
        stage_orders([example(status="on-hold")])
        with self.assertRaises(ValidationError):
            create_reviewed_receipt(WooOrderImport.objects.get())
        self.assertFalse(Receipt.objects.exists())

    def test_invalid_order_fails_without_partial_staging(self):
        bad = example(order_id=103)
        bad["total"] = "invalid"
        with self.assertRaises(ValidationError):
            stage_orders([example(), bad])
        self.assertFalse(WooOrderImport.objects.exists())

    def test_page_upload_exclude_restore_and_receipt(self):
        response = self.client.post(reverse("accounting:woo_inbox"), {
            "file": SimpleUploadedFile("orders.json", json.dumps([example()]).encode(), content_type="application/json")
        })
        self.assertEqual(response.status_code, 200)
        row = WooOrderImport.objects.get()
        url = reverse("accounting:woo_action", args=[row.pk])
        self.assertEqual(self.client.post(url, {"action": "exclude"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"action": "restore"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"action": "receipt"}).status_code, 302)
        self.assertEqual(Receipt.objects.count(), 1)
        self.assertFalse(JournalEntry.objects.exists())

    def test_access_restricted(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounting:woo_inbox")).status_code, 302)
