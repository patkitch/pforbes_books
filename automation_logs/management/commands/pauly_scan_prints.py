from django.core.management.base import BaseCommand
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.pauly.core import woo_get, inspect_product_for_standard_print


class Command(BaseCommand):
    help = (
        "Scan WooCommerce products to see which ones match the "
        "standard print variation template (Size: 11x14 & 8x10 white mat). "
        "Read-only: does NOT change any products."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--category",
            type=str,
            default=None,
            help="Optional WooCommerce category slug (e.g. 'giclee-prints'). "
                 "If omitted, scans all products.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Max number of products to inspect (default 200).",
        )

    def handle(self, *args, **options):
        category = options.get("category")
        limit = options.get("limit", 200)

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
            page = 1
            per_page = 50
            inspected = 0
            standard_count = 0
            non_standard_count = 0

            log(
                "info",
                f"Starting print scan with limit={limit}, category={category or 'ALL'}",
            )

            while inspected < limit:
                params = {
                    "per_page": per_page,
                    "page": page,
                    "orderby": "id",
                    "order": "asc",
                }
                if category:
                    # WooCommerce uses 'category' param as slug
                    params["category"] = category

                products = woo_get("products", params=params)
                if not products:
                    break

                for p in products:
                    if inspected >= limit:
                        break

                    result = inspect_product_for_standard_print(p)
                    inspected += 1

                    if result["is_standard"]:
                        standard_count += 1
                        log(
                            "info",
                            f"[OK] {result['name']} (ID={result['id']}) is standard.",
                            extra={"product_id": result["id"], "result": result},
                        )
                    else:
                        non_standard_count += 1
                        log(
                            "warning",
                            f"[MISMATCH] {result['name']} (ID={result['id']}) is NOT standard. Reason: {result['reason']}",
                            extra={"product_id": result["id"], "result": result},
                        )

                page += 1

            run.status = "success"
            run.records_affected = inspected
            run.finished_at = timezone.now()
            run.save()

            log(
                "info",
                f"Scan complete. Inspected={inspected}, standard={standard_count}, non_standard={non_standard_count}.",
            )

        except Exception as e:
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()
            log("error", f"Pauly scan failed: {str(e)}")
            raise e
