from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account


class ChartOfAccountsScreenTests(TestCase):
    def setUp(self):
        self.url = reverse("accounting:chart_of_accounts")
        self.user = get_user_model().objects.create_user(username="account_test", password="test-password")
        self.client.force_login(self.user)
        Account.objects.create(number="6100", name="Supplies", account_type="expense")
        Account.objects.create(number="6200", name="Inactive Services", account_type="expense", is_active=False)

    def test_only_active_accounts_shown_by_default(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Supplies")
        self.assertNotContains(response, "Inactive Services")

    def test_inactive_option_and_search(self):
        response = self.client.get(self.url, {"inactive": "1", "q": "6200"})
        self.assertContains(response, "Inactive Services")
        self.assertNotContains(response, "Supplies")

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
