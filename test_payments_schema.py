"""
Test Jobber Payments GraphQL Schema
Find what fields are actually available for payments in the 2025-04-16 API version
"""

import requests
import os
import json

JOBBER_API_KEY = os.environ.get("JOBBER_API_KEY")
API_VERSION = "2025-04-16"

if not JOBBER_API_KEY:
    print("❌ JOBBER_API_KEY not set")
    exit(1)

print("="*70)
print("TESTING JOBBER PAYMENTS SCHEMA")
print("="*70)
print(f"API Version: {API_VERSION}")
print()

headers = {
    "Authorization": f"Bearer {JOBBER_API_KEY}",
    "Content-Type": "application/json",
    "X-JOBBER-GRAPHQL-VERSION": API_VERSION
}

# Test 1: Get Payment type schema
print("Test 1: Payment Type Schema Introspection")
print("-"*70)

introspection_query = """
query {
  __type(name: "Payment") {
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

try:
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
        print("✓ SUCCESS! Available Payment fields:")
        if data.get("data") and data["data"].get("__type"):
            fields = data["data"]["__type"]["fields"]
            for field in sorted(fields, key=lambda x: x["name"]):
                field_name = field["name"]
                field_type = field["type"]["name"] or field["type"]["kind"]
                if field["type"].get("ofType"):
                    field_type += f" of {field['type']['ofType']['name']}"
                print(f"  - {field_name}: {field_type}")
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Try basic payment query
print("\n\nTest 2: Basic Payment Query (1 payment)")
print("-"*70)

basic_query = """
query {
  payments(first: 1) {
    nodes {
      id
      amount
      receivedOn
      paymentMethod
      referenceNumber
    }
  }
}
"""

try:
    response = requests.post(
        "https://api.getjobber.com/api/graphql",
        json={"query": basic_query},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        print("✓ SUCCESS! Basic payment query works:")
        print(json.dumps(data, indent=2))
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: Check PaymentFilterAttributes
print("\n\nTest 3: PaymentFilterAttributes Schema")
print("-"*70)

filter_query = """
query {
  __type(name: "PaymentFilterAttributes") {
    name
    inputFields {
      name
      type {
        name
        kind
      }
    }
  }
}
"""

try:
    response = requests.post(
        "https://api.getjobber.com/api/graphql",
        json={"query": filter_query},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        print("✓ SUCCESS! Available filter fields:")
        if data.get("data") and data["data"].get("__type"):
            fields = data["data"]["__type"]["inputFields"]
            for field in sorted(fields, key=lambda x: x["name"]):
                field_name = field["name"]
                field_type = field["type"]["name"] or field["type"]["kind"]
                print(f"  - {field_name}: {field_type}")
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 4: Payment with invoice reference
print("\n\nTest 4: Payment with Invoice Reference")
print("-"*70)

invoice_query = """
query {
  payments(first: 1) {
    nodes {
      id
      amount
      invoice {
        id
        invoiceNumber
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
        json={"query": invoice_query},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        print("✓ SUCCESS! Invoice reference works:")
        print(json.dumps(data, indent=2))
        
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*70)
print("TESTING COMPLETE")
print("="*70)
print("\nNext: Update payment_sync_service.py with correct schema")
