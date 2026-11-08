"""Conservative, automatic tag suggestions for Vincent original artwork.

This module does not connect to WooCommerce or create tags. The later draft
creation step will resolve these names against existing WooCommerce tags,
reusing matching tag IDs before creating any new tags.
"""

import re
from typing import Any, Mapping


# Only apply these thematic tags when the corresponding word or phrase is
# explicitly present in the artist's input. Do not infer painted objects,
# locations, style, or emotion from an image or a figurative title.
SUBJECT_KEYWORDS = (
    ("ocean", "Ocean Art"),
    ("sea", "Seascape"),
    ("seascape", "Seascape"),
    ("beach", "Beach Art"),
    ("coast", "Coastal Art"),
    ("mountain", "Mountain Art"),
    ("prairie", "Prairie Art"),
    ("landscape", "Landscape Art"),
    ("desert", "Desert Art"),
    ("river", "River Art"),
    ("lake", "Lake Art"),
    ("forest", "Forest Art"),
    ("flower", "Floral Art"),
    ("sunflower", "Floral Art"),
    ("wildlife", "Wildlife Art"),
    ("fox", "Wildlife Art"),
    ("owl", "Wildlife Art"),
    ("bird", "Bird Art"),
    ("storm", "Storm Art"),
    ("sunset", "Sunset Art"),
    ("sunrise", "Sunrise Art"),
    ("winter", "Winter Art"),
    ("snow", "Winter Art"),
    ("kansas", "Kansas Art"),
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _contains(text: str, keyword: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(keyword) + r"s?(?!\w)", text, flags=re.I))


def generate_original_artwork_tags(intake: Mapping[str, Any], *, max_tags: int = 8) -> list[str]:
    """Return distinct tag names based strictly on artist-entered information.

    Style and medium are taken directly from the intake. Optional subject
    phrases may become tags. Descriptive keywords are only recognized when
    explicitly provided in title, subject, or story. Unknown/empty fields
    never cause Vincent to invent a category or meaning.

    This produces *tag names*, not WooCommerce tag IDs. It does not write.
    """
    if max_tags < 1:
        raise ValueError("max_tags must be positive")

    tags: list[str] = []
    seen: set[str] = set()

    def add(label: str) -> None:
        label = _clean(label)
        key = label.casefold()
        if label and key not in seen and len(tags) < max_tags:
            tags.append(label)
            seen.add(key)

    add("Original Artwork")
    add(_clean(intake.get("style")))
    add(_clean(intake.get("medium")))

    subject = _clean(intake.get("subject"))
    if subject:
        # Keep artist-provided subject phrases, but avoid making a whole
        # paragraph into a tag. Do not split on ordinary spaces.
        for phrase in re.split(r"[,;]", subject):
            phrase = _clean(phrase)
            if phrase and len(phrase) <= 40:
                add(phrase)

    artist_text = " ".join(_clean(intake.get(key)) for key in ("title", "subject", "story_notes"))
    for keyword, label in SUBJECT_KEYWORDS:
        if _contains(artist_text, keyword):
            add(label)

    return tags
