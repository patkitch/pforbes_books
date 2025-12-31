"""
Test Jobber Products GraphQL Schema
Find what fields are actually available in the 2025-04-16 API version
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
print("TESTING JOBBER PRODUCTS/SERVICES SCHEMA")
print("="*70)
print(f"API Version: {API_VERSION}")
print()

# Test 1: Try to get schema introspection
print("Test 1: Basic products query (minimal fields)")
print("-"*70)

query1 = """
query {
  products(first: 1) {
    nodes {
      id
      name
      description
    }
  }
}
"""

headers = {
    "Authorization": f"Bearer {JOBBER_API_KEY}",
    "Content-Type": "application/json",
    "X-JOBBER-GRAPHQL-VERSION": API_VERSION
}

try:
    response = requests.post(
        "https://api.getjobber.com/api/graphql",
        json={"query": query1},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        print("✓ SUCCESS! Basic query works")
        print(json.dumps(data, indent=2))
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Try with taxable field
print("\n\nTest 2: Products with taxable field")
print("-"*70)

query2 = """
query {
  products(first: 1) {
    nodes {
      id
      name
      description
      taxable
    }
  }
}
"""

try:
    response = requests.post(
        "https://api.getjobber.com/api/graphql",
        json={"query": query2},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        print("✓ SUCCESS! Taxable field works")
        print(json.dumps(data, indent=2))
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: Try with category (without sub-selections)
print("\n\nTest 3: Products with category (as enum)")
print("-"*70)

query3 = """
query {
  products(first: 1) {
    nodes {
      id
      name
      description
      taxable
      category
    }
  }
}
"""

try:
    response = requests.post(
        "https://api.getjobber.com/api/graphql",
        json={"query": query3},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        print("✓ SUCCESS! Category as enum works")
        print(json.dumps(data, indent=2))
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 4: Get ALL available fields using introspection
print("\n\nTest 4: Schema introspection for ProductOrService type")
print("-"*70)

introspection_query = """
query {
  __type(name: "ProductOrService") {
    name
    fields {
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
        json={"query": introspection_query},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        print("✓ SUCCESS! Available fields:")
        if data.get("data") and data["data"].get("__type"):
            fields = data["data"]["__type"]["fields"]
            for field in fields:
                field_name = field["name"]
                field_type = field["type"]["name"] or field["type"]["kind"]
                print(f"  - {field_name}: {field_type}")
        else:
            print(json.dumps(data, indent=2))
        
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*70)
print("TESTING COMPLETE")
print("="*70)
print("\nBased on the results above, update the GraphQL query in:")
print("  forbes_lawn_accounting/services/service_items_sync_service.py")
