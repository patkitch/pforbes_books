"""Vincent original-artwork draft planning (READ ONLY).

This module assembles a WooCommerce draft payload, resolves existing tag IDs,
and checks for exact or possible duplicate original artwork.
It NEVER sends a POST/PUT/DELETE request, creates tags, or creates products.
A separate, explicitly approved creation step will be implemented later.
"""

from typing import Any, Callable, Mapping

from agents.vincent.core import build_original_artwork_draft_payload
from agents.vincent.tags import generate_original_artwork_tags
from agents.vincent.vincent_tag_resolver import resolve_existing_tags
from agents.vincent.vincent_duplicate_checker import review_original_title_matches


# Confirmed for the CURRENT original acrylic-on-canvas category only.
ORIGINAL_ACRYLIC_CATEGORY_ID = 1547


def prepare_original_artwork_draft_plan(
    intake: Mapping[str, Any],
    *,
    description: str,
    short_description: str,
    woo_get: Callable[..., Any],
    image_alt_text: str = "",
) -> dict[str, Any]:
    """Return a read-only, inspectable WooCommerce draft plan.

    `woo_get` may be the existing Pauly read-only helper or a test double.
    No network activity occurs apart from GET requests performed by that helper.
    No external data is changed.

    Since category 1547 is 'Original Acrylic on Canvas', other mediums are
    intentionally blocked until appropriate categories have been agreed.
    """
    medium = str(intake.get("medium") or "").strip().casefold()
    if "acrylic" not in medium:
        raise ValueError(
            "Category 1547 is 'Original Acrylic on Canvas'. "
            "Choose an appropriate category before creating a non-acrylic artwork draft."
        )

    payload = build_original_artwork_draft_payload(
        intake,
        category_id=ORIGINAL_ACRYLIC_CATEGORY_ID,
        description=description,
        short_description=short_description,
        image_alt_text=image_alt_text,
    )
    suggested_names = generate_original_artwork_tags(intake)
    resolution = resolve_existing_tags(suggested_names, woo_get=woo_get)
    payload["tags"] = [{"id": tag["id"]} for tag in resolution["matched"]]

    # Search only the original-artwork category; never treat print listings
    # with the same artwork title as original-painting duplicates.
    duplicates = review_original_title_matches(
        str(intake.get("title") or ""),
        category_id=ORIGINAL_ACRYLIC_CATEGORY_ID,
        woo_get=woo_get,
    )
    requires_review = bool(duplicates["exact"] or duplicates["possible"])

    return {
        "product_payload": payload,
        "suggested_tag_names": suggested_names,
        "existing_tags": resolution["matched"],
        "missing_tags": resolution["missing"],
        "duplicate_matches": duplicates,
        "requires_duplicate_review": requires_review,
        "creation_allowed_without_review": not requires_review,
        "write_performed": False,
        "note": (
            "READ-ONLY PLAN. Missing tags have not been created. "
            "Product has not been created or published. "
            "Exact or possible original-artwork matches require review before creation."
        ),
    }
