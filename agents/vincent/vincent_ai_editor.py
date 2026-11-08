"""Vincent's optional AI editor for artist-written stories.

No request is made on import. No WooCommerce access or product writes.
The API key is read from OPENAI_API_KEY (for local use, from .env).
"""

import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI


EDITOR_INSTRUCTIONS = (
    "You are a careful copy editor for an original-artwork artist's statement. "
    "Correct grammar, spelling, punctuation, and awkward sentence structure. "
    "Keep the artist's first- or second-person point of view, natural voice, imagery, "
    "meaning, and emotional restraint. Do not invent details, claims, feelings, "
    "interpretations, or sales language. Do not add a title, notes, or quotation marks. "
    "Return only the edited statement, preserving paragraph breaks where practical."
)


def polish_artist_story(story: str, *, client: Optional[OpenAI] = None) -> str:
    """Return a minimally polished artist story, or an empty string if none.

    Raises an exception on API errors so the calling view can offer the artist's
    original text rather than silently replacing it with something unexpected.
    This function makes one billable API request when story is nonempty.
    """
    if not isinstance(story, str):
        raise TypeError("story must be a string")
    story = story.strip()
    if not story:
        return ""

    if client is None:
        load_dotenv()
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not configured")
        client = OpenAI()

    response = client.responses.create(
        model="gpt-6-luna",
        instructions=EDITOR_INSTRUCTIONS,
        input=story,
        max_output_tokens=700,
    )
    revised = (response.output_text or "").strip()
    if not revised:
        raise RuntimeError("AI editor returned no text")
    return revised
