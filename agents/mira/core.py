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
            f"{name} is an open edition Giclée matted print, created from my original painting. "
            f"I wanted it to feel like a small window into a moment you might otherwise walk past."
        )

    process_paragraph = (
        "Like most of my work, this piece began with loose marks and a sense of curiosity. "
        "I built the scene with layers of acrylic, stepping back often to see how the colors were "
        "talking to each other. The final result balances structure and spontaneity — a mix of "
        "impressionism, emotion, and a little bit of rebellion against keeping things too perfect."
    )

    placement_paragraph = (
        "This print works beautifully in living rooms, hallways, or cozy reading corners where "
        "you want a quiet focal point. Because it's offered as a matted Giclée in two sizes, "
        "it's easy to frame and fit into your existing space."
    )

    body_paragraphs = [
        story_paragraph,
        process_paragraph,
        placement_paragraph,
    ]

    bullet_points = [
        "Open edition Giclée matted print based on my original painting.",
        "Available in two sizes, ready to frame.",
        "Rich color and texture that bring warmth and presence to your space.",
    ]

    # Social caption – short, ready for copy/paste
    social_caption = (
        f"New in the studio: {name} ✨\n\n"
        f"Printed as an open edition Giclée matted print in two sizes, ready to frame. "
        f"I painted this piece to capture a quiet, reflective moment — the kind that invites you to pause.\n\n"
        f"Now available at P.Forbes Art. 🖼️"
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
