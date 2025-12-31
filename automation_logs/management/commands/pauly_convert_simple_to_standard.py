from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.pauly.core import convert_simple_product_to_standard_print


class Command(BaseCommand):
    help = (
        "Convert a single simple product into a new variable product that matches "
        "the standard P.Forbes Art print template (Size with two variations). "
        "By default runs in dry-run mode (no changes) unless --commit is provided."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--product-id",
            type=int,
            required=True,
            help="WooCommerce product ID of the simple product to convert.",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually create the new variable product and variations. "
                 "If omitted, runs in dry-run mode (no changes).",
        )

    def handle(self, *args, **options):
        product_id = options["product_id"]
        commit = options["commit"]

        run = AgentRun.objects.create(
            agent_name="Pauly",
            run_type="manual",
            started_at=timezone.now(),
            status="running",
        )

        def log(level, message, extra=None):
            AgentEvent.objects.create(
                agent_run=run,
                timestamp=timezone.now(),
                level=level,
                message=message,
                extra=extra or {},
            )
            self.stdout.write(f"[{level.upper()}] {message}")

        try:
            mode = "COMMIT" if commit else "DRY-RUN"
            log(
                "info",
                f"Starting simple→standard conversion for product ID={product_id} in {mode} mode.",
            )

            result = convert_simple_product_to_standard_print(
                product_id=product_id,
                dry_run=not commit,
            )

            plan = result.get("plan", {})
            original_name = plan.get("original_name")
            base_price = plan.get("original_price")

            log(
                "info",
                f"Original product: '{original_name}' (ID={product_id}), base_price={base_price}.",
                extra={"plan": plan},
            )

            if not commit:
                log(
                    "info",
                    "Dry-run complete. No changes were made. "
                    "Inspect plan details in Automation Logs for this run.",
                )
                run.status = "success"
                run.records_affected = 0
                run.finished_at = timezone.now()
                run.save()
                return

            # COMMIT mode
            created_product = result.get("created_product", {})
            created_variations = result.get("created_variations", [])

            new_id = created_product.get("id")
            log(
                "info",
                f"Created new variable product draft ID={new_id} for '{original_name}'.",
                extra={"created_product": created_product},
            )

            log(
                "info",
                f"Created {len(created_variations)} variation(s) for new product ID={new_id}.",
                extra={"created_variations": created_variations},
            )

            run.status = "success"
            run.records_affected = 1 + len(created_variations)
            run.finished_at = timezone.now()
            run.save()

        except Exception as e:
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()
            log("error", f"Conversion failed: {str(e)}")
            raise CommandError(str(e))
