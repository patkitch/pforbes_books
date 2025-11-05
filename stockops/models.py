from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.text import slugify
from django.utils.timezone import now

# Read-only imports from Django-Ledger
from django_ledger.models import EntityModel
from django_ledger.models.items import ItemModel, ItemTransactionModel


User = get_user_model()


class Location(models.Model):
    """
    Physical or logical storage: e.g., 'Studio', 'Images Gallery', 'Offsite Storage'.
    """
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)

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
    """
    Our internal overlay: how much of an Item is currently allocated to a given Location.
    Sum of allocations across locations must be <= on_hand computed from Django-Ledger.

    This does NOT alter any Django-Ledger counts.
    """
    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT, related_name="stockops_allocations")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="stockops_allocations")
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    status = models.CharField(max_length=20, choices=ItemStatus.choices, default=ItemStatus.AVAILABLE)
    note = models.CharField(max_length=300, blank=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("item", "location")]
        verbose_name = "Stock Allocation"
        verbose_name_plural = "Stock Allocations"

    def __str__(self):
        return f"{self.item.name} @ {self.location.name} = {self.quantity}"

    @staticmethod
    def on_hand_qty(item: ItemModel) -> Decimal:
        """
        Pulls 'quantity_onhand' from Django-Ledger's ItemTransactionModel.inventory_count().
        """
        # Limit to the entity of the item
        # ItemModel has entity_id
        qs = ItemTransactionModel.objects.inventory_count(entity_model=item.entity_id)
        by_id = {row.get("item_model_id"): row for row in qs}
        row = by_id.get(item.uuid)
        return (row.get("quantity_onhand") if row else Decimal("0")) or Decimal("0")

    @staticmethod
    def allocated_total(item: ItemModel) -> Decimal:
        agg = StockAllocation.objects.filter(item=item).aggregate(total=models.Sum("quantity"))
        return (agg["total"] or Decimal("0")).quantize(Decimal("0.001"))

    @staticmethod
    def unallocated_qty(item: ItemModel) -> Decimal:
        return (StockAllocation.on_hand_qty(item) - StockAllocation.allocated_total(item)).quantize(Decimal("0.001"))

    def clean(self):
        super().clean()
        if self.quantity < 0:
            raise ValidationError("Quantity cannot be negative.")

        # Ensure total allocations across locations <= on_hand
        # Calculate as if this record were saved with new quantity
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
    """
    A user-initiated movement between locations. Saving a transfer updates our StockAllocation rows atomically.
    """
    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT, related_name="stockops_transfers")
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

        # Ensure there is enough allocated at from_location to move
        from_alloc, _ = StockAllocation.objects.get_or_create(item=self.item, location=self.from_location)
        if from_alloc.quantity < self.quantity:
            raise ValidationError(
                f"Not enough allocated at {self.from_location}. "
                f"Available={from_alloc.quantity}, requested move={self.quantity}."
            )

    def apply_transfer(self):
        """
        Mutates our allocations (not Django-Ledger) to reflect the move.
        """
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

            # Default statuses: keep as-is (do not force)
            from_alloc.full_clean()
            to_alloc.full_clean()
            from_alloc.save()
            to_alloc.save()

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        # Apply every time (idempotent for same values, but we assume quantity/from/to fixed once saved)
        self.apply_transfer()


class StatusOverlay(models.Model):
    """
    Allows marking per-item, per-location status WITHOUT changing quantities.
    Useful for flagging a specific piece as Damaged/Missing while still allocated.
    """
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
    """
    Lets you record expected inbound stock to a location (user-entered), without touching Django-Ledger.
    You can use xref fields to note the PO/Bill number manually.
    """
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

