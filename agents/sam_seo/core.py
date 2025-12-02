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


def _build_focus_keyphrase(product: Dict[str, Any]) -> str:
    """
    Build a Yoast-style focus keyphrase:
    - 2–5 words
    - includes 'print'
    - natural and subject-specific where possible
    """
    name = (product.get("name") or "").strip()
    artwork_title = _derive_artwork_title(name)

    lower_name = name.lower()

    # Base subject words
    subject_bits = []

    # Try to add key subject from title
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
    if "ocean" in lower_name or "sea" in lower_name or "coast" in lower_name or "bay" in lower_name:
        subject_bits.append("seascape")
    if "dog" in lower_name or "australian shepherd" in lower_name or "quill" in lower_name or "evie" in lower_name:
        subject_bits.append("dog portrait")

    # If we didn't find anything, fall back to artwork title
    if not subject_bits and artwork_title:
        subject_bits.append(artwork_title)

    # Decide print type
    if "giclée" in lower_name or "giclee" in lower_name:
        print_term = "giclée print"
    else:
        print_term = "art print"

    # Build phrase
    # Example: "Kansas windmill giclée print"
    if subject_bits:
        phrase = " ".join(subject_bits[:3]) + f" {print_term}"
    else:
        phrase = print_term

    # Clean extra spaces
    phrase = " ".join(phrase.split())

    return phrase.lower()


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


def _build_meta_description(product: Dict[str, Any], focus_keyphrase: str) -> str:
    """
    Build a Yoast-style meta description with dynamic tone:
    - includes the focus keyphrase once (at the beginning)
    - <= MAX_META_LENGTH characters
    - uses 'matted' when it fits, otherwise drops it
    """
    name = (product.get("name") or "").strip()
    description = (product.get("description") or "").strip()

    artwork_title = _derive_artwork_title(name)
    mood = _guess_mood_from_text(name + " " + description)

    # Decide base subject from keyphrase by stripping 'giclée print' / 'art print'
    subject = focus_keyphrase
    for phrase in ["giclée print", "giclee print", "art print"]:
        subject = subject.replace(phrase, "").strip()
    if not subject:
        subject = artwork_title or "artwork"

    # Build sentence template with 'matted' included first
    if mood == "dramatic":
        base = (
            f"{focus_keyphrase.capitalize()} with bold light and movement, "
            f"matted and ready to frame. Open edition for a striking focal point."
        )
    elif mood == "coastal":
        base = (
            f"{focus_keyphrase.capitalize()} capturing luminous coastal color, "
            f"matted and ready to frame. Open edition to bring the ocean home."
        )
    elif mood == "calm":
        base = (
            f"{focus_keyphrase.capitalize()} with soft impressionist light, "
            f"matted and ready to frame. Open edition for peaceful, warm decor."
        )
    elif mood == "story":
        base = (
            f"{focus_keyphrase.capitalize()} that tells a personal story, "
            f"matted and ready to frame. Open edition for meaningful wall art."
        )
    else:
        base = (
            f"{focus_keyphrase.capitalize()} with rich color and texture, "
            f"matted and ready to frame. Open edition for versatile home decor."
        )

    # First try with 'matted' included
    desc = _truncate_to_length(base, MAX_META_LENGTH)
    if len(desc) <= MAX_META_LENGTH:
        return desc

    # If still too long, try again without 'matted' (Option C behavior)
    base_no_matted = base.replace("matted and ", "")
    desc2 = _truncate_to_length(base_no_matted, MAX_META_LENGTH)

    return desc2


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
    """
    Given a WooCommerce product dict, return SEO suggestions:
      - focus_keyphrase
      - meta_description  (<= 155 chars)
      - seo_ok            (bool, simple heuristic)
      - reasoning         (short explanation)
    """
    name = (product.get("name") or "").strip()
    short_desc = _strip_html(product.get("short_description") or "")
    long_desc = _strip_html(product.get("description") or "")

    categories = [c.get("name", "") for c in product.get("categories", [])]
    tags = [t.get("name", "") for t in product.get("tags", [])]

    # Focus keyphrase: try to be concise & human
    # For your catalog, a good default is "Title | Giclée matted print by P. Forbes"
    base_keyphrase = name
    if "Giclée" not in base_keyphrase and "giclée" not in base_keyphrase.lower():
        base_keyphrase = f"{base_keyphrase} | Giclée matted print by P. Forbes"

    focus_keyphrase = base_keyphrase

    # Meta description: short summary from short_desc or long_desc, fallback to name
    source = short_desc or long_desc or name
    source = source.replace("\n", " ").strip()

    if not source:
        source = f"{name} is an open edition Giclée matted print by P. Forbes Art."

    # Ideal length: <= 155 chars (Yoast guideline)
    ideal_length = 155
    if len(source) > ideal_length:
        meta_description = source[:ideal_length].rstrip(" .,;:") + "…"
    else:
        meta_description = source

    # Simple heuristic: "ok" if length between 100 and 155
    seo_ok = 100 <= len(meta_description) <= 155

    reasoning_parts = []
    reasoning_parts.append("Meta description trimmed to ~155 characters for Yoast.")
    if not seo_ok:
        reasoning_parts.append("Length is outside the ideal 100–155 range; you may want to tweak it.")
    if tags:
        reasoning_parts.append(f"Existing tags considered: {', '.join(tags[:5])}")

    reasoning = " ".join(reasoning_parts)

    return {
        "focus_keyphrase": focus_keyphrase,
        "meta_description": meta_description,
        "seo_ok": seo_ok,
        "reasoning": reasoning,
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