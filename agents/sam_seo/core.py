from typing import Dict, Any
import html
import re

from agents.pauly.core import woo_get  # reuse Woo helper from Pauly


MAX_META_LENGTH = 155  # target length for Yoast meta descriptions


def _derive_artwork_title(name: str) -> str:
    """
    Try to strip suffixes like:
    ' – Open Edition Giclée Matted Print by P. Forbes'
    ' – Giclée Print by P. Forbes 16\"x20\"'
    and keep the base artwork title.
    """
    if not name:
        return ""

    artwork_title = name
    # Prefer splitting on en dash first
    if "–" in artwork_title:
        artwork_title = artwork_title.split("–")[0].strip()
    elif "|" in artwork_title:
        artwork_title = artwork_title.split("|")[0].strip()

    return artwork_title


def _guess_mood_from_text(text: str) -> str:
    """
    Very simple heuristic to guess mood based on keywords.
    This controls tone for the meta description.
    """
    if not text:
        return "neutral"

    t = text.lower()

    # Dramatic / stormy
    if any(word in t for word in ["storm", "stormy", "night", "breaking into dusk", "dusk", "glass explosion"]):
        return "dramatic"

    # Coastal / ocean
    if any(word in t for word in ["ocean", "sea", "coast", "bay", "waves", "lighthouse", "harbor", "bridge"]):
        return "coastal"

    # Prairie / calm landscape
    if any(word in t for word in ["kansas", "prairie", "flint hills", "field", "silo", "windmill", "farm"]):
        return "calm"

    # Story / figures / animals
    if any(word in t for word in ["child", "dancing", "celebrating", "evie", "quill", "dog", "australian shepherd"]):
        return "story"

    return "neutral"


def _product_taxonomy_text(product: Dict[str, Any]) -> str:
    """Return WooCommerce category and tag names as one searchable string."""
    labels = []
    for field in ("categories", "tags"):
        labels.extend(
            item.get("name", "")
            for item in product.get(field, [])
            if isinstance(item, dict)
        )
    return " ".join(labels).lower()


def _is_print_product(product: Dict[str, Any]) -> bool:
    """Identify products that are prints, even when they depict an original."""
    name = (product.get("name") or "").lower()
    taxonomy = _product_taxonomy_text(product)
    product_type = (product.get("type") or "").lower()
    return (
        "giclée" in name
        or "giclee" in name
        or bool(re.search(r"\bprints?\b", name))
        or "giclée" in taxonomy
        or "giclee" in taxonomy
        or bool(re.search(r"\bprints?\b", taxonomy))
        or product_type == "variable"
    )


def _is_original_artwork(product: Dict[str, Any]) -> bool:
    """Recognize a painting for sale, without confusing it with its prints."""
    if _is_print_product(product):
        return False
    taxonomy = _product_taxonomy_text(product)
    if "original artwork" in taxonomy:
        return True
    details = " ".join(
        (product.get(field) or "")
        for field in ("name", "short_description", "description")
    ).lower()
    return bool(
        re.search(r"\boriginal\b.{0,60}\b(painting|artwork)\b", details)
    )


def _build_focus_keyphrase(product: Dict[str, Any]) -> str:
    """Build a subject-specific phrase appropriate to the product being sold."""
    name = (product.get("name") or "").strip()
    artwork_title = _derive_artwork_title(name)
    lower_name = name.lower()

    if _is_original_artwork(product):
        details = " ".join(
            (product.get(field) or "")
            for field in ("short_description", "description")
        ).lower()
        medium = next(
            (
                word for word in ("acrylic", "oil", "watercolor", "watercolour", "gouache")
                if re.search(rf"\b{word}\b", details)
            ),
            "",
        )
        title_words = artwork_title.split()[:2]
        phrase_parts = title_words + ["original"]
        if medium:
            phrase_parts.extend([medium, "painting"])
        else:
            phrase_parts.append("painting")
        return " ".join(phrase_parts).lower()

    subject_bits = []
    if "windmill" in lower_name:
        subject_bits.append("windmill")
    if "silo" in lower_name:
        subject_bits.append("silo")
    if "lighthouse" in lower_name:
        subject_bits.append("lighthouse")
    if "bridge" in lower_name:
        subject_bits.append("bridge")
    if "prairie" in lower_name or "flint hills" in lower_name:
        subject_bits.append("prairie")
    if "kansas" in lower_name:
        subject_bits.append("kansas")
    if any(word in lower_name for word in ("ocean", "sea", "coast", "bay")):
        subject_bits.append("seascape")
    if any(word in lower_name for word in ("dog", "australian shepherd", "quill", "evie")):
        subject_bits.append("dog portrait")

    if not subject_bits and artwork_title:
        subject_bits.append(artwork_title)

    taxonomy = _product_taxonomy_text(product)
    is_giclee = any(
        term in lower_name + " " + taxonomy
        for term in ("giclée", "giclee")
    )
    print_term = "giclée print" if is_giclee else "art print"
    phrase = " ".join(subject_bits[:3]) + f" {print_term}" if subject_bits else print_term
    return " ".join(phrase.split()).lower()


