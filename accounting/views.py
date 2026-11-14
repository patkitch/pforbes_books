from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Account


@login_required
def chart_of_accounts(request):
    """Read-only COA screen: no changes to ledger or imported records."""
    show_inactive = request.GET.get("inactive") == "1"
    search = request.GET.get("q", "").strip()
    accounts = Account.objects.select_related("parent").order_by("number", "name")
    if not show_inactive:
        accounts = accounts.filter(is_active=True)
    if search:
        from django.db.models import Q
        accounts = accounts.filter(Q(number__icontains=search) | Q(name__icontains=search))
    return render(request, "accounting/chart_of_accounts.html", {
        "accounts": accounts,
        "search": search,
        "show_inactive": show_inactive,
    })
