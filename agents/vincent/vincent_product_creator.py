"""Vincent: explicitly gated creation of WooCommerce ORIGINAL ARTWORK drafts.

Not connected to a webpage or command-line entry point. The default is read-only.
Existing products are never updated, deleted, or published.
"""

from typing import Any, Callable, Mapping

from agents.vincent.vincent_draft_creator import prepare_original_artwork_draft_plan
from agents.vincent.vincent_tag_resolver import ensure_product_tags


def create_original_artwork_draft(
    intake: Mapping[str, Any],
    *,
    description: str,
    short_description: str,
    woo_get: Callable[..., Any],
    woo_post: Callable[..., Any] | None = None,
    image_alt_text: str = "",
    dry_run: bool = True,
    confirm_create: bool = False,
) -> dict[str, Any]:
    """Preview by default; create a draft only after explicit approval.

    - Read-only mode: GETs may occur; no POSTs.
    - Write mode: requires BOTH dry_run=False AND confirm_create=True.
    - Any exact or possible title match blocks creation (no override yet).
    - In write mode only, creates missing tags and then ONE simple draft.

    WooCommerce has no transaction across tag and product creation. If product
    creation fails after tags have been created, those tags may remain; an
    exception reports their IDs for reconciliation. Do not retry blindly.
    """
    if not dry_run and not confirm_create:
        raise PermissionError("Explicit confirm_create=True is required to create a draft")

    plan = prepare_original_artwork_draft_plan(
        intake,
        description=description,
        short_description=short_description,
        image_alt_text=image_alt_text,
        woo_get=woo_get,
    )
    if dry_run:
        return {**plan, "mode": "dry_run", "write_performed": False}

    if not plan["creation_allowed_without_review"]:
        raise RuntimeError(
            "Existing original artwork may match this title. Review before creation: "
            + repr(plan["duplicate_matches"])
        )
    if woo_post is None:
        raise ValueError("A WooCommerce POST helper is required for confirmed creation")

    # Make a private copy; never modify the caller's read-only plan.
    payload = {**plan["product_payload"]}
    # Force draft even if the payload builder changes in the future.
    payload["type"] = "simple"
    payload["status"] = "draft"
    tag_result = ensure_product_tags(
        plan["suggested_tag_names"], woo_get=woo_get, woo_post=woo_post
    )
    payload["tags"] = tag_result["tags"]

    try:
        product = woo_post("products", payload)
    except Exception as exc:
        raise RuntimeError(
            "Product creation failed; newly created tags may remain in WooCommerce. "
            f"Created tags: {tag_result['created']!r}. "
            "Check WooCommerce for a draft before retrying."
        ) from exc

    if not isinstance(product, dict) or not isinstance(product.get("id"), int):
        raise RuntimeError(
            "WooCommerce returned an unexpected product response. "
            "Check for a draft before retrying. "
            f"Created tags: {tag_result['created']!r}"
        )
    if product.get("status") != "draft" or product.get("type") != "simple":
        raise RuntimeError(
            "WooCommerce returned an unexpected product type or status. "
            f"Product ID: {product['id']}; review in WooCommerce immediately."
        )
    return {
        "mode": "created_draft",
        "write_performed": True,
        "product_id": product["id"],
        "product_status": product["status"],
        "created_tags": tag_result["created"],
        "reused_tags": tag_result["reused"],
    }
