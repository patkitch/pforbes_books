
"""Prevent repeated Vincent draft-creation requests."""


from django.db import transaction
from django.utils import timezone

from .models import VincentDraftSubmission



def claim_submission(submission_id):
    """
    Allow only one request to claim a pending submission.

    Returns True for the winning request.
    Returns False if the submission is missing or already claimed.
    """
    with transaction.atomic():
        updated = VincentDraftSubmission.objects.filter(
            pk=submission_id,
            status=VincentDraftSubmission.Status.PENDING,
        ).update(
            status=VincentDraftSubmission.Status.PROCESSING,
        )

    return updated == 1

def mark_submission_completed(submission_id, woo_product_id):
    """Record a successfully created WooCommerce draft."""
    if not isinstance(woo_product_id, int) or woo_product_id <= 0:
        raise ValueError("A valid WooCommerce product ID is required.")

    updated = VincentDraftSubmission.objects.filter(
        pk=submission_id,
        status=VincentDraftSubmission.Status.PROCESSING,
    ).update(
        status=VincentDraftSubmission.Status.COMPLETED,
        woo_product_id=woo_product_id,
        error_message="",
        completed_at=timezone.now(),
    )
    return updated == 1


def mark_submission_failed(submission_id, message=""):
    """Record a confirmed failure with no product created."""
    updated = VincentDraftSubmission.objects.filter(
        pk=submission_id,
        status=VincentDraftSubmission.Status.PROCESSING,
    ).update(
        status=VincentDraftSubmission.Status.FAILED,
        error_message=str(message)[:1000],
    )
    return updated == 1


def mark_submission_uncertain(submission_id, message=""):
    """Require manual review when the creation outcome is unknown."""
    updated = VincentDraftSubmission.objects.filter(
        pk=submission_id,
        status=VincentDraftSubmission.Status.PROCESSING,
    ).update(
        status=VincentDraftSubmission.Status.UNCERTAIN,
        error_message=str(message)[:1000],
    )
    return updated == 1

