from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.models import JournalEntry
from .models import Customer, Receipt
from .woo_receipts import stage_woo_order_receipt


class WooReceiptPreparationTests(TestCase):
    def order(self, order_id=100, customer_id=77, **overrides):
        order = {
            "id": order_id, "customer_id": customer_id,
            "date_created": "2027-02-04T15:20:00",
            "total": "250.00",
            "billing": {
                "first_name": "Jane", "last_name": "Collector",
                "email": "jane@example.com", "phone": "555-0100",
                "address_1": "123 Street", "city": "Overland Park",
            },
            "shipping": {"address_1": "123 Street", "city": "Overland Park"},
        }
        order.update(overrides)
        return order

    def test_registered_customer_created_once_for_multiple_orders(self):
        customer, receipt, created = stage_woo_order_receipt(self.order())
        self.assertTrue(created)
        self.assertEqual(customer.woo_customer_id, 77)
        self.assertEqual(receipt.amount, Decimal("250.00"))
        self.assertEqual(receipt.customer_id, customer.pk)
        self.assertEqual(receipt.source_reference, "order:100")
        same_customer, same_receipt, created = stage_woo_order_receipt(self.order())
        self.assertFalse(created)
        self.assertEqual(same_customer.pk, customer.pk)
        self.assertEqual(same_receipt.pk, receipt.pk)
        other_customer, second_receipt, created = stage_woo_order_receipt(self.order(order_id=101))
        self.assertTrue(created)
        self.assertEqual(other_customer.pk, customer.pk)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Receipt.objects.count(), 2)
        self.assertFalse(JournalEntry.objects.exists())

    def test_guest_orders_do_not_merge_by_name_or_email(self):
        first_customer, _, _ = stage_woo_order_receipt(self.order(customer_id=0))
        second_customer, _, _ = stage_woo_order_receipt(self.order(order_id=102, customer_id=0))
        self.assertNotEqual(first_customer.pk, second_customer.pk)
        self.assertIsNone(first_customer.woo_customer_id)
        self.assertEqual(Customer.objects.count(), 2)

    def test_invalid_order_never_creates_records(self):
        with self.assertRaises(ValidationError):
            stage_woo_order_receipt(self.order(order_id=-1))
        with self.assertRaises(ValidationError):
            stage_woo_order_receipt(self.order(total="-20.00"))
        with self.assertRaises(ValidationError):
            stage_woo_order_receipt(self.order(total="oops"))
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Receipt.objects.count(), 0)

    def test_duplicate_order_does_not_overwrite_original_customer(self):
        first_customer, first_receipt, _ = stage_woo_order_receipt(self.order())
        changed = self.order(
            billing={"first_name": "Different", "last_name": "Person", "email": "other@example.com"}
        )
        same_customer, same_receipt, created = stage_woo_order_receipt(changed)
        self.assertFalse(created)
        self.assertEqual(same_customer.pk, first_customer.pk)
        self.assertEqual(same_receipt.pk, first_receipt.pk)
        self.assertEqual(Customer.objects.count(), 1)
