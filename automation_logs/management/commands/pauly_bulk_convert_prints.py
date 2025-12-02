from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.pauly.core import woo_get, convert_simple_product_to_standard_print, STANDARD_PRINT_TITLE_SUFFIX


class Command(BaseCommand):
    help = (
        "Bulk-convert simple WooCommerce products into standard variable print drafts.\n\n"
        "- Only operates on products with type='simple'.\n"
        "- Further narrows to names containing 'Giclée' or 'Giclee'.\n"
        "- Skips anything with 'Greeting Cards' in the name.\n"
        "- Uses the STANDARD_PRINT template (Size with 11x14 & 8x10 white mat).\n"
        "- Default is DRY-RUN (no changes) unless --commit is provided."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Maximum number of simple products to process (default 5).",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually create variable product drafts and variations. "
                 "If omitted, runs in dry-run mode.",
        )
    def _has_standard_variable_for_artwork(self, artwork_title: str) -> bool:
        """
        Returns True if there is already a variable product whose name matches
        Pat's standard format for this artwork title.
        """
        target_name = f"{artwork_title}{STANDARD_PRINT_TITLE_SUFFIX}"
        target_name_lower = target_name.lower()

        # Search WooCommerce products by artwork title
        params = {
            "per_page": 20,
            "page": 1,
            "search": artwork_title,
        }
        products = woo_get("products", params=params) or []

        for prod in products:
            ptype = prod.get("type")
            name = (prod.get("name") or "").strip()
            name_lower = name.lower()

            # We only care about variable products that match the standard name exactly
            if ptype == "variable" and name_lower == target_name_lower:
                return True

        return False


    def handle(self, *args, **options):
        limit = options["limit"]
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

        mode = "COMMIT" if commit else "DRY-RUN"
        log(
            "info",
            f"Starting bulk simple→standard conversion in {mode} mode with limit={limit}.",
        )

        try:
            processed = 0
            page = 1
            per_page = 50

            while processed < limit:
                params = {
                    "per_page": per_page,
                    "page": page,
                    "orderby": "id",
                    "order": "asc",
                }

                products = woo_get("products", params=params)
                if not products:
                    break

                for p in products:
                    if processed >= limit:
                        break

                    pid = p.get("id")
                    name = (p.get("name") or "").strip()
                    ptype = p.get("type")

                    # 1) Only handle simple products
                    if ptype != "simple":
                        continue

                    # 2) Only things that look like prints (contains 'Giclée' or 'Giclee')
                    name_lower = name.lower()
                    if "giclée" not in name_lower and "giclee" not in name_lower:
                        continue

                    # 3) Skip greeting cards explicitly
                    if "greeting cards" in name_lower:
                        log(
                            "info",
                            f"Skipping simple product ID={pid} '{name}' (looks like greeting cards).",
                        )
                        continue
                    # 4) Derive artwork title the same way as in core
                    artwork_title = name
                    if "–" in artwork_title:
                        artwork_title = artwork_title.split("–")[0].strip()
                    elif "|" in artwork_title:
                        artwork_title = artwork_title.split("|")[0].strip()

                    # 5) Skip if a standard variable product already exists for this artwork
                    if self._has_standard_variable_for_artwork(artwork_title):
                        log(
                            "info",
                            f"Skipping simple product ID={pid} '{name}' because a standard "
                            f"variable product already exists for artwork '{artwork_title}'.",
                        )
                        continue
                    processed += 1

                    log(
                        "info",
                        f"Processing simple product ID={pid} '{name}' ({ptype})...",
                    )

                    result = convert_simple_product_to_standard_print(
                        product_id=pid,
                        dry_run=not commit,
                    )

                    plan = result.get("plan", {})
                    base_price = plan.get("original_price")

                    if not commit:
                        log(
                            "info",
                            f"[DRY-RUN] Would create variable draft from ID={pid}, "
                            f"base_price={base_price}.",
                            extra={"plan": plan},
                        )
                    else:
                        created_product = result.get("created_product", {})
                        created_variations = result.get("created_variations", [])
                        new_id = created_product.get("id")

                        log(
                            "info",
                            f"[COMMIT] Created new variable product draft ID={new_id} from simple ID={pid}.",
                            extra={"created_product": created_product},
                        )
                        log(
                            "info",
                            f"[COMMIT] Created {len(created_variations)} variation(s) for new product ID={new_id}.",
                            extra={"created_variations": created_variations},
                        )

                page += 1

            run.status = "success"
            run.records_affected = processed
            run.finished_at = timezone.now()
            run.save()

            log(
                "info",
                f"Bulk conversion complete. Processed={processed} simple product(s).",
            )

        except Exception as e:
            run.status = "error"
            run.finished_at = timezone.now()
            run.save()
            log("error", f"Bulk conversion failed: {str(e)}")
            raise CommandError(str(e))
