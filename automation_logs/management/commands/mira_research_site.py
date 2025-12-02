from django.core.management.base import BaseCommand
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.mira.core import get_product_overview, generate_design_strategy, design_strategy_to_markdown


class Command(BaseCommand):
    help = (
        "Mira: Research WooCommerce catalog and generate a design strategy "
        "document (palette, typography, layout, Elementor guidance). "
        "Results are logged in Automation Logs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Optional max number of products to analyze (default: 200).",
        )

    def handle(self, *args, **options):
        limit = options.get("limit", 200)

        # -----------------------------
        # 1. Start the agent run record
        # -----------------------------
        run = AgentRun.objects.create(
            agent_name="Mira",
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
            # 2. Fetch product overview
            # -----------------------------
            log(
                "info",
                f"Mira starting site research with product limit={limit}.",
            )

            products = get_product_overview(limit=limit)
            total = len(products)

            log(
                "info",
                f"Mira fetched {total} product(s) from WooCommerce for analysis.",
                extra={"sample_product": products[0] if products else None},
            )

            # -----------------------------
            # 3. Generate design strategy
            # -----------------------------
            strategy = generate_design_strategy(products)
            markdown = design_strategy_to_markdown(strategy)

            log(
                "info",
            "Mira generated design strategy (palette, typography, layout, Elementor guidance).",
            extra={
            "design_strategy": strategy,
            "design_markdown": markdown,
            },
            )


            # -----------------------------
            # 4. Finish run as success
            # -----------------------------
            run.status = "success"
            run.records_affected = total
            run.finished_at = timezone.now()
            run.save()

            summary = strategy.get("summary", {})
            log(
                "info",
                (
                    "Mira research complete. Total products: {total}. "
                    "Unique categories: {cats}. Unique tags: {tags}."
                ).format(
                    total=summary.get("total_products", total),
                    cats=len(summary.get("unique_categories", [])),
                    tags=len(summary.get("unique_tags", [])),
                ),
            )

        except Exception as e:
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()

            log("error", f"Mira encountered an error: {str(e)}")
            raise e
