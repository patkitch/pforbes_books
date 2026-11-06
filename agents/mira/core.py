# agents/mira/core.py

from typing import Dict, Any

from agents.pauly.core import woo_get  # reuse the same Woo helper Pauly uses


def generate_blog_from_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """
    Given a WooCommerce product dict, generate a blog draft + social caption.

    Returns a dict with keys:
      - blog_title
      - intro
      - body_paragraphs (list of strings)
      - bullet_points (list of strings)
      - social_caption
    """
    name = (product.get("name") or "").strip()
    short_desc = (product.get("short_description") or "").strip()
    long_desc = (product.get("description") or "").strip()

    categories = [c.get("name", "") for c in product.get("categories", [])]
    tags = [t.get("name", "") for t in product.get("tags", [])]

    primary_category = categories[0] if categories else "Giclée prints"
    tag_phrase = ", ".join(t for t in tags[:4] if t)

    # Blog title in your voice
    blog_title = f"New in the Studio: {name}"

    # Intro paragraph – friendly, a bit reflective, not woo-woo
    intro = (
        f"Today I'm excited to share a new addition to my {primary_category.lower()} collection: {name}. "
        f"This piece grew out of my love for color, light, and those quiet in–between moments "
        f"that invite you to pause and really look."
    )

    # Use descriptions if present, otherwise fall back
    if long_desc:
        story_paragraph = long_desc.replace("\r\n", " ").replace("\n", " ").strip()
    elif short_desc:
        story_paragraph = short_desc.replace("\r\n", " ").replace("\n", " ").strip()
    else:
        story_paragraph = (
            f"{name} is an open edition Giclée fine art print "
            f"reproduced from my original painting. "
            f"I wanted it to capture something worth pausing to appreciate."
        )

    process_paragraph = (
        "Like most of my work, this piece began with loose marks and a sense of curiosity. "
        "I built the scene with layers of acrylic, stepping back often to see how the colors were "
        "talking to each other. The final result balances structure and spontaneity — a mix of "
        "impressionism, emotion, and a little bit of rebellion against keeping things too perfect."
    )

    placement_paragraph = (
        "This open edition Giclée fine art print is available "
        "in three options: 8x10 with a white mat (4x6 image), "
        "11x14 with a white mat (8x10 image), "
        "or 11x14 unmatted. "
        "Choose the presentation that best suits your space."
    )

    body_paragraphs = [
        story_paragraph,
        process_paragraph,
        placement_paragraph,
    ]

    bullet_points = [
        "Open edition Giclée fine art print based on my original painting.",
        "Three print options: two matted and one unmatted.",
        "Reproduced from original artwork by P. Forbes.",
    ]

    # Social caption – short, ready for copy/paste
    social_caption = (
        f"New in the studio: {name}\n\n"
        f"Now available as an open edition Giclée fine art print, "
        f"with matted and unmatted options.\n\n"
        f"Explore the collection at P. Forbes Art. 🖼️"
    )

    if tag_phrase:
        social_caption += f"\n\n#{tag_phrase.replace(', ', ' #')}"

    return {
        "blog_title": blog_title,
        "intro": intro,
        "body_paragraphs": body_paragraphs,
        "bullet_points": bullet_points,
        "social_caption": social_caption,
    }


def fetch_and_generate_blog(product_id: int) -> Dict[str, Any]:
    """
    Read a product from WooCommerce by ID and generate Mira's blog draft.

    Returns:
      - product   (raw Woo dict)
      - blog      (dict from generate_blog_from_product)
    """
    product = woo_get(f"products/{product_id}")
    blog = generate_blog_from_product(product)
    return {
        "product": product,
        "blog": blog,
    }
