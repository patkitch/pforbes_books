
"""Vincent's controlled WooCommerce draft creation service.

Not connected to the Django creation endpoint yet.
Creation is disabled by default.
"""

from agents.vincent.vincent_product_creator import (
    create_original_artwork_draft,
)

from agents.vincent.descriptions import (
    generate_original_artwork_descriptions,
)

from .models import VincentDraftSubmission

from .vincent_submission_guard import (
    claim_submission,
    mark_submission_completed,
    mark_submission_uncertain,
)


def execute_vincent_creation(
    submission_id,
    intake,
    description,
    short_description,
    *,
    woo_get,
    woo_post,
    enabled=False,
):
    """Create at most one draft for a claimed submission."""

    if not enabled:
        return {
            "status": "disabled",
            "message": "WooCommerce creation is disabled.",
        }
    
    # Retrieve the saved artwork before claiming the submission.
    try:
        intake = get_vincent_artwork_snapshot(submission_id)
        descriptions = generate_original_artwork_descriptions(intake)
        description = descriptions["long_description"]
        short_description = descriptions["short_description"]
    except (VincentDraftSubmission.DoesNotExist, ValueError, TypeError, KeyError):
        return {
            "status": "blocked",
            "message": "The saved artwork details are missing or invalid.",
        }

    if not claim_submission(submission_id):
        return {
            "status": "blocked",
            "message": "Submission is not pending.",
        }

    try:
        result = create_original_artwork_draft(
            intake,
            description=description,
            short_description=short_description,
            woo_get=woo_get,
            woo_post=woo_post,
            dry_run=False,
            confirm_create=True,
        )
    except Exception:
        # The outcome may be uncertain once an external API is involved.
        # Never retry this submission automatically.
        mark_submission_uncertain(
            submission_id,
            "Creation did not complete with a verified result. "
            "Review WooCommerce before taking further action.",
        )
        return {
            "status": "uncertain",
            "message": "Check WooCommerce for a possible draft.",
        }

    
    try:
        completion_saved = mark_submission_completed(
            submission_id,
            result["product_id"],
        )
    except Exception:
        completion_saved = False

    if not completion_saved:
        # WooCommerce returned an ID, but PostgreSQL completion
        # could not be confirmed. Never create the product again.
        try:
            mark_submission_uncertain(
                submission_id,
                f"WooCommerce returned product ID {result['product_id']}, "
                "but completion could not be recorded.",
            )
        except Exception:
            pass

        return {
            "status": "uncertain",
            "product_id": result["product_id"],
            "message": (
                "WooCommerce returned a product ID, but database "
                "confirmation failed. Review the draft before proceeding."
            ),
        }


    return {
        "status": "completed",
        "product_id": result["product_id"],
    }

def get_vincent_artwork_snapshot(submission_id):
    """Retrieve the stored artwork and use its polished story."""
    submission = VincentDraftSubmission.objects.get(pk=submission_id)

    if not submission.artwork_snapshot:
        raise ValueError("This submission has no artwork snapshot.")

    intake = dict(submission.artwork_snapshot)

    if submission.status != VincentDraftSubmission.Status.PENDING:
        raise ValueError("This submission is no longer pending.")

    intake["story_notes"] = intake.get(
        "polished_story_notes",
        intake.get("story_notes", ""),
    )

    return intake

