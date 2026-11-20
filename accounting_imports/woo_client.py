"""Read-only WooCommerce REST v3 client for a deliberately manual import.

No API credentials are stored in the database or source tree. No write requests
to WooCommerce or automatic ledger postings are made.
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from django.core.exceptions import ValidationError

from .woo_orders import stage_orders

MAX_FETCH = 200
PAGE_SIZE = 50


class WooConnectionError(Exception):
    """User-safe connection failure; deliberately excludes credentials and API body."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _credentials():
    """Reuse the website automation WooCommerce settings when appropriate.

    Dedicated accounting variables take precedence. Never mix incomplete
    dedicated settings with the older website settings.
    """
    dedicated = (
        os.environ.get("PFORBooks_WOO_STORE_URL", "").strip(),
        os.environ.get("PFORBooks_WOO_CONSUMER_KEY", "").strip(),
        os.environ.get("PFORBooks_WOO_CONSUMER_SECRET", "").strip(),
    )
    existing = (
        os.environ.get("WOO_BASE_URL", "").strip(),
        os.environ.get("WOO_CONSUMER_KEY", "").strip(),
        os.environ.get("WOO_CONSUMER_SECRET", "").strip(),
    )
    if all(dedicated):
        return dedicated
    if any(dedicated):
        return ("", "", "")
    return existing


def configured():
    base, key, secret = _credentials()
    return (
        os.environ.get("PFORBooks_WOO_IMPORT_ENABLED", "").strip() == "1"
        and bool(base and key and secret)
    )


def _settings():
    if not configured():
        raise WooConnectionError("WooCommerce import is not configured on this environment.")
    raw, key, secret = _credentials()
    parsed = urllib.parse.urlsplit(raw)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username
        or parsed.password or parsed.query or parsed.fragment
        or parsed.port not in (None, 443) or parsed.path not in ("", "/")
    ):
        raise WooConnectionError("Store URL must be an HTTPS site root without a path or query.")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise WooConnectionError("Local HTTP addresses are not permitted.")
    return raw.rstrip("/"), key, secret


def fetch_recent_orders(*, days=30, opener=None):
    """Fetch at most 200 recent orders in pages; reject truncated sets.

    Does not stage records until all pages have been validated. The manual
    reviewer still decides whether to create each internal receipt.
    """
    if not isinstance(days, int) or not 1 <= days <= 90:
        raise ValidationError("Choose between 1 and 90 days.")
    base, key, secret = _settings()
    auth = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    after = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00"
    opener = opener or urllib.request.build_opener(_NoRedirect())
    orders = []
    for page in range(1, 6):
        query = urllib.parse.urlencode({
            "after": after, "per_page": PAGE_SIZE, "page": page,
            "orderby": "date", "order": "desc",
        })
        url = f"{base}/wp-json/wc/v3/orders?{query}"
        req = urllib.request.Request(url, headers={
            "Authorization": "Basic " + auth,
            "Accept": "application/json",
            "User-Agent": "PForbesBooks-Accounting-Import/1.0",
        }, method="GET")
        try:
            with opener.open(req, timeout=12) as response:
                if response.status != 200:
                    raise WooConnectionError("WooCommerce did not return a successful response.")
                raw = response.read(3_000_001)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WooConnectionError(
                "Unable to retrieve WooCommerce orders. Check the read-only API key and site connection."
            ) from None
        if len(raw) > 3_000_000:
            raise WooConnectionError("WooCommerce response is too large.")
        try:
            page_orders = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise WooConnectionError("WooCommerce returned invalid order data.") from None
        if not isinstance(page_orders, list) or len(page_orders) > PAGE_SIZE:
            raise WooConnectionError("WooCommerce returned an unexpected order list.")
        orders.extend(page_orders)
        if len(orders) > MAX_FETCH:
            raise WooConnectionError("More than 200 orders; use a smaller date window.")
        if len(page_orders) < PAGE_SIZE:
            break
        if page == 5:
            raise WooConnectionError("Too many orders for one import; use a smaller date window.")
    return orders


def fetch_and_stage(*, days=30, opener=None):
    orders = fetch_recent_orders(days=days, opener=opener)
    if not orders:
        return 0, 0
    return stage_orders(orders)
