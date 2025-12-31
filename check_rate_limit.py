"""
Check Jobber API rate limit status
"""
import os
import requests

JOBBER_API_KEY = os.environ.get("JOBBER_API_KEY")

# Simplest possible query (low cost)
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

response = requests.post(
    "https://api.getjobber.com/api/graphql",
    json={"query": query},
    headers=headers
)

result = response.json()

if "errors" in result:
    print("❌ Error:", result["errors"][0]["message"])
else:
    # Check extensions for rate limit info
    extensions = result.get("extensions", {})
    cost = extensions.get("cost", {})
    throttle = cost.get("throttleStatus", {})
    
    print("✅ API Connection OK")
    print(f"\nRate Limit Status:")
    print(f"  Available: {throttle.get('currentlyAvailable', 'unknown')}/{throttle.get('maximumAvailable', 'unknown')}")
    print(f"  Restore rate: {throttle.get('restoreRate', 'unknown')} points/minute")
    
    available = throttle.get('currentlyAvailable', 0)
    
    if available < 500:
        print(f"\n⚠️  Low credits ({available}). Wait ~{(500-available)//500 + 1} minutes")
    elif available < 2000:
        print(f"\n⚠️  Medium credits ({available}). Simple queries only")
    else:
        print(f"\n✅ Good to go! ({available} points available)")
