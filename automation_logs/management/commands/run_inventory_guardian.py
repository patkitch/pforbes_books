from django.core.management.base import BaseCommand
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.inventory.core import (
    get_inventory_items,
    compare_item_totals,
)


class Command(BaseCommand):
    help = "Runs the InventoryGuardian read-only inventory check agent."

    def handle(self, *args, **options):
        # -----------------------------
        # 1. Start the agent run record
        # -----------------------------
        run = AgentRun.objects.create(
            agent_name="InventoryGuardian",
            run_type="manual",
            started_at=timezone.now(),
            status="running",
        )

        # Helper function to log events
        def log(level, message, extra=None):
            AgentEvent.objects.create(
                agent_run=run,
                timestamp=timezone.now(),
                level=level,
                message=message,
                extra=extra or {},
            )
            # Show in console too
            self.stdout.write(f"[{level.upper()}] {message}")

        try:
            # High-level start message (INFO)
            log("info", "InventoryGuardian starting inventory snapshot...")

            # ------------------------------------
            # 2. Fetch items to inspect
            # ------------------------------------
            items_qs = get_inventory_items()
            total_items_examined = items_qs.count()
            mismatches = 0

            # One info line about volume
            log("info", f"InventoryGuardian will examine {total_items_examined} inventory item(s).")

            for item in items_qs.iterator():
                result = compare_item_totals(item)

                if result['mismatch']:
                    mismatches += 1

                    # Detailed warning only for mismatches
                    log(
                        "warning",
                        (
                            f"Mismatch for item '{item.name}' (PK: {item.pk}). "
                            f"Stored qty/value: {result['stored_qty']} / {result['stored_value']} "
                            f"Expected qty/value: {result['expected_qty']} / {result['expected_value']}"
                        ),
                        extra={
                            "item_pk": str(item.pk),
                            "item_name": item.name,
                            "stored_qty": str(result['stored_qty']),
                            "expected_qty": str(result['expected_qty']),
                            "stored_value": str(result['stored_value']),
                            "expected_value": str(result['expected_value']),
                        },
                    )
                # If it matches, we stay silent (no debug noise)

            # ------------------------------------
            # 3. Decide run status based on mismatches
            # ------------------------------------
            if mismatches > 0:
                run.status = "warning"
                final_msg = (
                    f"InventoryGuardian finished with {mismatches} mismatched item(s) "
                    f"out of {total_items_examined} examined."
                )
                log("warning", final_msg, extra={"mismatches": mismatches})
            else:
                run.status = "success"
                final_msg = (
                    f"InventoryGuardian finished successfully. "
                    f"All {total_items_examined} item(s) matched expected totals."
                )
                log("info", final_msg)

            run.records_affected = total_items_examined
            run.finished_at = timezone.now()
            run.save()

        except Exception as e:
            # ------------------------------------
            # 4. Mark run failed
            # ------------------------------------
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()

            log("error", f"InventoryGuardian encountered an error: {str(e)}")
            # Re-raise so you see the stack trace in the console
            raise e


