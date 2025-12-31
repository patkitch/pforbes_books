"""
Invoice Sync Service for Forbes Lawn Accounting
Syncs invoices from Jobber to LedgerLink and posts to the accounting ledger
"""

import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from decimal import Decimal


class InvoiceSyncService:
    """Service to sync invoices from Jobber to LedgerLink"""
    
    def __init__(
        self, 
        jobber_api_key: str,
        ledgerlink_api_key: str,
        entity_slug: str,
        revenue_account_taxable: str = "4024",
        revenue_account_nontaxable: str = "4025",
        tax_account: str = "2011",
        ar_account: str = "1200"
    ):
        self.jobber_api_key = jobber_api_key
        self.ledgerlink_api_key = ledgerlink_api_key
        self.entity_slug = entity_slug
        self.revenue_account_taxable = revenue_account_taxable
        self.revenue_account_nontaxable = revenue_account_nontaxable
        self.tax_account = tax_account
        self.ar_account = ar_account
        
        self.jobber_url = "https://api.getjobber.com/api/graphql"
        self.ledgerlink_url = "https://api.ledgerlink.io/graphql"
    
    def _jobber_request(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Make a GraphQL request to Jobber API"""
        headers = {
            "Authorization": f"Bearer {self.jobber_api_key}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": "2025-04-16"
        }
        
        response = requests.post(
            self.jobber_url,
            json={"query": query, "variables": variables or {}},
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    def _ledgerlink_request(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Make a GraphQL request to LedgerLink API"""
        headers = {
            "Authorization": f"Bearer {self.ledgerlink_api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            self.ledgerlink_url,
            json={"query": query, "variables": variables or {}},
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    def fetch_jobber_invoices(
        self, 
        after_cursor: Optional[str] = None,
        limit: int = 50,
        start_date: Optional[str] = None
    ) -> Dict:
        """
        Fetch invoices from Jobber
        
        Args:
            after_cursor: Pagination cursor
            limit: Number of invoices to fetch per request
            start_date: ISO date string to filter invoices (e.g., "2024-01-01")
        """
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
              }
              client {
                id
                firstName
                lastName
                companyName
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
            "after": after_cursor,
            "first": limit
        }
        
        if start_date:
            # Convert "2024-01-01" to ISO 8601 datetime format
            variables["issuedDateFilter"] = {
                "after": f"{start_date}T00:00:00Z"
            }
        
        return self._jobber_request(query, variables)
    
    def fetch_all_jobber_invoices(self, start_date: Optional[str] = None) -> List[Dict]:
        """
        Fetch all invoices from Jobber with pagination
        
        Args:
            start_date: ISO date string to filter invoices (e.g., "2024-01-01")
        """
        all_invoices = []
        has_next_page = True
        after_cursor = None
        
        print("Fetching invoices from Jobber...")
        
        while has_next_page:
            result = self.fetch_jobber_invoices(
                after_cursor=after_cursor,
                limit=8,  # Max safe batch size to stay under 10,000 query cost limit
                start_date=start_date
            )
            
            if "errors" in result:
                raise Exception(f"Jobber API error: {result['errors']}")
            
            data = result["data"]["invoices"]
            invoices = data["nodes"]
            page_info = data["pageInfo"]
            
            all_invoices.extend(invoices)
            
            has_next_page = page_info["hasNextPage"]
            after_cursor = page_info["endCursor"]
            
            print(f"Fetched {len(invoices)} invoices (total: {len(all_invoices)})")
        
        print(f"✓ Fetched {len(all_invoices)} total invoices from Jobber")
        return all_invoices
    
    def create_ledger_entry_for_invoice(self, invoice: Dict) -> Dict:
        """
        Create a ledger entry for an invoice
        
        Accounting entry:
        DR Accounts Receivable (1200)
        CR Revenue - Taxable (4024) or Non-Taxable (4025)
        CR Sales Tax Payable (2011)
        """
        # Get customer name
        client = invoice["client"]
        customer_name = client.get("companyName") or f"{client.get('firstName', '')} {client.get('lastName', '')}".strip()
        
        # Parse amounts from the amounts object
        amounts = invoice["amounts"]
        total = Decimal(str(amounts["total"]))
        tax_amount = Decimal(str(amounts.get("taxAmount", 0)))
        subtotal = Decimal(str(amounts["subtotal"]))
        
        # Determine if invoice is taxable based on line items
        line_items_data = invoice["lineItems"]["nodes"]
        has_taxable_items = any(item.get("taxable", False) for item in line_items_data)
        
        # Build line items
        line_items = []
        
        # DR Accounts Receivable
        line_items.append({
            "accountNumber": self.ar_account,
            "debitAmount": str(total),
            "creditAmount": "0",
            "description": f"Invoice #{invoice['invoiceNumber']} - {customer_name}"
        })
        
        # CR Revenue (taxable or non-taxable)
        if has_taxable_items:
            revenue_account = self.revenue_account_taxable
            revenue_desc = "Revenue - Taxable Services"
        else:
            revenue_account = self.revenue_account_nontaxable
            revenue_desc = "Revenue - Non-Taxable Services"
        
        line_items.append({
            "accountNumber": revenue_account,
            "debitAmount": "0",
            "creditAmount": str(subtotal),
            "description": revenue_desc
        })
        
        # CR Sales Tax Payable (if applicable)
        if tax_amount > 0:
            line_items.append({
                "accountNumber": self.tax_account,
                "debitAmount": "0",
                "creditAmount": str(tax_amount),
                "description": "Kansas Sales Tax"
            })
        
        # Create mutation
        mutation = """
        mutation CreateLedgerEntry($input: CreateLedgerEntryInput!) {
          createLedgerEntry(input: $input) {
            ledgerEntry {
              id
              entryNumber
              description
              transactionDate
              totalDebit
              totalCredit
              status
            }
            errors {
              field
              messages
            }
          }
        }
        """
        
        # Format transaction date
        issued_date = invoice.get("issuedDate")
        if issued_date:
            # Parse ISO 8601 datetime and convert to date
            transaction_date = datetime.fromisoformat(issued_date.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        else:
            transaction_date = datetime.now().strftime("%Y-%m-%d")
        
        variables = {
            "input": {
                "entitySlug": self.entity_slug,
                "description": f"Invoice #{invoice['invoiceNumber']} - {customer_name}",
                "transactionDate": transaction_date,
                "lineItems": line_items,
                "externalId": invoice["id"],
                "externalSource": "jobber"
            }
        }
        
        return self._ledgerlink_request(mutation, variables)
    
    def sync_invoices(
        self, 
        start_date: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Sync invoices from Jobber to LedgerLink
        
        Args:
            start_date: ISO date string to filter invoices (e.g., "2024-01-01")
            dry_run: If True, fetch invoices but don't post to ledger
        
        Returns:
            Dictionary with sync statistics
        """
        stats = {
            "total": 0,
            "posted": 0,
            "skipped": 0,
            "errors": 0,
            "invoices": []
        }
        
        # Fetch all invoices
        invoices = self.fetch_all_jobber_invoices(start_date=start_date)
        stats["total"] = len(invoices)
        
        if dry_run:
            print(f"\n🔍 DRY RUN: Would sync {len(invoices)} invoices")
            for inv in invoices[:5]:  # Show first 5
                amounts = inv["amounts"]
                print(f"  - Invoice #{inv['invoiceNumber']}: ${amounts['total']} ({inv['invoiceStatus']})")
            if len(invoices) > 5:
                print(f"  ... and {len(invoices) - 5} more")
            return stats
        
        # Post each invoice to the ledger
        print(f"\nPosting {len(invoices)} invoices to LedgerLink...")
        
        for invoice in invoices:
            invoice_num = invoice["invoiceNumber"]
            
            try:
                # Skip draft invoices (invoiceStatus is now an enum)
                if invoice["invoiceStatus"] == "DRAFT":
                    print(f"⊘ Skipping draft invoice #{invoice_num}")
                    stats["skipped"] += 1
                    continue
                
                # Create ledger entry
                result = self.create_ledger_entry_for_invoice(invoice)
                
                if "errors" in result and result["errors"]:
                    error_msg = f"Invoice #{invoice_num}: {result['errors']}"
                    print(f"✗ {error_msg}")
                    stats["errors"].append(error_msg)
                    continue
                
                ledger_entry = result["data"]["createLedgerEntry"]["ledgerEntry"]
                entry_errors = result["data"]["createLedgerEntry"]["errors"]
                
                if entry_errors:
                    error_msg = f"Invoice #{invoice_num}: {entry_errors}"
                    print(f"✗ {error_msg}")
                    stats["errors"].append(error_msg)
                    continue
                
                print(f"✓ Posted invoice #{invoice_num} as entry #{ledger_entry['entryNumber']}")
                stats["posted"] += 1
                stats["invoices"].append({
                    "invoice_number": invoice_num,
                    "entry_number": ledger_entry["entryNumber"],
                    "amount": invoice["amounts"]["total"]
                })
                
            except Exception as e:
                error_msg = f"Invoice #{invoice_num}: {str(e)}"
                print(f"✗ {error_msg}")
                stats["errors"].append(error_msg)
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"INVOICE SYNC SUMMARY")
        print(f"{'='*60}")
        print(f"Total Fetched: {stats['total_fetched']}")
        print(f"Posted:        {stats['posted']}")
        print(f"Skipped:       {stats['skipped']}")
        print(f"Errors:        {len(stats['errors'])}")
        
        if stats["errors"]:
            print(f"\nErrors:")
            for error in stats["errors"][:10]:  # Show first 10
                print(f"  - {error}")
            if len(stats["errors"]) > 10:
                print(f"  ... and {len(stats['errors']) - 10} more")
        
        return stats


def main():
    """Example usage"""
    import os
    
    # Configuration
    JOBBER_API_KEY = os.environ.get("JOBBER_API_KEY")
    LEDGERLINK_API_KEY = os.environ.get("LEDGERLINK_API_KEY")
    ENTITY_SLUG = "forbes-lawn-spraying-llc-dev-d6qyx55c"
    
    if not JOBBER_API_KEY or not LEDGERLINK_API_KEY:
        print("Error: Missing API keys")
        print("Set JOBBER_API_KEY and LEDGERLINK_API_KEY environment variables")
        return
    
    # Initialize service
    service = InvoiceSyncService(
        jobber_api_key=JOBBER_API_KEY,
        ledgerlink_api_key=LEDGERLINK_API_KEY,
        entity_slug=ENTITY_SLUG
    )
    
    # Sync invoices from 2024
    stats = service.sync_invoices(
        start_date="2024-01-01",
        dry_run=False  # Set to True to test without posting
    )
    
    print(f"\n✓ Sync complete!")


if __name__ == "__main__":
    main()
