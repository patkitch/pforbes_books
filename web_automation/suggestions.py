
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
    subject_type = _clean_text(
        intake.get("subject_type", "visual")
    ).lower()

    if subject_type not in ("visual", "theme"):
        subject_type = "visual"

    story_notes = _clean_text(intake.get("story_notes", ""))
    notes_for_agent = _clean_text(
        intake.get("notes_for_agent", "")
    )

    # Fallbacks
    base_title = title or "Untitled"
    subject_phrase = subject or "fine art"
    medium_phrase = medium or "original acrylic painting"

    # Identify the original artwork medium.
    # Do not assume every artwork is an acrylic painting.
    medium_lower = medium.lower()

    if "digital" in medium_lower or "procreate" in medium_lower:
        if "procreate" in medium_lower:
            artwork_medium = "original digital artwork created in Procreate"
        else:
            artwork_medium = "original digital artwork"
    elif "acrylic" in medium_lower:
        if "canvas" in medium_lower:
            artwork_medium = "original acrylic painting on canvas"
        else:
            artwork_medium = "original acrylic painting"
    elif "watercolor" in medium_lower:
        artwork_medium = "original watercolor painting"
    elif "oil" in medium_lower:
        artwork_medium = "original oil painting"
    else:
        artwork_medium = "original artwork"


    print_options_text = (
        "<h3>Available Print Options</h3>"
        "<ul>"
        "<li><strong>8×10 white mat</strong> — 4×6 print</li>"
        "<li><strong>11×14 white mat</strong> — 8×10 print</li>"
        "<li><strong>11×14 Print Only</strong> — No mat</li>"
        "</ul>"
    )


    # --- Title suggestions ---
    titles: List[str] = [
        f"{base_title} | Open Edition Giclée Fine Art Print by P. Forbes",
        f"{base_title} | Giclée Fine Art Print",
        f"{base_title} | Open Edition Fine Art Print",
    ]




    # --- Short descriptions ---
    # Use the original artwork's medium accurately.
    shorts: List[str] = [
        (
            f'Open edition Giclée fine art print of "{base_title}", '
            f'reproduced from an {artwork_medium} by P. Forbes.'
        ),
        (
            f'"{base_title}" is available as a Giclée fine art print '
            f'of an {artwork_medium} by P. Forbes, '
            f'with matted and unmatted options.'
        ),
        (
            f'A Giclée fine art reproduction of an {artwork_medium} '
            f'by P. Forbes, titled "{base_title}".'
        ),
    ]



    # Add artwork-specific context to the third suggestion.
    if subject:
        clean_subject = subject.strip().rstrip(".")

        if subject_type == "visual":


            visual_phrase = clean_subject
            if not clean_subject.startswith(("Kansas ",)):
                visual_phrase = clean_subject[0].lower() + clean_subject[1:]



            # Add an article for common singular descriptions.
            if not visual_phrase.startswith(("a ", "an ", "the ")):
                if visual_phrase.startswith(("abstract portrait", "ocean")):
                    visual_phrase = "an " + visual_phrase
                elif visual_phrase.startswith(("portrait", "fox", "bird")):
                    visual_phrase = "a " + visual_phrase

            shorts[2] += (
                f" The artwork features {visual_phrase}."
            )

        elif subject_type == "theme":
            theme_phrase = clean_subject[0].lower() + clean_subject[1:]
            shorts[2] += f" Its theme is {theme_phrase}."






    # --- Long descriptions ---
    # Preserve the artist's original story in every choice.
    longs: List[str] = []

    if story_notes:
        longs = [
            (
                f'{story_notes}\n\n'

                f'This {artwork_medium} by P. Forbes '
                f'is available as an open edition Giclée fine art print.'

            ),
            (
                f'Behind "{base_title}" is a personal story:\n\n'
                f'{story_notes}\n\n'
                f'This artwork is reproduced as a Giclée fine art print.'
            ),
            (

                f'Artist\'s story — "{base_title}"\n\n'
                f'{story_notes}'
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


    # Include the available print sizes in every long description.
    longs = [
        f"{description}\n\n{print_options_text}"
        for description in longs
    ]



    # --- Image alt text ---
    # Use visual subjects only when explicitly identified.
    # Never treat an artwork's theme as a visible object.
    alts: List[str] = []

    if subject and subject_type == "visual":
        clean_subject = subject.strip()

        alts = [
            f'{clean_subject} in "{base_title}" by P. Forbes.',
            f'"{base_title}" by P. Forbes. Subject: {clean_subject}.',
            f'{clean_subject} depicted in "{base_title}" by P. Forbes.',
        ]
    else:
        alts = [
            f'"{base_title}", {artwork_medium} by P. Forbes.',
            f'Original artwork titled "{base_title}" by P. Forbes.',
            f'"{base_title}" by P. Forbes.',
        ]




    return {
        "titles": titles,
        "short_descriptions": shorts,
        "long_descriptions": longs,
        "alt_texts": alts,
    }
