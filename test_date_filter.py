"""
Test Iso8601DateTimeRangeInput Schema
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

print("Testing Iso8601DateTimeRangeInput Schema")
print("="*70)

# Get Iso8601DateTimeRangeInput type schema
introspection_query = """
query {
  __type(name: "Iso8601DateTimeRangeInput") {
    name
    inputFields {
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
    print("✓ Available input fields:")
    if data.get("data") and data["data"].get("__type"):
        fields = data["data"]["__type"]["inputFields"]
        for field in sorted(fields, key=lambda x: x["name"]):
            field_name = field["name"]
            field_type = field["type"]["name"] or field["type"]["kind"]
            if field["type"].get("ofType"):
                field_type += f" of {field['type']['ofType']['name']}"
            print(f"  - {field_name}: {field_type}")
    else:
        print(json.dumps(data, indent=2))

# Test with different date formats
print("\n" + "="*70)
print("Testing Date Filter Variations")
print("="*70)

# Test 1: after field
print("\nTest 1: Using 'after' field")
test_query1 = """
query {
  invoices(first: 1, filter: {issuedDate: {after: "2024-01-01T00:00:00Z"}}) {
    nodes {
      id
      invoiceNumber
      issuedDate
    }
  }
}
"""

response = requests.post(
    "https://api.getjobber.com/api/graphql",
    json={"query": test_query1},
    headers=headers
)

data = response.json()
if "errors" in data:
    print("❌ Errors with 'after'")
else:
    print("✓ Success with 'after'!")

# Test 2: gte field
print("\nTest 2: Using 'gte' field (greater than or equal)")
test_query2 = """
query {
  invoices(first: 1, filter: {issuedDate: {gte: "2024-01-01T00:00:00Z"}}) {
    nodes {
      id
      invoiceNumber
      issuedDate
    }
  }
}
"""

response = requests.post(
    "https://api.getjobber.com/api/graphql",
    json={"query": test_query2},
    headers=headers
)

data = response.json()
if "errors" in data:
    print("❌ Errors with 'gte'")
else:
    print("✓ Success with 'gte'!")
    print(json.dumps(data, indent=2))
