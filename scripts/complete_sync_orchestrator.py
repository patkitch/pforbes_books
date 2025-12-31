"""
Complete Sync Orchestrator for Forbes Lawn Accounting
Orchestrates the complete sync process: Service Items -> Invoices -> Payments
"""

import os
from datetime import datetime
from typing import Optional, Dict, Any
from service_items_sync_service import ServiceItemsSyncService
from invoice_sync_service import InvoiceSyncService
from payment_sync_service import PaymentSyncService


class ForbesLawnSyncOrchestrator:
    """Orchestrates the complete sync process from Jobber to LedgerLink"""
    
    def __init__(
        self,
        jobber_api_key: str,
        ledgerlink_api_key: str,
        entity_slug: str = "forbes-lawn-spraying-llc-dev-d6qyx55c"
    ):
        self.jobber_api_key = jobber_api_key
        self.ledgerlink_api_key = ledgerlink_api_key
        self.entity_slug = entity_slug
        
        # Initialize services
        self.service_items_service = ServiceItemsSyncService(jobber_api_key)
        self.invoice_service = InvoiceSyncService(
            jobber_api_key=jobber_api_key,
            ledgerlink_api_key=ledgerlink_api_key,
            entity_slug=entity_slug
        )
        self.payment_service = PaymentSyncService(
            jobber_api_key=jobber_api_key,
            ledgerlink_api_key=ledgerlink_api_key,
            entity_slug=entity_slug
        )
    
    def run_complete_sync(
        self,
        start_date: Optional[str] = None,
        dry_run: bool = False,
        skip_service_items: bool = False
    ) -> Dict[str, Any]:
        """
        Run complete sync process
        
        Args:
            start_date: ISO date string to filter data (e.g., "2024-01-01")
            dry_run: If True, fetch data but don't post to ledger
            skip_service_items: If True, skip service items sync (useful if already synced)
        
        Returns:
            Dictionary with complete sync statistics
        """
        print(f"{'='*70}")
        print(f"FORBES LAWN ACCOUNTING - COMPLETE SYNC")
        print(f"{'='*70}")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Entity: {self.entity_slug}")
        print(f"Start Date: {start_date or 'All Time'}")
        print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        print(f"{'='*70}\n")
        
        results = {
            "started_at": datetime.now().isoformat(),
            "entity_slug": self.entity_slug,
            "start_date": start_date,
            "dry_run": dry_run
        }
        
        # Step 1: Sync Service Items
        if not skip_service_items:
            print("\n" + "="*70)
            print("STEP 1: SYNCING SERVICE ITEMS")
            print("="*70)
            try:
                service_items_stats = self.service_items_service.sync_service_items()
                results["service_items"] = service_items_stats
            except Exception as e:
                print(f"✗ Error syncing service items: {str(e)}")
                results["service_items"] = {"error": str(e)}
        else:
            print("\n⊘ Skipping service items sync (as requested)")
            results["service_items"] = {"skipped": True}
        
        # Step 2: Sync Invoices
        print("\n" + "="*70)
        print("STEP 2: SYNCING INVOICES")
        print("="*70)
        try:
            invoice_stats = self.invoice_service.sync_invoices(
                start_date=start_date,
                dry_run=dry_run
            )
            results["invoices"] = invoice_stats
        except Exception as e:
            print(f"✗ Error syncing invoices: {str(e)}")
            results["invoices"] = {"error": str(e)}
        
        # Step 3: Sync Payments
        print("\n" + "="*70)
        print("STEP 3: SYNCING PAYMENTS")
        print("="*70)
        try:
            payment_stats = self.payment_service.sync_payments(
                start_date=start_date,
                dry_run=dry_run
            )
            results["payments"] = payment_stats
        except Exception as e:
            print(f"✗ Error syncing payments: {str(e)}")
            results["payments"] = {"error": str(e)}
        
        # Final Summary
        results["completed_at"] = datetime.now().isoformat()
        self._print_final_summary(results)
        
        return results
    
    def _print_final_summary(self, results: Dict[str, Any]):
        """Print a comprehensive summary of the sync process"""
        print("\n" + "="*70)
        print("COMPLETE SYNC SUMMARY")
        print("="*70)
        
        # Service Items
        if "service_items" in results and not results["service_items"].get("skipped"):
            si = results["service_items"]
            if "error" not in si:
                print(f"\n📦 Service Items:")
                print(f"   Total: {si.get('total_fetched', 0)}")
                print(f"   Taxable: {si.get('taxable', 0)}")
                print(f"   Non-Taxable: {si.get('non_taxable', 0)}")
        
        # Invoices
        if "invoices" in results:
            inv = results["invoices"]
            if "error" not in inv:
                print(f"\n📄 Invoices:")
                print(f"   Fetched: {inv.get('total_fetched', 0)}")
                print(f"   Posted: {inv.get('posted', 0)}")
                print(f"   Skipped: {inv.get('skipped', 0)}")
                print(f"   Errors: {len(inv.get('errors', []))}")
                
                # Calculate total revenue
                if inv.get('invoices'):
                    total_revenue = sum(float(i['amount']) for i in inv['invoices'])
                    print(f"   Total Revenue Posted: ${total_revenue:,.2f}")
        
        # Payments
        if "payments" in results:
            pmt = results["payments"]
            if "error" not in pmt:
                print(f"\n💰 Payments:")
                print(f"   Fetched: {pmt.get('total_fetched', 0)}")
                print(f"   Posted: {pmt.get('posted', 0)}")
                print(f"   Skipped: {pmt.get('skipped', 0)}")
                print(f"   Errors: {len(pmt.get('errors', []))}")
                
                # Calculate total payments
                if pmt.get('payments'):
                    total_payments = sum(float(p['amount']) for p in pmt['payments'])
                    print(f"   Total Payments Posted: ${total_payments:,.2f}")
        
        # Overall Status
        print(f"\n{'='*70}")
        has_errors = any(
            results.get(key, {}).get("errors") or results.get(key, {}).get("error")
            for key in ["service_items", "invoices", "payments"]
        )
        
        if has_errors:
            print("⚠️  COMPLETED WITH ERRORS - Review logs above")
        else:
            print("✓ SYNC COMPLETED SUCCESSFULLY")
        
        print(f"{'='*70}\n")


