"""
Minimal test command - directly call Jobber API
"""

from django.core.management.base import BaseCommand, CommandError
import os
import requests


class Command(BaseCommand):
    help = 'Test Jobber API directly'

    def handle(self, *args, **options):
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY not set")
        
        self.stdout.write(f"Token starts with: {jobber_api_key[:20]}...")
        
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
            "Authorization": f"Bearer {jobber_api_key}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": "2025-04-16"
        }
        
        self.stdout.write("Making API call...")
        
        response = requests.post(
            "https://api.getjobber.com/api/graphql",
            json={"query": query},
            headers=headers
        )
        
        result = response.json()
        
        if "errors" in result:
            self.stdout.write(self.style.ERROR(f"ERROR: {result['errors']}"))
        else:
            self.stdout.write(self.style.SUCCESS("✓ API call successful!"))
            self.stdout.write(f"Account: {result['data']['account']['name']}")
            
            # Show rate limit
            extensions = result.get('extensions', {})
            cost = extensions.get('cost', {})
            throttle = cost.get('throttleStatus', {})
            available = throttle.get('currentlyAvailable', 'unknown')
            
            self.stdout.write(f"Rate limit: {available}/10000")
