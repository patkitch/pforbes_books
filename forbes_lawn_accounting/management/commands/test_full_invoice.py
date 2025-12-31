"""
Test FULL invoice query with line items
"""

from django.core.management.base import BaseCommand, CommandError
import os
import requests


class Command(BaseCommand):
    help = 'Test full invoice query with line items'

    def handle(self, *args, **options):
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY not set")
        
        # FULL query with all fields including line items
        query = """
        query FetchInvoices($after: String, $first: Int!, $issuedDateFilter: Iso8601DateTimeRangeInput) {
          invoices(after: $after, first: $first, filter: {issuedDate: $issuedDateFilter}) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              invoiceNumber
              subject
              message
              issuedDate
              dueDate
              amounts {
                total
                subtotal
                taxAmount
                invoiceBalance
                paymentsTotal
                depositAmount
                discountAmount
                tipsTotal
              }
              client {
                id
                name
              }
              lineItems {
                nodes {
                  id
                  name
                  description
                  quantity
                  unitPrice
                  totalPrice
                  taxable
                  linkedProductOrService {
                    id
                    name
                  }
                }
              }
              invoiceStatus
            }
          }
        }
        """
        
        variables = {
            "first": 2,  # Just 2 invoices
            "issuedDateFilter": {
                "after": "2025-01-01T00:00:00Z"
            }
        }
        
        headers = {
            "Authorization": f"Bearer {jobber_api_key}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": "2025-04-16"
        }
        
        self.stdout.write("Testing FULL invoice query (with line items)...")
        
        response = requests.post(
            "https://api.getjobber.com/api/graphql",
            json={"query": query, "variables": variables},
            headers=headers
        )
        
        result = response.json()
        
        if "errors" in result:
            self.stdout.write(self.style.ERROR(f"ERROR: {result['errors']}"))
        else:
            self.stdout.write(self.style.SUCCESS("✓ Query successful!"))
            invoices = result['data']['invoices']['nodes']
            self.stdout.write(f"Found {len(invoices)} invoices")
            
            for inv in invoices:
                line_count = len(inv['lineItems']['nodes'])
                self.stdout.write(f"  - Invoice #{inv['invoiceNumber']}: ${inv['amounts']['total']} ({line_count} lines)")
            
            # Show rate limit
            extensions = result.get('extensions', {})
            cost = extensions.get('cost', {})
            throttle = cost.get('throttleStatus', {})
            available = throttle.get('currentlyAvailable', 'unknown')
            requested_cost = cost.get('requestedQueryCost', 'unknown')
            actual_cost = cost.get('actualQueryCost', 'unknown')
            
            self.stdout.write(f"\nRequested cost: {requested_cost} points")
            self.stdout.write(f"Actual cost: {actual_cost} points")
            self.stdout.write(f"Remaining: {available}/10000")
            
            if requested_cost != 'unknown' and int(str(requested_cost)) > 5000:
                self.stdout.write(self.style.WARNING(
                    f"\n⚠️  WARNING: This query is VERY expensive! ({requested_cost} points)"
                ))
