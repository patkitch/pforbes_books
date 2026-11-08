"""Vincent: original-artwork WooCommerce draft payload preparation.

This module makes no network requests and creates no products.
It intentionally remains independent of Pauly's print workflow.
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Mapping
from urllib.parse import urlsplit


SHIPPING_CLASSES = {
    "sm": "flat_rate_original_artwork_sm",
    "m": "flat_rate_original_artwork_m",
    "l": "flat_rate_original_artwork_l",
    "xl": "flat_rate_original_artwork_xl",
}

CANVAS_PROFILES = {
    "traditional": "Traditional / Slim",
    "gallery": "Gallery / Deep Edge",
    "museum": "Museum / Ultra-Deep",
    "flat": "Flat Panel / Board",
}


def _required_text(data: Mapping[str, Any], field: str) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        raise ValueError(f"Missing required field: {field}")
    return value


def _positive_decimal(data: Mapping[str, Any], field: str) -> Decimal:
    raw = _required_text(data, field)
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return value


def build_original_artwork_draft_payload(
    intake: Mapping[str, Any],
    *,
    category_id: int,
    description: str,
    short_description: str,
    image_alt_text: str = "",
) -> Dict[str, Any]:
    """Build (but do not submit) a one-of-a-kind WooCommerce simple draft.

    Required intake keys:
      title, style, medium, width, height, canvas_profile, framed,
      shipping_size, price.
    When framed is True, frame_width and frame_height are also required.

    `description` and `short_description` are final, artist-approved text.
    The optional image URL is taken from intake["image_url"]. No image is uploaded
    or downloaded here. The alt text may be supplied by the caller; otherwise
    the artwork title is used.
    """
    title = _required_text(intake, "title")
    _required_text(intake, "style")
    _required_text(intake, "medium")
    artwork_width = _positive_decimal(intake, "width")
    artwork_height = _positive_decimal(intake, "height")
    price = _positive_decimal(intake, "price")

    profile = _required_text(intake, "canvas_profile").lower()
    if profile not in CANVAS_PROFILES:
        raise ValueError("Unknown canvas profile")

    framed = intake.get("framed")
    if not isinstance(framed, bool):
        raise ValueError("framed must be True or False")
    if framed:
        shipping_length = _positive_decimal(intake, "frame_width")
        shipping_width = _positive_decimal(intake, "frame_height")
    else:
        shipping_length = artwork_width
        shipping_width = artwork_height

    shipping_size = _required_text(intake, "shipping_size").lower()
    if shipping_size not in SHIPPING_CLASSES:
        raise ValueError("Unknown shipping size; choose SM, M, L, or XL")

    if not isinstance(category_id, int) or isinstance(category_id, bool) or category_id <= 0:
        raise ValueError("A valid existing Original Artwork category ID is required")

    image_url = str(intake.get("image_url") or "").strip()
    images = []
    if image_url:
        parsed = urlsplit(image_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("image_url must be a valid http(s) URL")
        images = [{"src": image_url, "alt": image_alt_text.strip() or title}]

    return {
        "name": title,
        "type": "simple",
        "status": "draft",
        "catalog_visibility": "visible",
        "regular_price": f"{price:.2f}",
        "description": description,
        "short_description": short_description,
        "categories": [{"id": category_id}],
        "images": images,
        "shipping_class": SHIPPING_CLASSES[shipping_size],
        # Match existing flat-rate store practice: two face dimensions,
        # no assumed thickness or package dimensions.
        "dimensions": {
            "length": format(shipping_length, "f"),
            "width": format(shipping_width, "f"),
            "height": "",
        },
        "tax_status": "taxable",
        "manage_stock": True,
        "stock_quantity": 1,
        "backorders": "no",
        "sold_individually": True,
        "virtual": False,
        "downloadable": False,
    }
