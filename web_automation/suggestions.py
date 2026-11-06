
from typing import Dict, List


def _clean_text(value: str) -> str:
    return (value or "").strip()


def generate_product_suggestions(intake: Dict) -> Dict[str, List[str]]:
    """
    Generate suggested titles, descriptions, and alt text
    for P. Forbes Art Giclee fine art prints.

    Supports three print options:
    - 11x14 white mat (8x10 print)
    - 8x10 white mat (4x6 print)
    - 11x14 Print Only (no mat)
    """

    title = _clean_text(intake.get("title", ""))
    medium = _clean_text(intake.get("medium", ""))
    subject = _clean_text(intake.get("subject", ""))
    story_notes = _clean_text(intake.get("story_notes", ""))
    notes_for_agent = _clean_text(
        intake.get("notes_for_agent", "")
    )

    # Fallbacks
    base_title = title or "Untitled"
    subject_phrase = subject or "fine art"
    medium_phrase = medium or "original acrylic painting"

    print_options_text = (
        "Available in three print options: "
        "8x10 with white mat (4x6 image), "
        "11x14 with white mat (8x10 image), "
        "or 11x14 unmatted."
    )

    # --- Title suggestions ---
    titles: List[str] = [
        f"{base_title} | Open Edition Giclée Fine Art Print by P. Forbes",
        f"{base_title} | Giclée Fine Art Print",
        f"{base_title} | Open Edition Fine Art Print",
    ]

    # --- Short descriptions ---
    shorts: List[str] = [
        (
            f"Open edition Giclée fine art print reproduced "
            f"from an {medium_phrase}. "
            f"{print_options_text}"
        ),
        (
            f"A fine art reproduction featuring {subject_phrase}, "
            f"with the color and texture of the original artwork. "
            f"{print_options_text}"
        ),
        (
            f"Bring \"{base_title}\" into your space "
            f"with an open edition Giclée fine art print. "
            f"{print_options_text}"
        ),
    ]

    # --- Long descriptions ---
    longs: List[str] = []

    if story_notes:
        longs.append(
            f"\"{base_title}\" is based on an "
            f"{medium_phrase.lower()}. "
            f"{story_notes} "
            f"{print_options_text}"
        )

        longs.append(
            f"\"{base_title}\" explores {subject_phrase}. "
            f"{story_notes} "
            f"{print_options_text}"
        )

    else:
        longs.append(
            f"\"{base_title}\" is reproduced from an "
            f"{medium_phrase.lower()}. "
            f"{print_options_text}"
        )

        longs.append(
            f"\"{base_title}\" features {subject_phrase}, "
            f"presented as an open edition Giclée fine art print. "
            f"{print_options_text}"
        )

    longs.append(
        f"\"{base_title}\" is a fine art reproduction "
        f"of an original work by P. Forbes. "
        f"{print_options_text}"
    )

    # --- Image alt text ---
    # Describe the artwork rather than the purchasing options.
    alts: List[str] = []

    if subject:
        alts.append(
            f"\"{base_title}\" depicting {subject_phrase}, "
            f"original artwork by P. Forbes."
        )
        alts.append(
            f"Fine art image of {subject_phrase} "
            f"from \"{base_title}\" by P. Forbes."
        )
    else:
        alts.append(
            f"\"{base_title}\" original artwork by P. Forbes."
        )
        alts.append(
            f"Fine art reproduction of \"{base_title}\" "
            f"by P. Forbes."
        )

    alts.append(
        f"\"{base_title}\" by P. Forbes, "
        f"reproduced as a Giclée fine art print."
    )

    return {
        "titles": titles,
        "short_descriptions": shorts,
        "long_descriptions": longs,
        "alt_texts": alts,
    }
