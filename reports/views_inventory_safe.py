from django.contrib import messages
from django.http import (
    HttpResponseBadRequest,
    HttpResponseNotFound,
    HttpResponseRedirect,
)
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView

from django_ledger.models import EntityModel
from django_ledger.models.items import ItemTransactionModel
from django_ledger.views.mixins import DjangoLedgerSecurityMixIn


class SafeInventoryRecountView(DjangoLedgerSecurityMixIn, DetailView):
    """
    Drop-in replacement for django_ledger.views.inventory.InventoryRecountView,
    but with one critical difference:

    - We NEVER call EntityModel.update_inventory(commit=True)

    Why:
    The stock Django Ledger view will overwrite ItemModel.inventory_received
    and ItemModel.inventory_received_value using whatever the "counted"
    math thinks is correct in this moment.

    In your workflow, that blew away real costs/qty for originals and prints.

    This safe version:
    - Still shows you the comparison table.
    - Still lets you "Recount Inventory" (refresh numbers).
    - Ignores ?confirm=1 so it CANNOT auto-write to ItemModel.
    """

    template_name = 'django_ledger/inventory/inventory_recount.html'
    http_method_names = ['get']
    slug_url_kwarg = 'entity_slug'

    def get_queryset(self):
        if not hasattr(self, 'queryset', None):
            self.queryset = EntityModel.objects.for_user(
                user_model=self.request.user
            )
        return super().get_queryset()

    def counted_inventory(self):
        # "What the system thinks is true from ItemTransactionModel rollups"
        return ItemTransactionModel.objects.inventory_count(
            entity_model=self.AUTHORIZED_ENTITY_MODEL
        )

    def recorded_inventory(self, queryset=None, as_values=True):
        # "What is saved in ItemModel snapshot fields right now"
        entity_model: EntityModel = self.AUTHORIZED_ENTITY_MODEL
        recorded_qs = entity_model.recorded_inventory(item_qs=queryset)
        return recorded_qs

    def get_context_data(self, adjustment=None, counted_qs=None, recorded_qs=None, **kwargs):
        self.object = self.get_object()
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Inventory Recount')
        context['header_title'] = _('Inventory Recount')

        recorded_qs = self.recorded_inventory() if not recorded_qs else recorded_qs
        counted_qs = self.counted_inventory() if not counted_qs else counted_qs

        # EntityModel.inventory_adjustment() basically diffs counted vs recorded
        adjustment = EntityModel.inventory_adjustment(counted_qs, recorded_qs) if not adjustment else adjustment

        context['count_inventory_received'] = counted_qs
        context['current_inventory_levels'] = recorded_qs
        context['inventory_adjustment'] = [
            (k, v) for k, v in adjustment.items() if any(v.values())
        ]

        # Tell template whether updates are currently allowed (we will set False)
        context['allow_inventory_writeback'] = False

        return context

    def get(self, request, *args, **kwargs):
        """
        In the stock view, hitting ?confirm=1 would immediately call update_inventory()
        which mutates ItemModel snapshot quantities & cost.

        We are going to BLOCK that behavior. We'll keep the UX message but not do the write.
        """

        confirm = self.request.GET.get('confirm')

        if confirm:
            # Try to coerce to int just to preserve the same behavior for bad input
            try:
                confirm = int(confirm)
            except (TypeError, ValueError):
                return HttpResponseBadRequest('Invalid confirm code.')
            finally:
                if confirm not in [0, 1]:
                    return HttpResponseNotFound('Invalid confirm code.')

            # DO NOT WRITE ANYTHING.
            messages.add_message(
                request,
                level=messages.WARNING,
                message=(
                    'Snapshot NOT auto-updated. '
                    'This install uses protected inventory. '
                    'Use the Inventory Reconciliation CSV under Admin → Reports '
                    'to repair items instead.'
                ),
                extra_tags='is-warning'
            )

            return HttpResponseRedirect(
                redirect_to=reverse(
                    'safe-inventory-recount',
                    kwargs={'entity_slug': self.kwargs['entity_slug']}
                )
            )

        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)
