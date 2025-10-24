from django.db import models

class BusinessTask(models.Model):
    """
    Real world running-the-art-business tasks: order prints, restock mailers,
    prep gallery delivery, varnish originals, etc.
    """
    title = models.CharField(max_length=200)
    notes = models.TextField(blank=True)

    PRIORITY_CHOICES = [
        ("high", "High"),
        ("med", "Medium"),
        ("low", "Low"),
    ]
    priority = models.CharField(
        max_length=4,
        choices=PRIORITY_CHOICES,
        default="med"
    )

    STATUS_CHOICES = [
        ("idea", "Idea / backlog"),
        ("doing", "In progress"),
        ("wait", "Waiting / on order"),
        ("done", "Done"),
    ]
    status = models.CharField(
        max_length=5,
        choices=STATUS_CHOICES,
        default="idea"
    )

    owner = models.CharField(
        max_length=100,
        blank=True,
        help_text="Who's on this? (Me, Husband, Gallery Contact, Printer, etc.)"
    )

    due_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Business Task"
        verbose_name_plural = "Business Tasks"
        ordering = ["-priority", "due_date", "status", "-created_at"]

    def __str__(self):
        return f"[BIZ][{self.get_priority_display()}] {self.title} ({self.get_status_display()})"


class SystemTask(models.Model):
    """
    Internal work on the system: accounting logic, Django Ledger behavior,
    credit-card flow, reports we’re building, etc.
    """
    title = models.CharField(max_length=200)
    notes = models.TextField(blank=True)

    PRIORITY_CHOICES = [
        ("high", "High"),
        ("med", "Medium"),
        ("low", "Low"),
    ]
    priority = models.CharField(
        max_length=4,
        choices=PRIORITY_CHOICES,
        default="med"
    )

    STATUS_CHOICES = [
        ("idea", "Idea / backlog"),
        ("doing", "In progress"),
        ("wait", "Waiting / blocked"),
        ("done", "Done"),
    ]
    status = models.CharField(
        max_length=5,
        choices=STATUS_CHOICES,
        default="idea"
    )

    owner = models.CharField(
        max_length=100,
        blank=True,
        help_text="Who's on this? (Me, Harold, Son, Gallery, etc.)"
    )

    due_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "System Task"
        verbose_name_plural = "System Tasks"
        ordering = ["-priority", "due_date", "status", "-created_at"]

    def __str__(self):
        return f"[SYSTEM][{self.get_priority_display()}] {self.title} ({self.get_status_display()})"

