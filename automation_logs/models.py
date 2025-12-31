from django.db import models


class AgentRun(models.Model):
    """
    One execution of an agent.

    Example:
    - InventoryGuardian run at 2:00 AM
    - Pauly run for a new artwork
    - Mira run for a design/blog pass
    """

    # Which agent is this?
    agent_name = models.CharField(max_length=100)
    # e.g. "InventoryGuardian", "Pauly", "Mira"

    # How was it started?
    RUN_TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('scheduled', 'Scheduled'),
        ('triggered', 'Triggered'),  # e.g. when a new product is created
    ]
    run_type = models.CharField(
        max_length=20,
        choices=RUN_TYPE_CHOICES,
        default='manual',
    )

    # Timing
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    # Status of the whole run
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('running', 'Running'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='running',
    )

    # Optional: how many records/things this run touched or inspected
    records_affected = models.IntegerField(null=True, blank=True)

    # Optional metadata/context (JSON requires PostgreSQL, which you have)
    context = models.JSONField(null=True, blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.agent_name} ({self.started_at:%Y-%m-%d %H:%M}) - {self.status}'


class AgentEvent(models.Model):
    """
    Detailed log messages that belong to a specific AgentRun.

    Example:
    - "Starting inventory snapshot..."
    - "Found mismatch for item 123..."
    - "WooCommerce product 456 created."
    """

    agent_run = models.ForeignKey(
        AgentRun,
        related_name='events',
        on_delete=models.CASCADE,
    )

    timestamp = models.DateTimeField()
    # When did this event happen?

    LEVEL_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('debug', 'Debug'),
    ]
    level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES,
        default='info',
    )

    message = models.TextField()
    # Human-readable description of what happened

    extra = models.JSONField(null=True, blank=True)
    # Optional: structured data (ids, counts, etc.)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f'[{self.level.upper()}] {self.timestamp:%Y-%m-%d %H:%M:%S}'

