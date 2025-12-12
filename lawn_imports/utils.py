# lawn_imports/utils.py

from typing import Optional, Tuple

from django_ledger.models import EntityModel, CustomerModel


def get_or_create_dl_customer_for_jobber(
    entity: EntityModel,
    client_name: str,
    client_email: Optional[str] = None,
    client_phone: Optional[str] = None,
) -> Tuple[CustomerModel, bool]:
    """
    Resolve a Django Ledger CustomerModel for a given Jobber client row.

    - First tries to match by entity + customer_name (and email when provided).
    - If not found, creates a new CustomerModel under this entity.

    Returns (customer, created_flag).
    """
    name = (client_name or "").strip()
    email = (client_email or "").strip() or None

    if not name:
        raise ValueError("Jobber row is missing client name; cannot create CustomerModel.")

    qs = CustomerModel.objects.filter(
        entity_model=entity,
        customer_name=name,
    )

    # If email is present, narrow by email as well (case insensitive)
    if email:
        qs = qs.filter(email__iexact=email)

    customer = qs.first()
    created = False

    if not customer:
        customer = CustomerModel.objects.create(
            entity_model=entity,
            customer_name=name,
            email=email,
            phone=client_phone,
        )
        created = True

    return customer, created

