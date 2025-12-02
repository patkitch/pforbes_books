from typing import Dict, List


def _clean_text(value: str) -> str:
    return (value or "").strip()


def generate_product_suggestions(intake: Dict) -> Dict[str, List[str]]:
    """
    Given raw intake data from NewProductForm, return suggestion lists for:
      - titles
      - short_descriptions
      - long_descriptions
      - alt_texts

    This is Pauly's 'brain' for Step 2 (but generic, for all automation).
    """
    title = _clean_text(intake.get("title", ""))
    medium = _clean_text(intake.get("medium", ""))
    subject = _clean_text(intake.get("subject", ""))
    story_notes = _clean_text(intake.get("story_notes", ""))
    notes_for_agent = _clean_text(intake.get("notes_for_agent", ""))

    # Fallbacks
    base_title = title or "Untitled"
    subject_phrase = subject or "impressionist landscape"
    medium_phrase = medium or "original acrylic painting"

    # --- Title suggestions ---
    titles: List[str] = []

    # 1) Classic P.Forbes art store style
    titles.append(f"{base_title} | Open Edition Giclée Matted Print by P. Forbes")

    # 2) Simpler format, better for SEO/product list
    titles.append(f"{base_title} – Giclée Matted Print by P. Forbes")

    # 3) Subject-emphasis format if we know the subject
    if subject:
        titles.append(
            f"{base_title} | {subject_phrase} | Open Edition Giclée Print by P. Forbes"
        )
    else:
        titles.append(
            f"{base_title} | Fine Art Giclée Matted Print by P. Forbes"
        )

    # --- Short descriptions (1–2 sentences max) ---
    shorts: List[str] = []

    shorts.append(
        f"Open edition matted Giclée print of an {medium_phrase}. "
        f"Two sizes, ready to frame and add warmth to your space."
    )

    shorts.append(
        f"A {subject_phrase} captured in rich color and texture, "
        f"offered as an open edition Giclée matted print in two sizes."
    )

    shorts.append(
        f"Printed from an {medium_phrase}, this open edition Giclée matted print "
        f"brings a touch of P.Forbes Art to your home or office."
    )

    # --- Long descriptions (can include story notes if present) ---
    longs: List[str] = []
    if story_notes:
        longs.append(
            f"\"{base_title}\" began as {medium_phrase.lower()}, inspired by {subject_phrase}. "
            f"{story_notes.strip()} "
            f"This open edition matted Giclée print is available in two sizes, ready to frame."
        )
        longs.append(
            f"This piece, titled \"{base_title}\", reflects P. Forbes’ impressionist approach to {subject_phrase}. "
            f"{story_notes.strip()} "
            f"Each open edition Giclée print is matted and prepared in two standard sizes."
        )
    else:
        longs.append(
            f"\"{base_title}\" is an {medium_phrase.lower()} rendered in P. Forbes’ impressionist style. "
            f"This open edition Giclée matted print is available in two sizes, ready to frame and enjoy."
        )
        longs.append(
            f"Soft color and texture bring \"{base_title}\" to life. "
            f"Reproduced as an open edition matted Giclée print, it comes in two sizes to suit your space."
        )

    # Third long description: hybrid of subject + medium + a hint of emotion
    longs.append(
        f"In this work, \"{base_title}\", {subject_phrase} is expressed through layered color and brushwork. "
        f"As an open edition matted Giclée print, it offers an accessible way to live with original art."
    )

    # --- Alt text suggestions (for accessibility + SEO) ---
    alts: List[str] = []

    if subject:
        alts.append(
            f"\"{base_title}\" {subject_phrase} painting by P. Forbes, available as a matted Giclée art print."
        )
        alts.append(
            f"Impressionist {subject_phrase} titled \"{base_title}\" by P. Forbes, reproduced as an open edition Giclée print."
        )
    else:
        alts.append(
            f"\"{base_title}\" painting by P. Forbes, reproduced as an open edition matted Giclée art print."
        )
        alts.append(
            f"Impressionist artwork titled \"{base_title}\" by P. Forbes, available as a matted Giclée print."
        )

    alts.append(
        f"Wall art print of \"{base_title}\" by P. Forbes, open edition matted Giclée suitable for home decor."
    )

    return {
        "titles": titles,
        "short_descriptions": shorts,
        "long_descriptions": longs,
        "alt_texts": alts,
    }
