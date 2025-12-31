"""
Test invoice sync with Django environment
"""
import os
import sys
import django

# Add project to path
sys.path.insert(0, 'C:/pforbes_books')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Now import after Django setup
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService

print("Testing with Django environment...")
print(f"JOBBER_API_KEY present: {bool(os.environ.get('JOBBER_API_KEY'))}")
print(f"LEDGERLINK_API_KEY present: {bool(os.environ.get('LEDGERLINK_API_KEY'))}")

# Get keys
jobber_key = os.environ.get("JOBBER_API_KEY")
ledgerlink_key = os.environ.get("LEDGERLINK_API_KEY") or "test-key"

if not jobber_key:
    print("ERROR: JOBBER_API_KEY not found in environment!")
    sys.exit(1)

print(f"\nJobber key starts with: {jobber_key[:20]}...")

# Try to create service
service = InvoiceSyncService(
    jobber_api_key=jobber_key,
    ledgerlink_api_key=ledgerlink_key,
    entity_slug="forbes-lawn-spraying-llc-dev-d6qyx55c"
)

print("\n✓ Service created successfully")
print("\nAttempting to fetch invoices...")

try:
    result = service.fetch_jobber_invoices(limit=1, start_date="2025-01-01")
    print("\n✓ SUCCESS! Query worked!")
    print(f"Response keys: {result.keys()}")
    
    if "data" in result:
        print("✓ Got data")
    if "errors" in result:
        print(f"✗ Got errors: {result['errors']}")
        
except Exception as e:
    print(f"\n✗ ERROR: {e}")
