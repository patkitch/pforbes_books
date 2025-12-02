from django.core.management.base import BaseCommand
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.pauly.core import (
    test_woocommerce_connection,
    create_variable_product_draft,
)


class Command(BaseCommand):
    help = (
        "Runs the Pauly product-creation agent: "
        "creates a variable WooCommerce product as DRAFT with two sizes "
        "(11x14 and 8x10 white mat), plus two variations."
    )

    def handle(self, *args, **options):
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
            # ------------------------------------
            # 2. Quick sanity check: Woo reachable?
            # ------------------------------------
            log("info", "Pauly starting: WooCommerce read-only sanity check...")
            products_summary = test_woocommerce_connection(max_products=1)
            log(
                "info",
                f"Pauly confirmed WooCommerce is reachable. "
                f"Sample product: {products_summary[0] if products_summary else 'none found.'}",
                extra={"sample_product": products_summary[0] if products_summary else None},
            )

            # ------------------------------------
            # 3. Define the artwork for this run
            # ------------------------------------
            # TODO: later we will feed this from a form or DB.
            artwork = {
                "title": "SAMPLE – Morning Reflections Giclée Print",
                "short_description": "A sample listing created by Pauly as DRAFT.",
                "description_long": (
                    "<p>This is a <strong>sample product</strong> created by Pauly as a draft. "
                    "In a real run, this description will be your full story for the artwork, "
                    "sized as 11x14 and 8x10 white mats.</p>"
                ),
                "sku_base": "SAMPLE-MR-GP",
                "price_11x14": "95.00",
                "price_8x10": "65.00",
                "categories": ["Giclée Prints"],
                "tags": ["sample", "pauly", "giclee"],
            }

            log("info", "Pauly is creating a DRAFT variable product with two sizes (11x14, 8x10).")

            # ------------------------------------
            # 4. Create product + variations in Woo (as DRAFT)
            # ------------------------------------
            creation_result = create_variable_product_draft(artwork)

            product = creation_result["product"]
            variations = creation_result["variations"]

            product_id = product.get("id")
            product_name = product.get("name")
            product_status = product.get("status")

            log(
                "info",
                f"Pauly created WooCommerce product ID={product_id} | Name='{product_name}' | Status={product_status}",
                extra={"product": product},
            )

            for v in variations:
                log(
                    "info",
                    (
                        "Pauly created variation ID={id} | SKU={sku} | Price={price} | Size={size}"
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

            # ------------------------------------
            # 5. Finish run as success
            # ------------------------------------
            run.status = "success"
            run.records_affected = 1  # one product (with two variations)
            run.finished_at = timezone.now()
            run.save()

            log(
                "info",
                "Pauly completed product creation as DRAFT successfully. "
                "Review the new product in WooCommerce before publishing.",
            )

        except Exception as e:
            # ------------------------------------
            # 6. Mark run failed
            # ------------------------------------
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()

            log("error", f"Pauly encountered an error: {str(e)}")
            raise e
