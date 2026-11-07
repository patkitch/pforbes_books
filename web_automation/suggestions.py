
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
    # Offer three clean choices without repeating all print sizes.
    shorts: List[str] = [
        (
            f'Open edition Giclée fine art print of "{base_title}", '
            f'reproduced from an original work by P. Forbes.'
        ),
        (
            f'"{base_title}" by P. Forbes, available as a '
            f'Giclée fine art print with matted and unmatted options.'
        ),
        (
            f'A reproduction of "{base_title}", '
            f'created as an open edition Giclée fine art print.'
        ),
    ]



    # --- Long descriptions ---
    # Preserve the artist's original story in every choice.
    longs: List[str] = []

    if story_notes:
        longs = [
            (
                f'{story_notes}\n\n'
                f'"{base_title}" is available as an open edition '
                f'Giclée fine art print.'
            ),
            (
                f'Behind "{base_title}" is a personal story:\n\n'
                f'{story_notes}\n\n'
                f'This artwork is reproduced as a Giclée fine art print.'
            ),
            (
                f'Artist\'s story — "{base_title}"\n\n'
                f'{story_notes}\n\n'
                f'Available with matted and unmatted print options.'
            ),
        ]
    else:
        longs = [
            (
                f'"{base_title}" is an original artwork by P. Forbes, '
                f'available as an open edition Giclée fine art print.'
            ),
            (
                f'A fine art reproduction of "{base_title}" '
                f'by P. Forbes, offered with matted and unmatted options.'
            ),
            (
                f'"{base_title}" is reproduced as a Giclée fine art '
                f'print from an original work by P. Forbes.'
            ),
        ]



    # --- Image alt text ---
    # Describe the artwork rather than the print product.
    alts: List[str] = []

    if subject:
        clean_subject = subject.strip()
        clean_subject = clean_subject[0].lower() + clean_subject[1:]

        alts = [
            f'{clean_subject[0].upper() + clean_subject[1:]} '
            f'in "{base_title}" by P. Forbes.',
            f'{clean_subject[0].upper() + clean_subject[1:]} — "{base_title}" by P. Forbes.',
            f'{clean_subject[0].upper() + clean_subject[1:]} depicted in "{base_title}" by P. Forbes.',
        ]
    else:
        alts = [
            f'Original artwork "{base_title}" by P. Forbes.',
            f'"{base_title}", an original painting by P. Forbes.',
            f'Artwork titled "{base_title}" by P. Forbes.',
        ]


    return {
        "titles": titles,
        "short_descriptions": shorts,
        "long_descriptions": longs,
        "alt_texts": alts,
    }
