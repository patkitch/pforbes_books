from django.core.management.base import BaseCommand
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.sam_seo.core import (
    fetch_products_batch,
    build_sam_seo_suggestion,
)


class Command(BaseCommand):
    help = (
        "Run SamSEO over WooCommerce products to suggest Yoast-style SEO:\n"
        "- Generates a focus keyphrase and meta description per product.\n"
        "- Respects ~155 character limit for meta description.\n"
        "- Dynamic tone selection based on artwork mood.\n"
        "- DOES NOT write to Woo/Yoast; only logs suggestions for copy/paste.\n"
        "Use --limit to control how many products are processed.\n"
        "Use --commit if you want to mark the run as a 'final' pass in logs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of products to process (default 50).",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help=(
                "Semantic flag only for now. When set, the run is considered a "
                "'final' pass in logs, but no changes are made to WooCommerce."
            ),
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        commit = options["commit"]

        run = AgentRun.objects.create(
            agent_name="SamSEO",
            run_type="commit" if commit else "manual",
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

        processed = 0
        page = 1
        per_page = 50

        log(
            "info",
            f"SamSEO starting SEO suggestion pass (limit={limit}, mode={'COMMIT' if commit else 'SUGGEST-ONLY'}).",
        )

        try:
            while processed < limit:
                products = fetch_products_batch(page=page, per_page=per_page)
                if not products:
                    break

                for product in products:
                    if processed >= limit:
                        break

                    pid = product.get("id")
                    name = (product.get("name") or "").strip()
                    ptype = product.get("type")
                    status = product.get("status")

                    # Only operate on normal store products
                    if ptype not in ("simple", "variable"):
                        continue

                    # Optionally skip trashed or weird statuses
                    if status not in ("publish", "draft", "pending", "private"):
                        continue

                    suggestion = build_sam_seo_suggestion(product)
                    focus = suggestion["focus_keyphrase"]
                    meta = suggestion["meta_description"]

                    processed += 1

                    log(
                        "info",
                        f"[SEO SUGGESTION] ID={pid} '{name}' | Focus='{focus}' | Meta='{meta}'",
                        extra={
                            "product_id": pid,
                            "product_name": name,
                            "product_type": ptype,
                            "focus_keyphrase": focus,
                            "meta_description": meta,
                            "status": status,
                        },
                    )

                page += 1

            run.status = "success"
            run.records_affected = processed
            run.finished_at = timezone.now()
            run.save()

            log(
                "info",
                f"SamSEO finished. Generated suggestions for {processed} product(s).",
            )

        except Exception as e:
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()
            log("error", f"SamSEO failed: {str(e)}")
            raise
