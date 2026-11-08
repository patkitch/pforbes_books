"""Read-only original-artwork duplicate checks for Vincent.

Only WooCommerce GET calls are made. Matches are restricted to the selected
original-artwork category, so print products with similar names are ignored.
"""

from typing import Any, Callable
import re


def _normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


# Descriptive catalog suffixes, *only* after a visible title separator.
# Deliberately do not remove ordinary title words such as 'Framed' by itself.
_ORIGINAL_SUFFIX = re.compile(
    r"\s*(?:[•|]|\s[-–—]\s)\s*"
    r"original\s+(?:acrylic|oil|watercolor|watercolour|mixed.media)?\s*"
    r"(?:painting|artwork|art)(?:\s+(?:framed|unframed|on\s+canvas|on\s+panel))*\s*$",
    re.IGNORECASE,
)


def _base_artwork_title(value: str) -> str:
    text = str(value or "").strip()
    return _normalize_title(_ORIGINAL_SUFFIX.sub("", text))


def _search_originals(title: str, *, category_id: int, woo_get: Callable[..., Any]) -> list[dict[str, Any]]:
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("Artwork title is required for duplicate checking.")
    if type(category_id) is not int or category_id <= 0:
        raise ValueError("A valid WooCommerce category ID is required.")

    # Search with the base title so a descriptive suffix on the new input
    # does not prevent retrieval of an existing listing.
    search_title = _ORIGINAL_SUFFIX.sub("", clean_title).strip() or clean_title
    found: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    page = 1
    while True:
        products = woo_get("products", params={
            "search": search_title,
            "status": "any",
            "per_page": 100,
            "page": page,
        })
        if not isinstance(products, list):
            raise RuntimeError("Unexpected WooCommerce product search response.")
        for product in products:
            if not isinstance(product, dict):
                continue
            pid = product.get("id")
            if type(pid) is not int or pid in seen_ids:
                continue
            categories = product.get("categories") or []
            in_category = any(
                isinstance(c, dict) and c.get("id") == category_id
                for c in categories
            )
            if not in_category:
                continue
            found.append({
                "id": pid,
                "name": product.get("name", ""),
                "status": product.get("status", ""),
                "type": product.get("type", ""),
            })
            seen_ids.add(pid)
        if len(products) < 100:
            break
        page += 1
    return found


def find_existing_originals(
    title: str, *, category_id: int = 1547, woo_get: Callable[..., Any]
) -> list[dict[str, Any]]:
    """Preserved interface: return *exact* original-title matches only."""
    return [
        p for p in _search_originals(title, category_id=category_id, woo_get=woo_get)
        if _normalize_title(p["name"]) == _normalize_title(title)
    ]


def review_original_title_matches(
    title: str, *, category_id: int = 1547, woo_get: Callable[..., Any]
) -> dict[str, list[dict[str, Any]]]:
    """Report exact and likely same-artwork matches for manual review.

    A possible match requires the *same complete base title* after removing
    a known 'Original ...' suffix. Similar words alone are not enough.
    This is not a guarantee that all duplicates will be found.
    """
    exact = []
    possible = []
    target = _normalize_title(title)
    base_target = _base_artwork_title(title)
    for product in _search_originals(title, category_id=category_id, woo_get=woo_get):
        if _normalize_title(product["name"]) == target:
            exact.append(product)
        elif _base_artwork_title(product["name"]) == base_target:
            possible.append(product)
    return {"exact": exact, "possible": possible}
