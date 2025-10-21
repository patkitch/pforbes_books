from django_ledger.models import AccountModel

class AccountLookupError(Exception):
    pass

def get_account(entity=None, *, code=None, role=None, name_icontains=None) -> AccountModel:
    """
    Flexible account lookup:
      - Prefer code
      - else by role
      - else by partial name
    Raises AccountLookupError with a helpful message if not found or ambiguous.
    """
    qs = AccountModel.objects.all()
    if entity is not None:
        entity_slug = getattr(entity, "slug", None) or getattr(entity, "entity_slug", None)
        if entity_slug:
            qs = qs.filter(_entity_slug=entity_slug)

    if code:
        try:
            return qs.get(code=code)
        except AccountModel.DoesNotExist:
            raise AccountLookupError(f"No account with code='{code}' for entity='{entity_slug}'.")
        except AccountModel.MultipleObjectsReturned:
            raise AccountLookupError(f"Multiple accounts with code='{code}' for entity='{entity_slug}'.")

    if role:
        matches = list(qs.filter(role=role)[:2])
        if len(matches) == 1:
            return matches[0]
        elif not matches:
            raise AccountLookupError(f"No account with role='{role}' for entity='{entity_slug}'.")
        else:
            raise AccountLookupError(f"Multiple accounts with role='{role}'. Specify code or name.")

    if name_icontains:
        matches = list(qs.filter(name__icontains=name_icontains)[:3])
        if len(matches) == 1:
            return matches[0]
        elif not matches:
            raise AccountLookupError(f"No account with name like '{name_icontains}'.")
        else:
            raise AccountLookupError(f"Multiple accounts match '{name_icontains}'. Specify code.")

    raise AccountLookupError("Provide at least one of: code, role, or name_icontains.")

# accounting/util/account_codes.py
# --- Customer side (A/R) ---
AR_CODE = "1050"               # Recievables
CASH_CODE = "1012"             # Bank Checking  (use this for direct deposits)
UNDEPOSITED_CODE = "1020"      # Undeposited Funds (use if batching bank deposits)
SALES_DISCOUNTS_CODE = "4090"  # Sales Discounts (contra-revenue)

# --- Vendor side (A/P) ---
AP_CODE = "2000"               # Accounts Payable
INVENTORY_CODE = "1100"        # Inventory (general bucket)
# If you later want to split discounts by category, you also have:
INVENTORY_ORIGINALS_CODE = "1110"   # Inventory - Originals
INVENTORY_PRINTS_CODE = "1120"      # Inventory - Prints

