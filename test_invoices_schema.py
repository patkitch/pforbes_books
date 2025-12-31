"""
Test Jobber Invoices GraphQL Schema
Find what fields are actually available for invoices in the 2025-04-16 API version
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
print("TESTING JOBBER INVOICES SCHEMA")
print("="*70)
print(f"API Version: {API_VERSION}")
print()

headers = {
    "Authorization": f"Bearer {JOBBER_API_KEY}",
    "Content-Type": "application/json",
    "X-JOBBER-GRAPHQL-VERSION": API_VERSION
}

# Test 1: Get Invoice type schema
print("Test 1: Invoice Type Schema Introspection")
print("-"*70)

introspection_query = """
query {
  __type(name: "Invoice") {
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
        print("✓ SUCCESS! Available Invoice fields:")
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

# Test 2: Get InvoiceLineItem schema
print("\n\nTest 2: InvoiceLineItem Schema Introspection")
print("-"*70)

introspection_query2 = """
query {
  __type(name: "InvoiceLineItem") {
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
        json={"query": introspection_query2},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        print("✓ SUCCESS! Available InvoiceLineItem fields:")
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

# Test 3: Try a basic invoice query
print("\n\nTest 3: Basic Invoice Query (1 invoice)")
print("-"*70)

basic_query = """
query {
  invoices(first: 1) {
    nodes {
      id
      invoiceNumber
      subject
      total
      subtotal
      taxTotal
      issuedDate
      dueDate
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
        print("✓ SUCCESS! Basic invoice query works:")
        print(json.dumps(data, indent=2))
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 4: Try invoice with line items
print("\n\nTest 4: Invoice with Line Items")
print("-"*70)

lineitems_query = """
query {
  invoices(first: 1) {
    nodes {
      id
      invoiceNumber
      lineItems {
        nodes {
          id
          name
          description
          quantity
          total
        }
      }
    }
  }
}
"""

try:
    response = requests.post(
        "https://api.getjobber.com/api/graphql",
        json={"query": lineitems_query},
        headers=headers
    )
    
    data = response.json()
    
    if "errors" in data:
        print("❌ Errors:")
        print(json.dumps(data["errors"], indent=2))
    else:
        print("✓ SUCCESS! Line items query works:")
        print(json.dumps(data, indent=2))
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 5: Check filter options
print("\n\nTest 5: InvoiceFilterAttributes Schema")
print("-"*70)

filter_query = """
query {
  __type(name: "InvoiceFilterAttributes") {
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

print("\n" + "="*70)
print("TESTING COMPLETE")
print("="*70)
