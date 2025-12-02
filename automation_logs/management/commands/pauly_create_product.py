import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.pauly.core import create_variable_product_draft


class Command(BaseCommand):
    help = (
        "Create a variable WooCommerce product as DRAFT with two sizes "
        "(11x14 and 8x10 white mat) from a JSON config file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            type=str,
            required=True,
            help="Path to the JSON file describing the artwork.",
        )

    def handle(self, *args, **options):
        config_path = options["config"]

        # -----------------------------
        # 0. Validate config path
        # -----------------------------
        path = Path(config_path)
        if not path.is_file():
            raise CommandError(f"Config file not found: {config_path}")

        # -----------------------------
        # 1. Start the agent run record
        # -----------------------------
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
            # -----------------------------
            # 2. Load artwork config
            # -----------------------------
            log("info", f"Loading artwork config from {config_path}.")

            with path.open("r", encoding="utf-8-sig") as f:
                artwork = json.load(f)

            log(
                "info",
                f"Artwork loaded: {artwork.get('title', 'Untitled')} (SKU base: {artwork.get('sku_base')})",
                extra={"artwork": artwork},
            )

            # -----------------------------
            # 3. Create product + variations in Woo (as DRAFT)
            # -----------------------------
            log(
                "info",
                "Pauly is creating a DRAFT variable product with two sizes "
                "(11x14 white mat, 8x10 white mat).",
            )

            creation_result = create_variable_product_draft(artwork)

            product = creation_result["product"]
            variations = creation_result["variations"]

            product_id = product.get("id")
            product_name = product.get("name")
            product_status = product.get("status")

            log(
                "info",
                f"Pauly created WooCommerce product ID={product_id} | "
                f"Name='{product_name}' | Status={product_status}",
                extra={"product": product},
            )

            for v in variations:
                log(
                    "info",
                    (
                        "Pauly created variation ID={id} | SKU={sku} | "
                        "Price={price} | Size={size}"
                    ).format(
                        id=v.get("id"),
                        sku=v.get("sku"),
                        price=v.get("regular_price"),
                        size=(
                            v.get("attributes", [{}])[0].get("option")
                            if v.get("attributes") else None
                        ),
                    ),
                    extra={"variation": v},
                )

            # -----------------------------
            # 4. Finish run as success
            # -----------------------------
            run.status = "success"
            run.records_affected = 1
            run.finished_at = timezone.now()
            run.save()

            log(
                "info",
                "Pauly completed product creation as DRAFT successfully. "
                "Review the new product in WooCommerce before publishing.",
            )

        except Exception as e:
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()

            log("error", f"Pauly encountered an error: {str(e)}")
            raise e
