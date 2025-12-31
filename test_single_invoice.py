"""
Test Single Invoice Fetch - Invoice #754
"""

import requests
import os
import json

JOBBER_API_KEY = os.environ.get("JOBBER_API_KEY")
LEDGERLINK_API_KEY = os.environ.get("LEDGERLINK_API_KEY")
API_VERSION = "2025-04-16"
ENTITY_SLUG = "forbes-lawn-spraying-llc-dev-d6qyx55c"

headers = {
    "Authorization": f"Bearer {JOBBER_API_KEY}",
    "Content-Type": "application/json",
    "X-JOBBER-GRAPHQL-VERSION": API_VERSION
}

print("="*70)
print("Testing Invoice #754 Fetch")
print("="*70)

# Query for recent invoices (we'll find #754 in the results)
query = """
query {
  invoices(first: 20) {
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

try:
    response = requests.post(
        "https://api.getjobber.com/api/graphql",
        json={"query": query},
        headers=headers
    )
    
    data = response.json()
    
    # Debug: print the actual response
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    elif "data" not in data:
        print("❌ Unexpected response format:")
        print(json.dumps(data, indent=2))
    else:
        print("✓ Success! Searching for invoice #754...")
        invoices = data["data"]["invoices"]["nodes"]
        
        # Find invoice #754
        invoice = None
        for inv in invoices:
            if inv["invoiceNumber"] == "754":
                invoice = inv
                break
        
        if not invoice:
            print("❌ Invoice #754 not found in recent invoices")
            print(f"Found these invoice numbers: {[inv['invoiceNumber'] for inv in invoices]}")
        else:
            print(f"✓ Found invoice #754!")
        
            print(f"\nInvoice #{invoice['invoiceNumber']}")
            print(f"Status: {invoice['invoiceStatus']}")
            
            # Get client name
            client = invoice['client']
            client_name = client.get('companyName') or f"{client.get('firstName', '')} {client.get('lastName', '')}".strip()
            print(f"Client: {client_name}")
            print(f"Issued: {invoice['issuedDate']}")
            print(f"Total: ${invoice['amounts']['total']}")
            print(f"Subtotal: ${invoice['amounts']['subtotal']}")
            print(f"Tax: ${invoice['amounts']['taxAmount']}")
            print(f"Balance: ${invoice['amounts']['invoiceBalance']}")
            print(f"Payments: ${invoice['amounts']['paymentsTotal']}")
            
            print(f"\nLine Items ({len(invoice['lineItems']['nodes'])}):")
            for item in invoice['lineItems']['nodes']:
                taxable = "✓ Taxable" if item['taxable'] else "✗ Non-taxable"
                print(f"  - {item['name']}: ${item['totalPrice']} ({taxable})")
            
            print("\n" + "="*70)
            print("ACCOUNTING ENTRY PREVIEW")
            print("="*70)
            
            # Determine revenue account
            has_taxable = any(item['taxable'] for item in invoice['lineItems']['nodes'])
            revenue_account = "4024 (Taxable)" if has_taxable else "4025 (Non-taxable)"
            
            total = float(invoice['amounts']['total'])
            subtotal = float(invoice['amounts']['subtotal'])
            tax = float(invoice['amounts']['taxAmount'])
            
            print(f"\nDR  1200 Accounts Receivable    ${total:>10.2f}")
            print(f"  CR  {revenue_account:<25} ${subtotal:>10.2f}")
            if tax > 0:
                print(f"  CR  2011 Sales Tax Payable      ${tax:>10.2f}")
            
            print("\n" + "="*70)
            print("✓ Query structure is CORRECT!")
            print("✓ Ready to sync when rate limit resets")
            print("="*70)
        
except Exception as e:
    print(f"❌ Error: {e}")