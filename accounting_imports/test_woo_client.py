"""Simulated API tests; never connect to the user's actual store."""
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import WooOrderImport
from .woo_client import WooConnectionError, fetch_recent_orders, fetch_and_stage, configured
from .test_woo_orders import example


ENV = {
    "PFORBooks_WOO_IMPORT_ENABLED": "1",
    "PFORBooks_WOO_STORE_URL": "https://example.org",
    "PFORBooks_WOO_CONSUMER_KEY": "ck_dummy",
    "PFORBooks_WOO_CONSUMER_SECRET": "cs_dummy",
}


class FakeResponse:
    status = 200

    def __init__(self, orders):
        self.body = json.dumps(orders).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, count):
        return self.body[:count]


class FakeOpener:
    def __init__(self, orders):
        self.orders = orders
        self.calls = []

    def open(self, req, timeout):
        self.calls.append((req, timeout))
        return FakeResponse(self.orders)


class WooAPIClientTests(TestCase):
    @patch.dict("os.environ", ENV, clear=False)
    def test_read_only_fetch_and_stage(self):
        opener = FakeOpener([example()])
        fetched = fetch_recent_orders(days=7, opener=opener)
        self.assertEqual(len(fetched), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.full_url.startswith("https://example.org/wp-json/wc/v3/orders?"))
        self.assertEqual(timeout, 12)
        self.assertTrue(request.get_header("Authorization").startswith("Basic "))
        self.assertEqual(fetch_and_stage(days=7, opener=FakeOpener([example()])), (1, 0))
        self.assertEqual(fetch_and_stage(days=7, opener=FakeOpener([example()])), (0, 1))
        self.assertEqual(WooOrderImport.objects.count(), 1)

    @patch.dict("os.environ", ENV, clear=False)
    def test_pagination_and_limits(self):
        first = [example(order_id=i) for i in range(1, 51)]
        class Paged:
            def __init__(self):
                self.calls = 0
            def open(self, req, timeout):
                self.calls += 1
                return FakeResponse(first if self.calls == 1 else [example(order_id=51)])
        opener = Paged()
        self.assertEqual(len(fetch_recent_orders(opener=opener)), 51)
        self.assertEqual(opener.calls, 2)

    @patch.dict("os.environ", {"PFORBooks_WOO_IMPORT_ENABLED": "0"}, clear=True)
    def test_disabled_by_default(self):
        self.assertFalse(configured())
        with self.assertRaises(WooConnectionError):
            fetch_recent_orders(opener=FakeOpener([example()]))

    @patch.dict("os.environ", ENV, clear=True)
    def test_rejects_non_https_configuration(self):
        from os import environ
        environ["PFORBooks_WOO_STORE_URL"] = "http://example.org"
        with self.assertRaises(WooConnectionError):
            fetch_recent_orders(opener=FakeOpener([]))

    @patch.dict("os.environ", ENV, clear=True)
    def test_staff_fetch_button(self):
        user = get_user_model().objects.create_user("woo_fetcher", password="pw", is_staff=True)
        self.client.force_login(user)
        with patch("accounting_imports.woo_views.fetch_and_stage", return_value=(2, 1)) as fetch:
            response = self.client.post(reverse("accounting:woo_inbox"), {
                "source": "woocommerce", "days": "7"
            })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 new orders")
        fetch.assert_called_once_with(days=7)

    @patch.dict("os.environ", {
        "PFORBooks_WOO_IMPORT_ENABLED": "1",
        "WOO_BASE_URL": "https://example.org",
        "WOO_CONSUMER_KEY": "ck_existing",
        "WOO_CONSUMER_SECRET": "cs_existing",
    }, clear=True)
    def test_reuses_existing_woo_environment_keys(self):
        self.assertTrue(configured())
        opener = FakeOpener([example()])
        self.assertEqual(len(fetch_recent_orders(days=7, opener=opener)), 1)
        self.assertEqual(opener.calls[0][0].get_method(), "GET")

    @patch.dict("os.environ", {
        "PFORBooks_WOO_IMPORT_ENABLED": "1",
        "WOO_BASE_URL": "https://example.org",
        "WOO_CONSUMER_KEY": "ck_existing",
        "WOO_CONSUMER_SECRET": "cs_existing",
        "PFORBooks_WOO_CONSUMER_KEY": "ck_unpaired",
    }, clear=True)
    def test_incomplete_accounting_override_refuses_fallback(self):
        self.assertFalse(configured())
        with self.assertRaises(WooConnectionError):
            fetch_recent_orders(opener=FakeOpener([]))

    @patch.dict("os.environ", {
        "WOO_BASE_URL": "https://example.org",
        "WOO_CONSUMER_KEY": "ck_existing",
        "WOO_CONSUMER_SECRET": "cs_existing",
    }, clear=True)
    def test_existing_credentials_alone_do_not_enable_import(self):
        self.assertFalse(configured())
