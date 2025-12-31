from django.core.management.base import BaseCommand
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.sam_seo.core import fetch_all_products, analyze_product_for_seo


class Command(BaseCommand):
    help = (
        "SamSEO: Review WooCommerce products and suggest focus keyphrase and meta description "
        "for those with missing or weak SEO. Suggestions are logged in Automation Logs only."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional limit on number of products to review (default: all).",
        )

    def handle(self, *args, **options):
        limit = options.get("limit")

        # -----------------------------
        # 1. Start the agent run record
        # -----------------------------
        run = AgentRun.objects.create(
            agent_name="SamSEO",
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
            # 2. Fetch products
            # -----------------------------
            log(
                "info",
                f"SamSEO starting SEO review. Limit={limit if limit is not None else 'ALL'} products.",
            )

            products = fetch_all_products(limit=limit)
            total_products = len(products)

            log(
                "info",
                f"SamSEO fetched {total_products} product(s) from WooCommerce for review.",
            )

            suggestions_count = 0
            good_count = 0

            # -----------------------------
            # 3. Analyze each product
            # -----------------------------
            for product in products:
                analysis = analyze_product_for_seo(product)

                if analysis["is_good"]:
                    good_count += 1
                    # Keep noise low: log at info with simple message, no big extra blob
                    log(
                        "info",
                        (
                            f"Product ID={analysis['product_id']} "
                            f"('{analysis['product_name']}') SEO OK: {analysis['reason']}"
                        ),
                        extra={
                            "product_id": analysis["product_id"],
                            "product_name": analysis["product_name"],
                            "existing_focus_keyphrase": analysis["existing_focus_keyphrase"],
                            "meta_description_length": analysis["details"]["meta_description_length"],
                        },
                    )
                else:
                    suggestions_count += 1
                    # Log suggestions with full extra payload
                    log(
                        "info",
                        (
                            f"SEO suggestion for product ID={analysis['product_id']} "
                            f"('{analysis['product_name']}'): {analysis['reason']}"
                        ),
                        extra={
                            "product_id": analysis["product_id"],
                            "product_name": analysis["product_name"],
                            "existing_focus_keyphrase": analysis["existing_focus_keyphrase"],
                            "existing_meta_description": analysis["existing_meta_description"],
                            "suggested_focus_keyphrase": analysis["suggested_focus_keyphrase"],
                            "suggested_meta_description": analysis["suggested_meta_description"],
                            "details": analysis["details"],
                        },
                    )

            # -----------------------------
            # 4. Finish run as success
            # -----------------------------
            summary_msg = (
                f"SamSEO finished review. Total products: {total_products}. "
                f"SEO OK: {good_count}. Suggestions needed: {suggestions_count}."
            )
            log("info", summary_msg)

            run.status = "success"
            run.records_affected = suggestions_count
            run.finished_at = timezone.now()
            run.save()

        except Exception as e:
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()

            log("error", f"SamSEO encountered an error: {str(e)}")
            raise e
