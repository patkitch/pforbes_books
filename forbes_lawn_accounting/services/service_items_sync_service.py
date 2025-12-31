"""
Service Items Sync Service for Forbes Lawn Accounting
Syncs service items from Jobber (for reference/mapping purposes)
"""

import requests
from typing import Dict, List, Optional, Any
import json


class ServiceItemsSyncService:
    """Service to sync service items from Jobber"""
    
    def __init__(self, jobber_api_key: str):
        self.jobber_api_key = jobber_api_key
        self.jobber_url = "https://api.getjobber.com/api/graphql"
    
    def _jobber_request(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Make a GraphQL request to Jobber API"""
        headers = {
            "Authorization": f"Bearer {self.jobber_api_key}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": "2025-04-16"
        }
        
        response = requests.post(
            self.jobber_url,
            json={"query": query, "variables": variables or {}},
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    def fetch_jobber_products(
        self, 
        after_cursor: Optional[str] = None,
        limit: int = 100
    ) -> Dict:
        """
        Fetch products/service items from Jobber
        
        Args:
            after_cursor: Pagination cursor
            limit: Number of products to fetch per request
        """
        query = """
        query FetchProducts($after: String, $first: Int!) {
          products(after: $after, first: $first) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              name
              description
              defaultUnitCost
              internalUnitCost
              taxable
              category
            }
          }
        }
        """
        
        variables = {
            "after": after_cursor,
            "first": limit
        }
        
        return self._jobber_request(query, variables)
    
    def fetch_all_jobber_products(self) -> List[Dict]:
        """Fetch all products/service items from Jobber with pagination"""
        all_products = []
        has_next_page = True
        after_cursor = None
        
        print("Fetching service items from Jobber...")
        
        while has_next_page:
            result = self.fetch_jobber_products(after_cursor=after_cursor)
            
            if "errors" in result:
                raise Exception(f"Jobber API error: {result['errors']}")
            
            data = result["data"]["products"]
            products = data["nodes"]
            page_info = data["pageInfo"]
            
            all_products.extend(products)
            
            has_next_page = page_info["hasNextPage"]
            after_cursor = page_info["endCursor"]
            
            print(f"Fetched {len(products)} products (total: {len(all_products)})")
        
        print(f"✓ Fetched {len(all_products)} total products from Jobber")
        return all_products
    
    def sync_service_items(self, output_file: str = "service_items.json") -> Dict[str, Any]:
        """
        Sync service items from Jobber and save to a JSON file
        
        Args:
            output_file: Path to output JSON file
        
        Returns:
            Dictionary with sync statistics
        """
        stats = {
            "total_fetched": 0,
            "taxable": 0,
            "non_taxable": 0,
            "by_category": {}
        }
        
        # Fetch all products
        products = self.fetch_all_jobber_products()
        stats["total_fetched"] = len(products)
        
        # Analyze products
        for product in products:
            # Count taxable vs non-taxable
            if product.get("taxable"):
                stats["taxable"] += 1
            else:
                stats["non_taxable"] += 1
            
            # Count by category (category is now an enum: SERVICE, PRODUCT, etc.)
            category = product.get("category")
            if category:
                if category not in stats["by_category"]:
                    stats["by_category"][category] = 0
                stats["by_category"][category] += 1
        
        # Save to file
        with open(output_file, 'w') as f:
            json.dump(products, f, indent=2)
        
        print(f"\n✓ Saved {len(products)} service items to {output_file}")
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"SERVICE ITEMS SYNC SUMMARY")
        print(f"{'='*60}")
        print(f"Total Items:     {stats['total_fetched']}")
        print(f"Taxable:         {stats['taxable']}")
        print(f"Non-Taxable:     {stats['non_taxable']}")
        
        if stats["by_category"]:
            print(f"\nBy Category:")
            for category, count in sorted(stats["by_category"].items()):
                print(f"  {category}: {count}")
        
        return stats
    
    def display_products_table(self, products: List[Dict] = None):
        """Display products in a formatted table"""
        if products is None:
            products = self.fetch_all_jobber_products()
        
        print(f"\n{'='*100}")
        print(f"{'Name':<40} {'Category':<15} {'Price':<10} {'Taxable':<10} {'Internal Cost':<15}")
        print(f"{'='*100}")
        
        for product in products:
            name = product["name"][:38] + ".." if len(product["name"]) > 40 else product["name"]
            category = product.get("category", "N/A")[:13]
            default_cost = product.get("defaultUnitCost", 0)
            unit_cost = f"${default_cost:.2f}" if default_cost else "N/A"
            taxable = "Yes" if product.get("taxable") else "No"
            internal = product.get("internalUnitCost", 0)
            internal_cost = f"${internal:.2f}" if internal else "N/A"
            
            print(f"{name:<40} {category:<15} {unit_cost:<10} {taxable:<10} {internal_cost:<15}")
        
        print(f"{'='*100}")
        print(f"Total: {len(products)} products")


def main():
    """Example usage"""
    import os
    
    # Configuration
    JOBBER_API_KEY = os.environ.get("JOBBER_API_KEY")
    
    if not JOBBER_API_KEY:
        print("Error: Missing JOBBER_API_KEY")
        print("Set JOBBER_API_KEY environment variable")
        return
    
    # Initialize service
    service = ServiceItemsSyncService(jobber_api_key=JOBBER_API_KEY)
    
    # Sync service items
    stats = service.sync_service_items(output_file="service_items.json")
    
    # Optionally display products table
    print("\n📋 Would you like to see the products table? (It will be long)")
    # Uncomment to display:
    # service.display_products_table()
    
    print(f"\n✓ Sync complete!")


if __name__ == "__main__":
    main()