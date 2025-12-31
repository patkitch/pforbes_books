"""
Payment Sync Service for Forbes Lawn Accounting
Syncs payments from Jobber to LedgerLink and posts to the accounting ledger

Updated for Jobber API 2025-04-16 with correct payment schema
"""

import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from decimal import Decimal


class PaymentSyncService:
    """Service to sync payments from Jobber to LedgerLink"""
    
    # Payment method mapping based on __typename
    PAYMENT_METHOD_MAPPING = {
        "CashPaymentRecord": {
            "account": "1050",  # Deposit Clearing
            "type": "CASH",
            "description": "Cash Payment"
        },
        "CheckPaymentRecord": {
            "account": "1050",  # Deposit Clearing
            "type": "CHECK",
            "description": "Check Payment"
        },
        "JobberPaymentsCreditCardPaymentRecord": {
            "account": "1000",  # Cash (direct deposit)
            "type": "CREDIT_CARD",
            "description": "Credit Card Payment (Jobber)"
        },
        "JobberPaymentsACHPaymentRecord": {
            "account": "1000",  # Cash (direct deposit)
            "type": "ACH",
            "description": "ACH Payment (Jobber)"
        },
        "OtherPaymentRecord": {
            "account": "1050",  # Deposit Clearing
            "type": "OTHER",
            "description": "Other Payment"
        }
    }
    
    def __init__(
        self, 
        jobber_api_key: str,
        ledgerlink_api_key: str,
        entity_slug: str,
        ar_account: str = "1200",
        cash_account: str = "1000",
        deposit_clearing_account: str = "1050"
    ):
        self.jobber_api_key = jobber_api_key
        self.ledgerlink_api_key = ledgerlink_api_key
        self.entity_slug = entity_slug
        self.ar_account = ar_account
        self.cash_account = cash_account
        self.deposit_clearing_account = deposit_clearing_account
        
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
    
    def fetch_jobber_payments(
        self, 
        after_cursor: Optional[str] = None,
        limit: int = 50,
        start_date: Optional[str] = None
    ) -> Dict:
        """
        Fetch payments from Jobber
        
        Args:
            after_cursor: Pagination cursor
            limit: Number of payments to fetch per request
            start_date: ISO date string to filter payments (e.g., "2025-01-01")
        """
        query = """
        query FetchPayments($after: String, $first: Int!, $filter: PaymentRecordFilterAttributes) {
          paymentRecords(after: $after, first: $first, filter: $filter) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              __typename
              id
              entryDate
              amount
              adjustmentType
              invoice {
                id
                invoiceNumber
              }
              client {
                id
                name
              }
              
              # Check payments
              ... on CheckPaymentRecord {
                # No additional fields needed
              }
              
              # Cash payments
              ... on CashPaymentRecord {
                # No additional fields needed
              }
              
              # Other payments
              ... on OtherPaymentRecord {
                # No additional fields needed
              }
              
              # Jobber Payments: Credit Card
              ... on JobberPaymentsCreditCardPaymentRecord {
                paymentType
                transactionStatus
                brand
                lastDigits
              }
              
              # Jobber Payments: ACH
              ... on JobberPaymentsACHPaymentRecord {
                paymentType
                transactionStatus
                bankName
                lastDigits
              }
            }
          }
        }
        """
        
        # Build filter
        filter_obj = {
            "adjustmentType": "PAYMENT"  # CRITICAL: Only get actual payments!
        }
        
        if start_date:
            filter_obj["entryDate"] = {
                "after": f"{start_date}T00:00:00Z"
            }
        
        variables = {
            "after": after_cursor,
            "first": limit,
            "filter": filter_obj
        }
        
        return self._jobber_request(query, variables)
    
    def fetch_all_jobber_payments(self, start_date: Optional[str] = None) -> List[Dict]:
        """Fetch all payments from Jobber with pagination"""
        all_payments = []
        has_next_page = True
        after_cursor = None
        
        print(f"Fetching payments from Jobber...")
        if start_date:
            print(f"  Start date: {start_date}")
        
        while has_next_page:
            result = self.fetch_jobber_payments(
                after_cursor=after_cursor,
                start_date=start_date
            )
            
            if "errors" in result:
                raise Exception(f"Jobber API error: {result['errors']}")
            
            data = result["data"]["paymentRecords"]
            payments = data["nodes"]
            page_info = data["pageInfo"]
            
            all_payments.extend(payments)
            
            has_next_page = page_info["hasNextPage"]
            after_cursor = page_info["endCursor"]
            
            print(f"  Fetched {len(payments)} payments (total: {len(all_payments)})")
        
        print(f"✓ Fetched {len(all_payments)} total payments from Jobber")
        return all_payments
    
    def create_ledger_entry_for_payment(self, payment: Dict) -> Dict:
        """
        Create a ledger entry for a payment
        
        Accounting entry:
        DR Cash (1000) or Deposit Clearing (1050)
        CR Accounts Receivable (1200)
        """
        # Get payment type and determine account
        payment_type = payment["__typename"]
        
        if payment_type not in self.PAYMENT_METHOD_MAPPING:
            # Skip refunds and unknown types
            if payment_type == "JobberPaymentsRefundPaymentRecord":
                print(f"  ⊘ Skipping refund: {payment['id']}")
                return None
            raise Exception(f"Unknown payment type: {payment_type}")
        
        method_info = self.PAYMENT_METHOD_MAPPING[payment_type]
        debit_account = method_info["account"]
        payment_desc = method_info["description"]
        
        # Get payment details
        amount = Decimal(str(payment["amount"]))
        client_name = payment["client"]["name"]
        invoice_num = payment["invoice"]["invoiceNumber"]
        entry_date = payment["entryDate"]
        
        # Format transaction date
        if entry_date:
            transaction_date = datetime.fromisoformat(entry_date.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        else:
            transaction_date = datetime.now().strftime("%Y-%m-%d")
        
        # Build line items
        line_items = []
        
        # DR Cash or Deposit Clearing
        line_items.append({
            "accountNumber": debit_account,
            "debitAmount": str(amount),
            "creditAmount": "0",
            "description": f"{payment_desc} - Invoice #{invoice_num} - {client_name}"
        })
        
        # CR Accounts Receivable
        line_items.append({
            "accountNumber": self.ar_account,
            "debitAmount": "0",
            "creditAmount": str(amount),
            "description": f"Payment for Invoice #{invoice_num}"
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
        
        variables = {
            "input": {
                "entitySlug": self.entity_slug,
                "description": f"{payment_desc} - Invoice #{invoice_num} - {client_name}",
                "transactionDate": transaction_date,
                "lineItems": line_items,
                "externalId": payment["id"],
                "externalSource": "jobber_payment"
            }
        }
        
        return self._ledgerlink_request(mutation, variables)
    
    def sync_payments(
        self, 
        start_date: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Sync payments from Jobber to LedgerLink
        
        Args:
            start_date: ISO date string (e.g., "2025-01-01")
            dry_run: If True, fetch but don't post to ledger
        
        Returns:
            Statistics dictionary
        """
        stats = {
            "total": 0,
            "posted": 0,
            "skipped": 0,
            "errors": 0,
            "payments": []
        }
        
        # Fetch all payments
        payments = self.fetch_all_jobber_payments(start_date=start_date)
        stats["total"] = len(payments)
        
        if dry_run:
            print(f"\n🔍 DRY RUN: Would sync {len(payments)} payments")
            
            # Group by type
            by_type = {}
            for pmt in payments:
                ptype = pmt["__typename"]
                by_type[ptype] = by_type.get(ptype, 0) + 1
            
            print(f"\nPayment Types:")
            for ptype, count in sorted(by_type.items()):
                method_name = self.PAYMENT_METHOD_MAPPING.get(ptype, {}).get("type", ptype)
                print(f"  {method_name}: {count}")
            
            # Show first 5
            print(f"\nFirst 5 payments:")
            for pmt in payments[:5]:
                ptype = self.PAYMENT_METHOD_MAPPING.get(pmt["__typename"], {}).get("type", pmt["__typename"])
                print(f"  - {ptype} ${pmt['amount']:.2f} for Invoice #{pmt['invoice']['invoiceNumber']}")
            
            if len(payments) > 5:
                print(f"  ... and {len(payments) - 5} more")
            
            return stats
        
        # Post each payment to the ledger
        print(f"\nPosting {len(payments)} payments to LedgerLink...")
        
        for payment in payments:
            invoice_num = payment["invoice"]["invoiceNumber"]
            payment_type = payment["__typename"]
            
            try:
                # Skip refunds
                if payment_type == "JobberPaymentsRefundPaymentRecord":
                    stats["skipped"] += 1
                    continue
                
                result = self.create_ledger_entry_for_payment(payment)
                
                if result is None:
                    stats["skipped"] += 1
                    continue
                
                if "errors" in result and result["errors"]:
                    print(f"✗ Error posting payment for invoice #{invoice_num}: {result['errors']}")
                    stats["errors"] += 1
                    continue
                
                ledger_entry = result["data"]["createLedgerEntry"]["ledgerEntry"]
                print(f"✓ Posted payment for invoice #{invoice_num} as entry #{ledger_entry['entryNumber']}")
                stats["posted"] += 1
                stats["payments"].append({
                    "invoice_number": invoice_num,
                    "entry_number": ledger_entry["entryNumber"],
                    "amount": payment["amount"],
                    "type": self.PAYMENT_METHOD_MAPPING[payment_type]["type"]
                })
                
            except Exception as e:
                print(f"✗ Error posting payment for invoice #{invoice_num}: {e}")
                stats["errors"] += 1
        
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
    service = PaymentSyncService(
        jobber_api_key=JOBBER_API_KEY,
        ledgerlink_api_key=LEDGERLINK_API_KEY,
        entity_slug=ENTITY_SLUG
    )
    
    # Sync payments (dry run)
    print("="*60)
    print("PAYMENT SYNC - DRY RUN")
    print("="*60)
    
    stats = service.sync_payments(
        start_date="2025-01-01",
        dry_run=True
    )
    
    print(f"\n{'='*60}")
    print(f"SYNC COMPLETE")
    print(f"{'='*60}")
    print(f"Total payments: {stats['total']}")
    print(f"Would post: {stats['total']}")
    
    print(f"\n✓ Payment sync ready!")


if __name__ == "__main__":
    main()