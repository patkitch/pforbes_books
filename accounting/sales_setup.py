"""One-time, repeatable local-test Chart of Accounts sales organization.

Keeps original Account primary keys (and therefore all existing JournalLine links).
Refuses to run when the local data no longer matches the user-approved mapping.
No changes to any non-sales accounts.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Account


# (original number, new number, expected name)
EXISTING = (
    ("4005", "4011", "Original Art Sales"),
    ("4006", "4012", "Print Sales"),
    ("4003", "4013", "Gallery Commission"),
)
PARENT = ("4010", "Sales Income")
NEW_CHILDREN = (
    ("4014", "Website Sales"),
    ("4015", "Commissioned Artwork Sales"),
)


@transaction.atomic
def organize_sales_income():
    """Validate entire mapping first; apply atomically; safe to repeat.

    The account number may be edited; its ID stays unchanged. The parent
    connection of posted accounts changes only as part of this explicit,
    approved one-time COA reorganization. No posted lines are changed.
    """
    accounts = {
        a.number: a for a in Account.objects.select_for_update().all()
    }
    changes = []
    selected = []

    def validate_account(account, label):
        if account.account_type != "income":
            raise ValidationError(f"{label} must be an Income account.")
        if not account.is_active:
            raise ValidationError(f"{label} is inactive; review it before organizing sales.")

    for old_no, new_no, expected in EXISTING:
        old = accounts.get(old_no)
        new = accounts.get(new_no)
        if old and new:
            raise ValidationError(
                f"Both {old_no} and {new_no} exist. No sales accounts were changed."
            )
        account = old or new
        if account is None:
            raise ValidationError(
                f"Required existing sales account {old_no} ({expected}) is missing."
            )
        if account.name != expected:
            raise ValidationError(
                f"Account {account.number} is named {account.name!r}; expected {expected!r}."
            )
        validate_account(account, expected)
        selected.append((account, new_no))

    parent = accounts.get(PARENT[0])
    if parent is not None:
        validate_account(parent, "Sales Income")
        if parent.name != PARENT[1] or parent.parent_id is not None:
            raise ValidationError("4010 must be a top-level Sales Income parent.")
        if parent.journal_lines.exists():
            raise ValidationError("4010 has journal activity; it cannot be a subtotal-only parent.")

    for no, name in NEW_CHILDREN:
        account = accounts.get(no)
        if account:
            validate_account(account, name)
            if account.name != name:
                raise ValidationError(f"Account {no} already exists as {account.name!r}.")
            if account.journal_lines.exists() and parent is None:
                raise ValidationError(
                    f"Existing account {no} has transactions but no Sales Income parent."
                )

    # Existing sales accounts must not already belong to another hierarchy.
    for account, new_no in selected:
        if account.parent_id and (parent is None or account.parent_id != parent.pk):
            raise ValidationError(
                f"Account {account.number} has a different parent. Review before reorganizing."
            )
        if account.children.exists():
            raise ValidationError(
                f"Account {account.number} already has child accounts. Review before reorganizing."
            )

    if parent is None:
        parent = Account.objects.create(
            number=PARENT[0], name=PARENT[1], account_type="income",
            normal_balance="credit", memo="Sales subtotal parent; post to child accounts.",
        )
        changes.append("Created 4010 — Sales Income")
    for account, new_no in selected:
        fields = []
        if account.number != new_no:
            account.number = new_no
            fields.append("number")
        if account.parent_id != parent.pk:
            account.parent = parent
            fields.append("parent")
        if fields:
            account.save(update_fields=fields)
            changes.append(f"Updated {new_no} — {account.name}")

    for number, name in NEW_CHILDREN:
        account = accounts.get(number)
        if account is None:
            Account.objects.create(
                number=number, name=name, account_type="income",
                normal_balance="credit", parent=parent,
            )
            changes.append(f"Created {number} — {name}")
        elif account.parent_id != parent.pk:
            if account.parent_id is not None:
                raise ValidationError(
                    f"Account {number} has a different parent; refusing to move it."
                )
            account.parent = parent
            account.save(update_fields=["parent"])
            changes.append(f"Linked {number} — {name} to Sales Income")

    return changes