def _truncate_to_length(text: str, max_len: int) -> str:
    """
    Truncate text to max_len characters without chopping mid-word badly.
    """
    if len(text) <= max_len:
        return text

    trimmed = text[:max_len]
    # Try to backtrack to last space
    last_space = trimmed.rfind(" ")
    if last_space > 0:
        trimmed = trimmed[:last_space]

    return trimmed



def _build_meta_description(
    product: Dict[str, Any],
    focus_keyphrase: str
) -> str:
    """Build a concise, product-specific meta description within 155 characters."""
    name = (product.get("name") or "").strip()
    short_description = _strip_html(product.get("short_description") or "")
    long_description = _strip_html(product.get("description") or "")

    if _is_original_artwork(product):
        # Original listings need their own title and artist story, not print copy.
        source = long_description or short_description or name
        if name and name.lower() not in source.lower():
            source = f"{name}. {source}"
        return _truncate_to_length(" ".join(source.split()), MAX_META_LENGTH)

    description = long_description
    mood = _guess_mood_from_text(name + " " + description)

    if mood == "dramatic":
        ending = (
            "Bold light and movement in an open edition "
            "fine art print. Matted and unmatted options."
        )
    elif mood == "coastal":
        ending = (
            "Coastal color and atmosphere in an open edition "
            "fine art print. Matted and unmatted options."
        )
    elif mood == "calm":
        ending = (
            "A peaceful scene reproduced as an open edition "
            "fine art print. Matted and unmatted options."
        )
    elif mood == "story":
        ending = (
            "A story captured in an open edition fine art "
            "print. Matted and unmatted options."
        )
    else:
        ending = (
            "An open edition fine art print by P. Forbes, "
            "available with or without a mat."
        )

    base = f"{focus_keyphrase.capitalize()}. {ending}"
    return _truncate_to_length(base, MAX_META_LENGTH)


def build_sam_seo_suggestion(product: Dict[str, Any]) -> Dict[str, str]:
    """
    Main entry point for SamSEO:
    Given a WooCommerce product JSON, return a dict with:
      - focus_keyphrase
      - meta_description
    """
    focus_keyphrase = _build_focus_keyphrase(product)
    meta_description = _build_meta_description(product, focus_keyphrase)

    return {
        "focus_keyphrase": focus_keyphrase,
        "meta_description": meta_description,
    }


def fetch_products_batch(page: int, per_page: int = 50) -> Any:
    """
    Fetch a page of WooCommerce products.
    We're reusing Pauly's Woo helper.
    """
    params = {
        "per_page": per_page,
        "page": page,
        "orderby": "id",
        "order": "asc",
    }
    return woo_get("products", params=params)

def _strip_html(text: str) -> str:
    if not text:
        return ""
    # unescape HTML entities and remove tags
    text = html.unescape(text)
    return re.sub(r"<[^>]+>", "", text)


def suggest_seo_for_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """Return a focus keyphrase and product-specific meta description."""
    name = (product.get("name") or "").strip()
    short_desc = _strip_html(product.get("short_description") or "")
    long_desc = _strip_html(product.get("description") or "")
    tags = [
        t.get("name", "")
        for t in product.get("tags", [])
        if isinstance(t, dict)
    ]

    focus_keyphrase = _build_focus_keyphrase(product)
    is_original = _is_original_artwork(product)
    source = (long_desc or short_desc or name) if is_original else (short_desc or long_desc or name)
    source = " ".join(source.replace("\\n", " ").split()).strip()

    if is_original and name and name.lower() not in source.lower():
        source = f"{name}. {source}"

    if not source:
        source = (
            f"{name} is an open edition Giclée fine art print "
            "by P. Forbes, available with or without a mat."
        )

    meta_description = _truncate_to_length(source, MAX_META_LENGTH)
    seo_ok = 100 <= len(meta_description) <= MAX_META_LENGTH

    reasoning_parts = [
        "Meta description trimmed to ~155 characters for Yoast."
    ]
    if not seo_ok:
        reasoning_parts.append(
            "Length is outside the ideal 100–155 range; you may want to tweak it."
        )
    if tags:
        reasoning_parts.append(f"Existing tags considered: {', '.join(tags[:5])}")

    return {
        "focus_keyphrase": focus_keyphrase,
        "meta_description": meta_description,
        "seo_ok": seo_ok,
        "reasoning": " ".join(reasoning_parts),
    }


def fetch_and_suggest_seo(product_id: int) -> Dict[str, Any]:
    """
    Read a product from WooCommerce by ID and generate SEO suggestions.
    Returns a dict with:
      - product
      - suggestions
    """
    product = woo_get(f"products/{product_id}")
    suggestions = suggest_seo_for_product(product)
    return {
        "product": product,
        "suggestions": suggestions,
    }