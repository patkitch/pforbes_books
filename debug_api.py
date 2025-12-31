"""
Debug Jobber API response to see rate limit structure
"""
import os
import requests
import json

JOBBER_API_KEY = os.environ.get("JOBBER_API_KEY")

# Simplest possible query
query = """
{
  account {
    id
    name
  }
}
"""

headers = {
    "Authorization": f"Bearer {JOBBER_API_KEY}",
    "Content-Type": "application/json",
    "X-JOBBER-GRAPHQL-VERSION": "2025-04-16"
}

print("Making request to Jobber API...")
response = requests.post(
    "https://api.getjobber.com/api/graphql",
    json={"query": query},
    headers=headers
)

print(f"Status code: {response.status_code}")
print(f"\nFull response:")
print(json.dumps(response.json(), indent=2))
