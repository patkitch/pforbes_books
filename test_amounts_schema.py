"""
Test InvoiceAmounts Schema
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

print("Testing InvoiceAmounts Schema")
print("="*70)

# Get InvoiceAmounts type schema
introspection_query = """
query {
  __type(name: "InvoiceAmounts") {
    name
    fields {
      name
      type {
        name
        kind
        ofType {
          name
          kind
        }
      }
    }
  }
}
"""

response = requests.post(
    "https://api.getjobber.com/api/graphql",
    json={"query": introspection_query},
    headers=headers
)

data = response.json()

if "errors" in data:
    print("❌ Errors:")
    print(json.dumps(data["errors"], indent=2))
else:
    print("✓ Available InvoiceAmounts fields:")
    if data.get("data") and data["data"].get("__type"):
        fields = data["data"]["__type"]["fields"]
        for field in sorted(fields, key=lambda x: x["name"]):
            field_name = field["name"]
            field_type = field["type"]["name"] or field["type"]["kind"]
            if field["type"].get("ofType"):
                field_type += f" of {field['type']['ofType']['name']}"
            print(f"  - {field_name}: {field_type}")
    else:
        print(json.dumps(data, indent=2))

# Now try a real query
print("\n" + "="*70)
print("Testing Real Invoice Query")
print("="*70)

test_query = """
query {
  invoices(first: 1) {
    nodes {
      id
      invoiceNumber
      amounts {
        total
        subtotal
      }
    }
  }
}
"""

response = requests.post(
    "https://api.getjobber.com/api/graphql",
    json={"query": test_query},
    headers=headers
)

data = response.json()

if "errors" in data:
    print("❌ Errors:")
    print(json.dumps(data["errors"], indent=2))
else:
    print("✓ Success! Response:")
    print(json.dumps(data, indent=2))
