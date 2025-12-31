"""
Search for invoices - show what's available
"""

import requests
import os
import json

JOBBER_API_KEY = os.environ.get("JOBBER_API_KEY")
API_VERSION = "2025-04-16"

headers = {
    "Authorization": f"Bearer {JOBBER_API_KEY}",
    "Content-Type": "application/json",
    "X-JOBBER-GRAPHQL-VERSION": API_VERSION
}

print("="*70)
print("Searching for Recent Invoices")
print("="*70)

# Get most recent invoices
query = """
query {
  invoices(first: 10) {
    nodes {
      id
      invoiceNumber
      subject
      issuedDate
      invoiceStatus
      amounts {
        total
      }
      client {
        firstName
        lastName
        companyName
      }
    }
  }
}
"""

try:
    response = requests.post(
        "https://api.getjobber.com/api/graphql",
        json={"query": query},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        invoices = data["data"]["invoices"]["nodes"]
        
        if len(invoices) == 0:
            print("No invoices found!")
        else:
            print(f"\nFound {len(invoices)} recent invoices:\n")
            print(f"{'#':<8} {'Client':<30} {'Total':<12} {'Status':<15} {'Date'}")
            print("="*80)
            
            for inv in invoices:
                client = inv['client']
                client_name = client.get('companyName') or f"{client.get('firstName', '')} {client.get('lastName', '')}".strip()
                client_name = client_name[:28] if len(client_name) > 28 else client_name
                
                inv_num = inv['invoiceNumber']
                total = f"${inv['amounts']['total']:.2f}"
                status = inv['invoiceStatus']
                date = inv['issuedDate'][:10] if inv['issuedDate'] else "N/A"
                
                print(f"{inv_num:<8} {client_name:<30} {total:<12} {status:<15} {date}")
            
            print("\n" + "="*70)
            print("Copy an invoice number from above to test with!")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
