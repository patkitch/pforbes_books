from django.db import models, transaction
from django.utils.text import slugify
from django.utils.timezone import now
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import DecimalField

from django_ledger.models import ItemTransactionModel
from django_ledger.models.entity import EntityModel
from django_ledger.models.items import ItemModel

User = get_user_model()


class Location(models.Model):
    # NEW: keep a clear link to the entity the location lives under
    entity = models.ForeignKey(EntityModel, on_delete=models.PROTECT, related_name="locations")
    # BACK TO TEXT: 'name' should be a label (Studio, Gallery, Offsite)
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    entity = models.ForeignKey(
    EntityModel,
    on_delete=models.PROTECT,
    related_name="locations",
    null=True,   # <- add
    blank=True,  # <- add (optional, just for admin form)
)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Location"
        verbose_name_plural = "Locations"

    def __str__(self):
        return self.name


class ItemStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    SOLD = "sold", "Sold"
    DAMAGED = "damaged", "Damaged"
    MISSING = "missing", "Missing"
    IN_TRANSFER = "in_transfer", "In Transfer"


class StockAllocation(models.Model):
    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT, related_name="stockops_allocations")
    # REVERT: point to Location (int PK), not EntityModel (uuid)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="stockops_allocations")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    status = models.CharField(max_length=20, choices=ItemStatus.choices, default=ItemStatus.AVAILABLE)
    note = models.CharField(max_length=300, blank=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stock Allocation"
        verbose_name_plural = "Stock Allocations"

    def __str__(self):
        return f"{self.item.name} @ {self.location.name} = {self.quantity}"

    @staticmethod
    def on_hand_qty(item) -> Decimal:
        # (Leaving your logic; we can refine later)
        q = Decimal("0")
        try:
            qs = ItemModel.objects.inventory_count(entity_model=item.entity_id)
            row = None
            for r in qs:
                k = r.get("item_model_id") or r.get("item_model__uuid") or r.get("item_model")
                if k == item.uuid:
                    row = r
                    break
            if row:
                v = row.get("quantity_onhand") or row.get("qty_on_hand") or row.get("onhand")
                if v is not None:
                    q = Decimal(v)
        except Exception:
            pass

        if q == 0:
            agg = (
                ItemTransactionModel.objects
                .filter(
                item_model=item,                    # FK to the same ItemModel instance
                item_model__entity_id=item.entity_id
        )
            .aggregate(
                net=Coalesce(
                    Sum('quantity'),
                    0.0,
                    output_field=DecimalField(max_digits=20, decimal_places=3),
            )
        )
    )   

        return Decimal(agg['net'] or 0).quantize(Decimal('0.001'))

    @staticmethod
    def allocated_total(item: ItemModel) -> Decimal:
        agg = StockAllocation.objects.filter(item=item).aggregate(total=models.Sum("quantity"))
        return (Decimal(agg["total"] or 0)).quantize(Decimal("0.001"))

    @staticmethod
    def unallocated_qty(item: ItemModel) -> Decimal:
        return (StockAllocation.on_hand_qty(item) - StockAllocation.allocated_total(item)).quantize(Decimal("0.001"))

    def clean(self):
        super().clean()
        if self.quantity < 0:
            raise ValidationError("Quantity cannot be negative.")

        current_total = (
            StockAllocation.objects.filter(item=self.item)
            .exclude(pk=self.pk)
            .aggregate(total=models.Sum("quantity"))["total"] or Decimal("0")
        )
        proposed_total = (current_total + (self.quantity or Decimal("0"))).quantize(Decimal("0.001"))
        on_hand = StockAllocation.on_hand_qty(self.item)

        if proposed_total > on_hand:
            raise ValidationError(
                f"Allocation exceeds on-hand. On-hand={on_hand}, proposed total allocation={proposed_total}."
            )


class StockTransfer(models.Model):
    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT, related_name="stockops_transfers")
    # REVERT: Locations, not Entities
    from_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="transfer_from")
    to_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="transfer_to")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)
    created = models.DateTimeField(default=now)

    class Meta:
        verbose_name = "Stock Transfer"
        verbose_name_plural = "Stock Transfers"

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            raise ValidationError("Transfer quantity must be > 0.")
        if self.from_location_id == self.to_location_id:
            raise ValidationError("From/To locations must be different.")
        # BUGFIX: compare item's entity with the locations' entity
        if self.item.entity_id != self.from_location.entity_id or self.item.entity_id != self.to_location.entity_id:
            raise ValidationError("Item entity and Location entity must match.")

        from_alloc, _ = StockAllocation.objects.get_or_create(item=self.item, location=self.from_location)
        if from_alloc.quantity < self.quantity:
            raise ValidationError(
                f"Not enough allocated at {self.from_location}. "
                f"Available={from_alloc.quantity}, requested move={self.quantity}."
            )

    def apply_transfer(self):
        with transaction.atomic():
            from_alloc, _ = StockAllocation.objects.select_for_update().get_or_create(
                item=self.item, location=self.from_location
            )
            to_alloc, _ = StockAllocation.objects.select_for_update().get_or_create(
                item=self.item, location=self.to_location
            )

            if from_alloc.quantity < self.quantity:
                raise ValidationError(
                    f"Not enough at {self.from_location}. "
                    f"Available={from_alloc.quantity}, requested move={self.quantity}."
                )

            from_alloc.quantity = (from_alloc.quantity - self.quantity).quantize(Decimal("0.001"))
            to_alloc.quantity = (to_alloc.quantity + self.quantity).quantize(Decimal("0.001"))

            from_alloc.full_clean(); to_alloc.full_clean()
            from_alloc.save(); to_alloc.save()

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        self.apply_transfer()


class StatusOverlay(models.Model):
    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT, related_name="stockops_status_overlays")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="stockops_status_overlays")
    status = models.CharField(max_length=20, choices=ItemStatus.choices, default=ItemStatus.AVAILABLE)
    note = models.CharField(max_length=300, blank=True)
    effective = models.DateTimeField(default=now)

    class Meta:
        unique_together = [("item", "location", "status", "effective")]
        verbose_name = "Status Overlay"
        verbose_name_plural = "Status Overlays"

    def __str__(self):
        return f"{self.item.name} @ {self.location} [{self.status}]"


class PendingReceipt(models.Model):
    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT, related_name="stockops_pending_receipts")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="stockops_pending_receipts")
    expected_qty = models.DecimalField(max_digits=12, decimal_places=3)
    expected_date = models.DateField(null=True, blank=True)
    vendor_name = models.CharField(max_length=160, blank=True)
    po_or_bill_ref = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=300, blank=True)
    created = models.DateTimeField(default=now)

    class Meta:
        verbose_name = "Pending Receipt"
        verbose_name_plural = "Pending Receipts"

    def clean(self):
        super().clean()
        if self.expected_qty <= 0:
            raise ValidationError("Expected quantity must be > 0.")
