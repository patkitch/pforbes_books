"""Vincent: WooCommerce product tag lookup and optional creation.

The lookup function is READ-ONLY. The creation function is a WRITE operation:
call it only after an explicit Create WooCommerce Draft action, never while
showing previews. Both functions accept injected WooCommerce helpers for tests.
"""

from typing import Any, Callable, Iterable
import os
import time

# Preview-only, process-local cache; each Django worker keeps its own copy.
_TAG_CACHE_SECONDS = 15 * 60
_tag_cache: dict[str, Any] = {"store": None, "expires": 0.0, "tags": None}


def invalidate_tag_cache() -> None:
    """Discard cached preview tags after a successful WooCommerce tag write."""
    _tag_cache.update({"store": None, "expires": 0.0, "tags": None})


def _is_production_woo_get(woo_get: Callable[..., Any]) -> bool:
    """Never share cached results across injected test helpers."""
    return (getattr(woo_get, "__module__", "") == "agents.pauly.core"
            and getattr(woo_get, "__name__", "") == "woo_get")


def _all_existing_tags(*, woo_get: Callable[..., Any]) -> list[dict[str, Any]]:
    """Fetch paginated tags for read-only preview; never cache partial results."""
    store = os.getenv("WOO_BASE_URL", "").rstrip("/").casefold()
    now = time.monotonic()
    use_cache = _is_production_woo_get(woo_get)
    if (use_cache and _tag_cache["tags"] is not None
            and _tag_cache["store"] == store and now < _tag_cache["expires"]):
        return _tag_cache["tags"]

    all_tags: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = woo_get("products/tags", params={"per_page": 100, "page": page})
        if not isinstance(batch, list):
            raise ValueError("Unexpected WooCommerce tag lookup response")
        all_tags.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    if use_cache:
        _tag_cache.update({"store": store, "expires": time.monotonic() + _TAG_CACHE_SECONDS,
                           "tags": all_tags})
    return all_tags


# Only approved equivalents; never use fuzzy matching.
TAG_ALIASES: dict[str, str] = {"acrylic": "Acrylic Painting"}


def _canonical_names(suggested_names: Iterable[str]) -> list[tuple[str, str]]:
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for original in suggested_names:
        requested = str(original or "").strip()
        canonical = TAG_ALIASES.get(requested.casefold(), requested)
        if not canonical or canonical.casefold() in seen:
            continue
        seen.add(canonical.casefold())
        unique.append((requested, canonical))
    return unique


def _find_exact_tag(name: str, *, woo_get: Callable[..., Any]) -> dict[str, Any] | None:
    page = 1
    while True:
        results = woo_get("products/tags", params={"search": name, "per_page": 100, "page": page})
        if not isinstance(results, list):
            raise ValueError("Unexpected WooCommerce tag lookup response")
        for tag in results:
            if (isinstance(tag, dict)
                    and str(tag.get("name", "")).strip().casefold() == name.casefold()
                    and type(tag.get("id")) is int and tag["id"] > 0):
                return tag
        if len(results) < 100:
            return None
        page += 1


def resolve_existing_tags(
    suggested_names: Iterable[str], *, woo_get: Callable[..., Any]
) -> dict[str, Any]:
    """READ-ONLY: returns {'matched': [...], 'missing': [...]}.

    Each match has requested, name and id. Missing names use the original
    suggestion, as before. No tag or product is ever created here.
    """
    # One paginated catalog fetch (normally two requests for this store),
    # rather than a separate API search for every suggested tag.
    catalog = _all_existing_tags(woo_get=woo_get)
    by_name: dict[str, dict[str, Any]] = {}
    for tag in catalog:
        if (isinstance(tag, dict) and isinstance(tag.get("name"), str)
                and type(tag.get("id")) is int and tag["id"] > 0):
            by_name.setdefault(tag["name"].strip().casefold(), tag)

    matched: list[dict[str, Any]] = []
    missing: list[str] = []
    for requested, canonical in _canonical_names(suggested_names):
        found = by_name.get(canonical.casefold())
        if found is None:
            missing.append(requested)
        else:
            matched.append({"requested": requested, "name": found["name"], "id": found["id"]})
    return {"matched": matched, "missing": missing}


def ensure_product_tags(
    suggested_names: Iterable[str],
    *,
    woo_get: Callable[..., Any],
    woo_post: Callable[..., Any],
) -> dict[str, Any]:
    """WRITE: reuse existing tags, create missing ones and return tag IDs.

    Call only as part of an explicitly approved WooCommerce draft creation.
    This function itself does NOT create a product or publish anything. It may
    create tags in the store, so never invoke it during a preview or dry-run.

    Returns {'tags': [{'id': ...}], 'created': [...], 'reused': [...]}.
    If WooCommerce rejects a creation, the error propagates; earlier tag writes
    cannot be automatically rolled back. The caller should log those effects.
    """
    tags: list[dict[str, int]] = []
    created: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []

    for requested, canonical in _canonical_names(suggested_names):
        found = _find_exact_tag(canonical, woo_get=woo_get)
        if found is not None:
            reused.append({"requested": requested, "name": found["name"], "id": found["id"]})
            tags.append({"id": found["id"]})
            continue

        # No tag was found. WooCommerce might create it or reject a race with
        # another request. Never guess an ID or silently create a duplicate.
        try:
            new_tag = woo_post("products/tags", {"name": canonical})
        except Exception:
            existing_after_error = _find_exact_tag(canonical, woo_get=woo_get)
            if existing_after_error is None:
                raise
            found = existing_after_error
            reused.append({"requested": requested, "name": found["name"], "id": found["id"]})
            tags.append({"id": found["id"]})
            continue

        if (not isinstance(new_tag, dict)
                or type(new_tag.get("id")) is not int
                or new_tag["id"] <= 0):
            raise RuntimeError(f"WooCommerce did not return a valid ID for tag {canonical!r}")
        invalidate_tag_cache()  # A successful write makes any preview cache stale.
        created.append({"requested": requested, "name": new_tag.get("name", canonical), "id": new_tag["id"]})
        tags.append({"id": new_tag["id"]})

    return {"tags": tags, "created": created, "reused": reused}
