# jobber_sync/management/commands/jobber_smoke_test.py
from __future__ import annotations

import json
from django.core.management.base import BaseCommand

from jobber_sync.graphql.queries import INVOICES_WINDOW
from jobber_sync.services.jobber_client import execute_jobber_gql


class Command(BaseCommand):
    help = "Smoke test: call Jobber GraphQL from Django and print invoice pageInfo + first few invoice numbers."

    def add_arguments(self, parser):
        parser.add_argument("--first", type=int, default=5)
        parser.add_argument("--after", type=str, default=None)
        parser.add_argument("--debug", action="store_true", help="Print raw JSON response.")

    def handle(self, *args, **options):
        variables = {
            "first": options["first"],
            "after": options["after"],
            "filter": None,
            "sort": None,  # keep it null until you want to supply sort inputs
        }

        res = execute_jobber_gql(INVOICES_WINDOW, variables)

        if options["debug"]:
            self.stdout.write(json.dumps(res.raw, indent=2))

        if res.errors:
            self.stdout.write(self.style.ERROR("GraphQL returned errors:"))
            self.stdout.write(json.dumps(res.errors, indent=2))
            return

        invoices = (res.data or {}).get("invoices") or {}
        page_info = invoices.get("pageInfo") or {}
        nodes = invoices.get("nodes") or []

        self.stdout.write(self.style.SUCCESS("Jobber GraphQL call succeeded."))
        self.stdout.write(f"pageInfo.hasNextPage = {page_info.get('hasNextPage')}")
        self.stdout.write(f"pageInfo.endCursor   = {page_info.get('endCursor')}")

        self.stdout.write("\nFirst invoices returned:")
        for n in nodes[:10]:
            self.stdout.write(f"- #{n.get('invoiceNumber')} | {n.get('invoiceStatus')} | {n.get('client', {}).get('name')}")
