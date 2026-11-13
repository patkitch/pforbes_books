"""Vincent's future WooCommerce draft-creation endpoint.

SECURITY HOLD: intentionally performs no WooCommerce writes.  The existing
Django staff login, POST-only enforcement and CSRF middleware protect this
endpoint once it is added to urls.py.  Product creation is NOT enabled here.
"""

from django.contrib.admin.views.decorators import staff_member_required
from agents.pauly.core import woo_get, woo_post
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from .vincent_creation_service import execute_vincent_creation


# Safety switch: real WooCommerce creation is disabled.
VINCENT_WOO_CREATION_ENABLED = True


@staff_member_required
@csrf_protect
@require_POST
def vincent_create_draft(request):
    """Create a draft and clear the intake only after confirmed success."""
    if not VINCENT_WOO_CREATION_ENABLED:
        return render(
            request,
            "web_automation/vincent_creation_result.html",
            {
                "status": "disabled",
                "message": "WooCommerce creation is still disabled.",
            },
        )

    from .models import VincentDraftSubmission

    submission_id = request.session.get("vincent_draft_submission_id")

    if not submission_id:
        return HttpResponseForbidden("No Vincent submission was found.")

    try:
        submission = VincentDraftSubmission.objects.get(pk=submission_id)
    except (
        VincentDraftSubmission.DoesNotExist,
        ValueError,
        TypeError,
    ):
        return HttpResponseForbidden(
            "The Vincent submission is invalid or missing."
        )

    if submission.status != VincentDraftSubmission.Status.PENDING:
        return HttpResponseForbidden(
            "This submission is no longer pending."
        )

    result = execute_vincent_creation(
        submission.id,
        None,
        "",
        "",
        woo_get=woo_get,
        woo_post=woo_post,
        enabled=VINCENT_WOO_CREATION_ENABLED,
    )

    if result["status"] == "completed":
        # The artwork is safely recorded in WooCommerce and in the
        # submission record. A new intake should start with a blank form.
        for key in (
            "vincent_original_artwork_intake",
            "vincent_polished_artist_story",
            "vincent_editor_warning",
            "vincent_draft_submission_id",
        ):
            request.session.pop(key, None)

    return render(
        request,
        "web_automation/vincent_creation_result.html",
        {
            "status": result["status"],
            "message": result.get(
                "message",
                "WooCommerce draft created successfully."
                if result["status"] == "completed"
                else "Draft creation requires review.",
            ),
            "product_id": result.get("product_id"),
        },
    )
