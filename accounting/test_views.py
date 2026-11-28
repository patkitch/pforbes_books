from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account


class ChartOfAccountsScreenTests(TestCase):
    def setUp(self):
        self.url = reverse("accounting:chart_of_accounts")
        self.user = get_user_model().objects.create_user(username="account_test", password="test-password", is_staff=True)
        self.client.force_login(self.user)
        self.parent = Account.objects.create(number="6100", name="Supplies", account_type="expense")
        self.child = Account.objects.create(number="6110", name="Paint", account_type="expense", parent=self.parent)
        self.inactive = Account.objects.create(number="6200", name="Inactive Services", account_type="expense", is_active=False)

    def test_only_active_accounts_shown_by_default(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Supplies")
        self.assertContains(response, "Paint")
        self.assertNotContains(response, "Inactive Services")

    def test_inactive_option_and_search(self):
        response = self.client.get(self.url, {"inactive": "1", "q": "6200"})
        self.assertContains(response, "Inactive Services")
        self.assertNotContains(response, "Supplies")

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_create_account(self):
        response = self.client.post(reverse("accounting:account_new"), {
            "number": "6120", "name": "Canvas", "account_type": "expense",
            "detail_type": "", "parent": str(self.parent.pk), "memo": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Account.objects.filter(number="6120", parent=self.parent).exists())

    def test_reject_wrong_number_range(self):
        response = self.client.post(reverse("accounting:account_new"), {
            "number": "1120", "name": "Canvas", "account_type": "expense",
            "detail_type": "", "parent": "", "memo": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not match")
        self.assertFalse(Account.objects.filter(number="1120").exists())

    def test_deactivate_and_reactivate(self):
        url = reverse("accounting:account_status", args=[self.child.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.child.refresh_from_db()
        self.assertFalse(self.child.is_active)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.child.refresh_from_db()
        self.assertTrue(self.child.is_active)

    def test_cannot_deactivate_parent_with_active_children(self):
        response = self.client.post(reverse("accounting:account_status", args=[self.parent.pk]))
        self.assertEqual(response.status_code, 400)
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.is_active)

    def test_status_change_requires_post(self):
        response = self.client.get(reverse("accounting:account_status", args=[self.child.pk]))
        self.assertEqual(response.status_code, 403)

    def test_non_staff_cannot_edit(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        response = self.client.get(reverse("accounting:account_new"))
        self.assertEqual(response.status_code, 302)
