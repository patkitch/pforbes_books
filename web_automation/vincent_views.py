"""Vincent original-artwork intake, preview, and read-only draft review.

No write requests to WooCommerce are performed here.
"""

from decimal import Decimal
from .models import VincentDraftSubmission
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from agents.vincent.descriptions import generate_original_artwork_descriptions
from agents.vincent.vincent_ai_editor import polish_artist_story
from agents.vincent.tags import generate_original_artwork_tags
from agents.vincent.vincent_product_creator import create_original_artwork_draft
from agents.pauly.core import woo_get
from .vincent_forms import VincentOriginalArtworkForm

from .vincent_creation_service import get_vincent_artwork_snapshot



SESSION_INTAKE_KEY = "vincent_original_artwork_intake"
SESSION_POLISHED_KEY = "vincent_polished_artist_story"
SESSION_EDITOR_WARNING_KEY = "vincent_editor_warning"
SESSION_SUBMISSION_KEY = "vincent_draft_submission_id"


def _session_safe_data(cleaned_data):
    """Convert Django Decimal inputs for JSON-backed session storage."""
    return {
        key: (str(value) if isinstance(value, Decimal) else value)
        for key, value in cleaned_data.items()
    }



@require_http_methods(["GET", "POST"])
def vincent_intake(request):
    """Collect artwork data without altering Pauly's print intake."""
    if request.method == "POST":
        form = VincentOriginalArtworkForm(request.POST)
        if form.is_valid():
            intake = _session_safe_data(form.cleaned_data)
            request.session[SESSION_INTAKE_KEY] = intake

            # Create a new submission record for this artwork.
            
            submission = VincentDraftSubmission.objects.create(
                artwork_snapshot=intake.copy()
            )

            request.session[SESSION_SUBMISSION_KEY] = str(submission.id)

            # Polish the artist's story once per valid submission.
            original_story = (intake.get("story_notes") or "").strip()
            request.session[SESSION_POLISHED_KEY] = original_story
            request.session[SESSION_EDITOR_WARNING_KEY] = ""

            if original_story:
                try:
                    request.session[SESSION_POLISHED_KEY] = polish_artist_story(
                        original_story
                    )
                except Exception:
                    request.session[SESSION_EDITOR_WARNING_KEY] = (
                        "AI editing was unavailable. "
                        "Your original story is shown unchanged."
                    )
            
            # Preserve the polished story with the artwork submission.
            snapshot = dict(intake)
            snapshot["polished_story_notes"] = request.session.get(
                SESSION_POLISHED_KEY, original_story
            )
            submission.artwork_snapshot = snapshot
            submission.save(update_fields=["artwork_snapshot", "updated_at"])

            return redirect("web_automation:vincent_preview")
    else:
        form = VincentOriginalArtworkForm(
            initial=request.session.get(SESSION_INTAKE_KEY, {})
        )

    return render(
        request,
        "web_automation/vincent_intake.html",
        {"form": form},
    )





@require_http_methods(["GET"])
def vincent_preview(request):
    """Show descriptions and prospective tags; do not create a draft."""
    intake = request.session.get(SESSION_INTAKE_KEY)
    if not intake:
        return redirect("web_automation:vincent_intake")

    # Build descriptions from a copy, leaving the original intake intact.
    preview_intake = dict(intake)
    preview_intake["story_notes"] = request.session.get(
        SESSION_POLISHED_KEY, intake.get("story_notes", "")
    )
    descriptions = generate_original_artwork_descriptions(preview_intake)
    tags = generate_original_artwork_tags(intake)
    return render(
        request,
        "web_automation/vincent_preview.html",
        {
            "intake": intake,
            "descriptions": descriptions,
            "tags": tags,
            "editor_warning": request.session.get(SESSION_EDITOR_WARNING_KEY, ""),
        },
    )


@require_http_methods(["GET"])
def vincent_draft_review(request):
    """Preview a WooCommerce draft plan with live read-only tag/duplicate checks.

    This endpoint has no write path. It does not create or change products.
    The URL and template will be connected in separate, reviewed steps.
    """
    intake = request.session.get(SESSION_INTAKE_KEY)
    if not intake:
        return redirect("web_automation:vincent_intake")

    preview_intake = dict(intake)
    preview_intake["story_notes"] = request.session.get(
        SESSION_POLISHED_KEY, intake.get("story_notes", "")
    )
    descriptions = generate_original_artwork_descriptions(preview_intake)

    try:
        plan = create_original_artwork_draft(
            preview_intake,
            description=descriptions["long_description"],
            short_description=descriptions["short_description"],
            woo_get=woo_get,
            dry_run=True,
        )
    except (ValueError, RuntimeError, OSError):
        # Don't expose credentials, API details, or internal tracebacks.
        return render(
            request,
            "web_automation/vincent_draft_review.html",
            {"intake": intake, "error": "Draft review could not be completed. Check the artwork category and WooCommerce connection."},
        )

    return render(
        request,
        "web_automation/vincent_draft_review.html",
        {"intake": intake, "plan": plan, "product": plan["product_payload"]},
    )

@require_http_methods(["GET"])
def vincent_confirm_draft(request):
    """Read-only confirmation screen. No WooCommerce POST path exists."""
    
    submission_id = request.session.get(SESSION_SUBMISSION_KEY)
    if not submission_id:
        return redirect("web_automation:vincent_intake")

    try:
        preview_intake = get_vincent_artwork_snapshot(submission_id)
    except (VincentDraftSubmission.DoesNotExist, ValueError, TypeError):
        return render(
            request,
            "web_automation/vincent_confirm_draft.html",
            {"error": "The saved artwork submission is unavailable."},
        )

    intake = preview_intake

    descriptions = generate_original_artwork_descriptions(preview_intake)

    try:
        plan = create_original_artwork_draft(
            preview_intake,
            description=descriptions["long_description"],
            short_description=descriptions["short_description"],
            woo_get=woo_get,
            dry_run=True,
        )
    except (ValueError, RuntimeError, OSError):
        return render(
            request,
            "web_automation/vincent_confirm_draft.html",
            {
                "intake": intake,
                "error": "Confirmation review is unavailable. Check the artwork category and WooCommerce connection.",
            },
        )

    
    return render(
        request,
        "web_automation/vincent_confirm_draft.html",
        {
            "intake": intake,
            "plan": plan,
            "product": plan["product_payload"],
            "submission_id": request.session.get(SESSION_SUBMISSION_KEY),
        },
    )

