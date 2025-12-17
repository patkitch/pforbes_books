from __future__ import annotations

from datetime import date
from typing import Tuple
from uuid import UUID

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


def month_range(year: int, month: int) -> Tuple[date, date]:
    if month < 1 or month > 12:
        raise CommandError("month must be 1..12")
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def looks_like_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except Exception:
        return False


class Command(BaseCommand):
    help = "Unlock/unpost (if possible) and delete all Journal Entries in a specific Entity+Ledger for a given month."

    def add_arguments(self, parser):
        parser.add_argument("--entity-slug", required=True)

        # ✅ New: preferred stable identifier
        parser.add_argument("--ledger-uuid", required=False, help="Ledger UUID (recommended)")

        # ✅ New: human friendly option
        parser.add_argument("--ledger-name", required=False, help="Ledger name (exact match)")

        # ✅ Legacy: kept for compatibility
        parser.add_argument(
            "--ledger-xid",
            required=False,
            help="Legacy identifier. We try to match ledger_xid, then name; if it looks like UUID, we try uuid too.",
        )

        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)

        parser.add_argument("--commit", action="store_true", help="Actually delete. Default is dry-run.")
        parser.add_argument("--force", action="store_true", help="Proceed even if count is high (safety switch).")

        # Sandbox crowbar for weird locked JEs
        parser.add_argument(
            "--hard-unlock",
            action="store_true",
            help="If a JE remains locked after normal attempts, force DB update locked=False (sandbox/reset use).",
        )

    def handle(self, *args, **opts):
        entity_slug = opts["entity_slug"]
        ledger_uuid = opts.get("ledger_uuid")
        ledger_name = opts.get("ledger_name")
        ledger_xid = opts.get("ledger_xid")

        year = opts["year"]
        month = opts["month"]
        commit = opts["commit"]
        force = opts["force"]
        hard_unlock = opts["hard_unlock"]

        if not (ledger_uuid or ledger_name or ledger_xid):
            raise CommandError("You must provide one of: --ledger-uuid OR --ledger-name OR --ledger-xid")

        start, end = month_range(year, month)

        EntityModel = apps.get_model("django_ledger", "EntityModel")
        LedgerModel = apps.get_model("django_ledger", "LedgerModel")
        JournalEntryModel = apps.get_model("django_ledger", "JournalEntryModel")

        entity = EntityModel.objects.filter(slug=entity_slug).first()
        if not entity:
            raise CommandError(f"Entity not found: slug={entity_slug}")

        # --- DEBUG: show ledgers in this entity (safe) ---
        self.stdout.write(f"DEBUG: entity_slug={entity_slug} -> entity_uuid={entity.uuid}")
        self.stdout.write("DEBUG: available ledgers for this entity:")
        for row in LedgerModel.objects.filter(entity=entity).values("name", "ledger_xid", "uuid"):
            self.stdout.write(
                f"  - name={row['name']!r} ledger_xid={row.get('ledger_xid')!r} uuid={row['uuid']}"
            )

        # --- Resolve ledger ---
        ledger = None
        resolve_attempts = []

        # 1) UUID (preferred)
        if ledger_uuid:
            resolve_attempts.append(f"uuid={ledger_uuid}")
            ledger = LedgerModel.objects.filter(entity=entity, uuid=ledger_uuid).first()

        # 2) Name (exact)
        if ledger is None and ledger_name:
            resolve_attempts.append(f"name={ledger_name}")
            ledger = LedgerModel.objects.filter(entity=entity, name=ledger_name).first()

        # 3) Legacy --ledger-xid:
        #    - if UUID-looking -> try uuid
        #    - then try ledger_xid
        #    - then try name
        if ledger is None and ledger_xid:
            if looks_like_uuid(ledger_xid):
                resolve_attempts.append(f"uuid(from ledger_xid)={ledger_xid}")
                ledger = LedgerModel.objects.filter(entity=entity, uuid=ledger_xid).first()

            if ledger is None:
                resolve_attempts.append(f"ledger_xid={ledger_xid}")
                ledger = LedgerModel.objects.filter(entity=entity, ledger_xid=ledger_xid).first()

            if ledger is None:
                resolve_attempts.append(f"name(from ledger_xid)={ledger_xid}")
                ledger = LedgerModel.objects.filter(entity=entity, name=ledger_xid).first()

        if not ledger:
            raise CommandError(
                f"Ledger not found for entity={entity_slug}. Tried: {', '.join(resolve_attempts)}"
            )

        self.stdout.write(self.style.SUCCESS(
            f"Resolved ledger: name={ledger.name!r} uuid={ledger.uuid} ledger_xid={getattr(ledger, 'ledger_xid', None)!r}"
        ))

        # Base query
        je_qs = JournalEntryModel.objects.filter(ledger=ledger)

        # Filter by month using timestamp/date field
        je_fields = {f.name for f in JournalEntryModel._meta.fields}
        if "timestamp" in je_fields:
            je_qs = je_qs.filter(timestamp__date__gte=start, timestamp__date__lt=end)
            order_by = ("timestamp", "je_number")
        elif "date" in je_fields:
            je_qs = je_qs.filter(date__gte=start, date__lt=end)
            order_by = ("date", "je_number")
        else:
            raise CommandError("JournalEntryModel has no 'timestamp' or 'date' field to filter by month.")

        count = je_qs.count()

        self.stdout.write(self.style.NOTICE(
            f"\nTarget:"
            f"\n  entity={entity_slug}"
            f"\n  ledger_uuid={ledger.uuid}"
            f"\n  ledger_name={ledger.name}"
            f"\n  month={start}..{end} (exclusive)"
        ))
        self.stdout.write(self.style.NOTICE(f"Journal Entries found: {count}"))
        self.stdout.write(self.style.NOTICE(f"MODE: {'COMMIT' if commit else 'DRY RUN'}"))
        self.stdout.write(self.style.NOTICE(f"hard_unlock={'ON' if hard_unlock else 'OFF'}\n"))

        if count == 0:
            self.stdout.write(self.style.WARNING("Nothing to delete."))
            return

        if count > 200 and not force:
            raise CommandError(f"Refusing to process {count} JEs without --force. (Safety switch)")

        ctx = transaction.atomic if commit else _noop_context

        deleted = 0
        skipped = 0
        failed = 0

        with ctx():
            for je in je_qs.order_by(*order_by):
                je.refresh_from_db()

                try:
                    # ---- 1) Try normal unlock (often unavailable) ----
                    if je.locked and hasattr(je, "can_unlock") and je.can_unlock():
                        self.stdout.write(f"  - UNLOCK {je.uuid}")
                        if commit:
                            je.unlock()
                            je.refresh_from_db()

                    # ---- 2) If still locked, try mark_as_unlocked (may not persist) ----
                    if je.locked and hasattr(je, "mark_as_unlocked"):
                        self.stdout.write(f"  - FORCE UNLOCK (mark_as_unlocked) {je.uuid}")
                        if commit:
                            je.mark_as_unlocked()
                            je.save()
                            je.refresh_from_db()

                    # ---- 3) Unpost (normal or forced) ----
                    if je.posted and hasattr(je, "can_unpost") and je.can_unpost():
                        self.stdout.write(f"  - UNPOST {je.uuid}")
                        if commit:
                            je.unpost()
                            je.refresh_from_db()

                    if je.posted and hasattr(je, "mark_as_unposted"):
                        self.stdout.write(f"  - FORCE UNPOST (mark_as_unposted) {je.uuid}")
                        if commit:
                            je.mark_as_unposted()
                            je.save()
                            je.refresh_from_db()

                    # ---- 4) Sandbox crowbar: hard DB unlock if it STILL refuses ----
                    if je.locked and hard_unlock:
                        self.stdout.write(self.style.WARNING(f"  - HARD UNLOCK override (DB update) {je.uuid}"))
                        if commit:
                            JournalEntryModel.objects.filter(uuid=je.uuid).update(locked=False)
                            je.refresh_from_db()

                    # ---- 5) Delete ----
                    if hasattr(je, "can_delete") and je.can_delete():
                        desc = getattr(je, "description", "") or ""
                        self.stdout.write(f"Deleting JE: {je.uuid}  desc={desc!r}")
                        if commit:
                            je.delete()
                        deleted += 1
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"SKIP JE {je.uuid} posted={je.posted} locked={je.locked} "
                            f"can_unlock={je.can_unlock() if hasattr(je,'can_unlock') else 'n/a'} "
                            f"can_unpost={je.can_unpost() if hasattr(je,'can_unpost') else 'n/a'} "
                            f"can_delete={je.can_delete() if hasattr(je,'can_delete') else 'n/a'}"
                        ))
                        skipped += 1

                except Exception as e:
                    failed += 1
                    self.stdout.write(self.style.ERROR(f"FAILED JE {je.uuid}: {e}"))
                    continue

        self.stdout.write(self.style.SUCCESS(f"\nDONE. deleted={deleted} skipped={skipped} failed={failed}"))
        if not commit:
            self.stdout.write(self.style.WARNING("Dry-run mode: no changes were written."))


class _noop_context:
    def __enter__(self): return None
    def __exit__(self, exc_type, exc, tb): return False
