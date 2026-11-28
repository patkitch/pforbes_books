from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import BusinessProfile


class BusinessProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="profileadmin", password="testpass", is_staff=True,
        )
        self.client.force_login(self.user)
        self.url = reverse("accounting:business_profile")

    def payload(self):
        return {
            "display_name": "P. Forbes Art",
            "legal_name": "P. Forbes Art",
            "entity_type": "sole",
            "tax_id_type": "ssn",
            "tax_id_last_four": "1234",
            "country": "United States",
            "industry": "Independent artist",
        }

    def test_profile_create_and_update_single_record(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        self.assertEqual(BusinessProfile.objects.count(), 1)
        data = self.payload()
        data["display_name"] = "P. Forbes Art Studio"
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(BusinessProfile.objects.count(), 1)
        self.assertEqual(BusinessProfile.objects.get().display_name, "P. Forbes Art Studio")

    def test_rejects_full_tax_id_and_does_not_save(self):
        data = self.payload()
        data["tax_id_last_four"] = "123456789"
        self.assertEqual(self.client.post(self.url, data).status_code, 200)
        self.assertFalse(BusinessProfile.objects.exists())

    def test_requires_staff_and_does_not_expose_profile(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        regular = get_user_model().objects.create_user(username="regular", password="test")
        self.client.force_login(regular)
        self.assertEqual(self.client.get(self.url).status_code, 302)
