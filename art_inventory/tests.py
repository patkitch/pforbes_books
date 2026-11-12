from django.test import TestCase
from django.core.exceptions import ValidationError
from .models import Artwork,InventoryActivity,Location,Original,PrintOption,PrintStock
from .services import record_activity

class InventoryTests(TestCase):
    def setUp(self):
        self.home=Location.objects.get(name="Home"); self.gallery=Location.objects.get(name="Images Art Gallery")
        self.art=Artwork.objects.create(title="Sample"); self.original=Original.objects.create(artwork=self.art,location=self.home)
        self.print=PrintOption.objects.create(artwork=self.art,print_type="matted_8x10_4x6")
    def test_transfer_and_sale_counts(self):
        record_activity(kind="purchase",quantity=5,print_option_id=self.print.pk,to_location_id=self.home.pk)
        record_activity(kind="transfer",quantity=2,print_option_id=self.print.pk,from_location_id=self.home.pk,to_location_id=self.gallery.pk)
        record_activity(kind="local_sale",quantity=1,print_option_id=self.print.pk,from_location_id=self.gallery.pk)
        self.assertEqual(PrintStock.objects.get(print_option=self.print,location=self.home).quantity,3)
        self.assertEqual(PrintStock.objects.get(print_option=self.print,location=self.gallery).quantity,1)
    def test_made_to_order_leaves_stock_unchanged(self):
        record_activity(kind="made_to_order",quantity=1,print_option_id=self.print.pk)
        self.assertFalse(PrintStock.objects.exists())
    def test_oversell_rejected(self):
        with self.assertRaises(ValidationError): record_activity(kind="local_sale",quantity=1,print_option_id=self.print.pk,from_location_id=self.gallery.pk)
    def test_original_sale(self):
        record_activity(kind="original_sale",quantity=1,original_id=self.original.pk,from_location_id=self.home.pk)
        self.original.refresh_from_db(); self.assertEqual(self.original.status,"sold"); self.assertEqual(self.original.on_hand,0)