def main():
    """Run the complete sync"""
    # Load API keys from environment
    JOBBER_API_KEY = os.environ.get("JOBBER_API_KEY")
    LEDGERLINK_API_KEY = os.environ.get("LEDGERLINK_API_KEY")
    
    if not JOBBER_API_KEY:
        print("❌ Error: JOBBER_API_KEY environment variable not set")
        print("\nTo set it, run:")
        print('export JOBBER_API_KEY="your-jobber-api-key"')
        return
    
    if not LEDGERLINK_API_KEY:
        print("❌ Error: LEDGERLINK_API_KEY environment variable not set")
        print("\nTo set it, run:")
        print('export LEDGERLINK_API_KEY="your-ledgerlink-api-key"')
        return
    
    # Configuration
    ENTITY_SLUG = "forbes-lawn-spraying-llc-dev-d6qyx55c"
    START_DATE = "2024-01-01"  # Change this to sync from a different date
    DRY_RUN = False  # Set to True to test without posting to ledger
    SKIP_SERVICE_ITEMS = False  # Set to True if service items already synced
    
    # Initialize orchestrator
    orchestrator = ForbesLawnSyncOrchestrator(
        jobber_api_key=JOBBER_API_KEY,
        ledgerlink_api_key=LEDGERLINK_API_KEY,
        entity_slug=ENTITY_SLUG
    )
    
    # Run complete sync
    results = orchestrator.run_complete_sync(
        start_date=START_DATE,
        dry_run=DRY_RUN,
        skip_service_items=SKIP_SERVICE_ITEMS
    )
    
    # Optionally save results to JSON
    import json
    with open("sync_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"📊 Results saved to sync_results.json")


if __name__ == "__main__":
    main()
