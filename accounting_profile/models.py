"""Business identity for the single-company accounting test.

This is not multi-company ledger isolation or a credential vault.
Never store complete SSNs/EINs here.
"""
from django.db import models


class BusinessProfile(models.Model):
    SOLE = "sole"
    LLC = "llc"
    CORPORATION = "corporation"
    PARTNERSHIP = "partnership"
    OTHER = "other"
    ENTITY_TYPES = [
        (SOLE, "Sole proprietorship"),
        (LLC, "Limited liability company (LLC)"),
        (CORPORATION, "Corporation"),
        (PARTNERSHIP, "Partnership"),
        (OTHER, "Other"),
    ]
    TAX_IDS = [
        ("none", "Not provided"),
        ("ssn", "SSN (last four only)"),
        ("ein", "EIN (last four only)"),
    ]

    # Single-business v1: do not create a second profile and assume that
    # all journals, bank accounts and customers become company-scoped.
    display_name = models.CharField(max_length=160)
    legal_name = models.CharField(max_length=160, blank=True)
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPES, default=SOLE)
    tax_id_type = models.CharField(max_length=4, choices=TAX_IDS, default="none")
    tax_id_last_four = models.CharField(max_length=4, blank=True)
    address_line_1 = models.CharField(max_length=180, blank=True)
    address_line_2 = models.CharField(max_length=180, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=40, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=80, default="United States")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    industry = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.tax_id_last_four and (
            len(self.tax_id_last_four) != 4 or not self.tax_id_last_four.isascii()
            or not self.tax_id_last_four.isdigit()
        ):
            raise ValidationError({"tax_id_last_four": "Enter only the last four digits."})
        if self.tax_id_type == "none" and self.tax_id_last_four:
            raise ValidationError({"tax_id_last_four": "Choose SSN or EIN, or leave this blank."})

    def __str__(self):
        return self.display_name
