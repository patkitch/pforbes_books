"""Artist-controlled descriptions for Vincent's original artwork.

Pure formatting only: no WooCommerce calls, product creation, or artist-story rewriting.
"""

import re
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any, Mapping


CANVAS_LABELS = {
    "traditional": "Traditional / Slim",
    "gallery": "Gallery / Deep Edge",
    "museum": "Museum / Ultra-Deep",
    "flat": "Flat Panel / Board",
}

STYLE_ADJECTIVES = {
    "abstract": "abstract",
    "abstract impressionism": "abstract impressionist",
    "impressionism": "impressionist",
    "realism": "realist",
    "expressionism": "expressionist",
    "surrealism": "surrealist",
    "minimalism": "minimalist",
}


def _text(data: Mapping[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip()


def _measurement(data: Mapping[str, Any], key: str) -> str:
    value = _text(data, key)
    if not value:
        raise ValueError(f"Missing measurement: {key}")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid measurement: {key}") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"Measurement must be greater than zero: {key}")
    return format(number.normalize(), "f")


def _medium_phrase(medium: str) -> tuple[str, str | None]:
    """Return a natural artwork noun phrase and any explicitly named support."""
    if " on " not in medium.lower():
        base, support = medium.strip(), None
    else:
        i = medium.lower().index(" on ")
        base, support = medium[:i].strip(), medium[i + 4 :].strip()
    known = {
        "acrylic": "acrylic painting",
        "acrylics": "acrylic painting",
        "oil": "oil painting",
        "oils": "oil painting",
        "watercolor": "watercolor painting",
        "watercolour": "watercolour painting",
        "gouache": "gouache painting",
    }
    return known.get(base.lower(), "artwork"), support


def _story_paragraphs(story: str) -> str:
    """Preserve the artist's words, line breaks, and paragraph spacing safely."""
    if not story:
        return ""
    normalized = story.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = []
    for block in re.split(r"\n\s*\n", normalized):
        block = block.strip()
        if block:
            paragraphs.append("<p>" + escape(block).replace("\n", "<br>") + "</p>")
    return "\n".join(paragraphs)


def generate_original_artwork_descriptions(intake: Mapping[str, Any]) -> dict[str, str]:
    """Generate short text and clean HTML without section headings.

    Vincent's optional story-polishing step happens before this function.
    Here the story is only escaped and formatted, never rewritten.
    """
    title = _text(intake, "title")
    style = _text(intake, "style")
    medium = _text(intake, "medium")
    if not title or not style or not medium:
        raise ValueError("Title, style, and medium are required")

    width = _measurement(intake, "width")
    height = _measurement(intake, "height")
    profile = _text(intake, "canvas_profile").lower()
    if profile not in CANVAS_LABELS:
        raise ValueError("Choose a valid canvas profile")
    framed = intake.get("framed")
    if not isinstance(framed, bool):
        raise ValueError("framed must be True or False")

    story = _text(intake, "story_notes")
    style_adjective = STYLE_ADJECTIVES.get(style.lower())
    medium_noun, support = _medium_phrase(medium)

    if medium_noun == "artwork":
        kind = "original artwork"
        style_note = f" in the {style} style"
        medium_note = f" made with {medium}"
        concise = f"Original {width} × {height}-inch artwork in {medium}"
        if style_adjective:
            concise = f"Original {width} × {height}-inch {style_adjective} artwork in {medium}"
        else:
            concise += f", {style} style"
    else:
        descriptor = f"{style_adjective} " if style_adjective else ""
        kind = f"original {descriptor}{medium_noun}"
        style_note = "" if style_adjective else f" in the {style} style"
        medium_note = ""
        concise = f"Original {width} × {height}-inch {descriptor}{medium_noun}"

    if support:
        kind += f" on {support}"
        concise += f" on {support}"
    elif medium_noun != "artwork" and profile in ("traditional", "gallery", "museum"):
        profile_words = {
            "traditional": "slim-profile",
            "gallery": "gallery-profile",
            "museum": "museum-profile",
        }
        support_phrase = f"{profile_words[profile]} canvas"
        kind += f" on {support_phrase}"
        concise += f" on {support_phrase}"

    intro = (
        f"<p><strong>{escape(title)}</strong> is an "
        f"{escape(kind)}{escape(style_note)}{escape(medium_note)}.</p>"
    )

    specs = [
        ("Medium", medium),
        ("Style", style),
        ("Size", f"{width} × {height} inches"),
        ("Canvas", CANVAS_LABELS[profile]),
        ("Framing", "Framed" if framed else "Unframed"),
    ]
    if framed:
        frame_width = _measurement(intake, "frame_width")
        frame_height = _measurement(intake, "frame_height")
        specs.append(("Outside frame size", f"{frame_width} × {frame_height} inches"))

    # A single compact paragraph, not H3 headings or a bulleted specification list.
    specs_html = "<p><small>" + "<br>".join(
        f"<strong>{escape(label)}:</strong> {escape(value)}"
        for label, value in specs
    ) + "</small></p>"

    long_description = "\n".join(
        part for part in (intro, _story_paragraphs(story), specs_html) if part
    )
    short_description = concise + ". " + ("Framed." if framed else "Unframed.")
    return {
        "short_description": short_description,
        "long_description": long_description,
    }
