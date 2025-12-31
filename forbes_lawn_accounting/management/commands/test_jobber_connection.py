"""
Test Jobber API connection and token validity.

This command will:
1. Check if Jobber credentials are configured
2. Test the API token with a simple query
3. Show token expiration info
4. Guide you through refreshing if needed

Usage:
    python manage.py test_jobber_connection
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import json
from datetime import datetime


class Command(BaseCommand):
    help = 'Test Jobber API connection and token validity'
    
    def handle(self, *args, **options):
        self.stdout.write("="*60)
        self.stdout.write("JOBBER API CONNECTION TEST")
        self.stdout.write("="*60)
        
        # Step 1: Check credentials
        self.stdout.write("\n📋 Checking Jobber credentials...")
        
        client_id = getattr(settings, 'JOBBER_CLIENT_ID', None)
        client_secret = getattr(settings, 'JOBBER_CLIENT_SECRET', None)
        access_token = getattr(settings, 'JOBBER_ACCESS_TOKEN', None)
        refresh_token = getattr(settings, 'JOBBER_REFRESH_TOKEN', None)
        
        if not client_id:
            self.stdout.write(self.style.ERROR("❌ JOBBER_CLIENT_ID not found in settings"))
            return
        
        if not client_secret:
            self.stdout.write(self.style.ERROR("❌ JOBBER_CLIENT_SECRET not found in settings"))
            return
        
        if not access_token:
            self.stdout.write(self.style.ERROR("❌ JOBBER_ACCESS_TOKEN not found in settings"))
            self.stdout.write("\nYou need to get an access token from Jobber.")
            return
        
        self.stdout.write(self.style.SUCCESS("✓ Client ID found"))
        self.stdout.write(self.style.SUCCESS("✓ Client Secret found"))
        self.stdout.write(self.style.SUCCESS("✓ Access Token found"))
        
        if refresh_token:
            self.stdout.write(self.style.SUCCESS("✓ Refresh Token found"))
        else:
            self.stdout.write(self.style.WARNING("⚠ No Refresh Token found"))
        
        # Step 2: Test the API with a simple query
        self.stdout.write("\n🔌 Testing API connection...")
        
        # Simple query to get account info
        query = """
        query {
            account {
                id
                name
            }
        }
        """
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'X-JOBBER-GRAPHQL-VERSION': '2025-04-16',
            'Content-Type': 'application/json',
        }
        
        url = 'https://api.getjobber.com/api/graphql'
        
        try:
            response = requests.post(
                url,
                json={'query': query},
                headers=headers,
                timeout=10
            )
            
            self.stdout.write(f"Response Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'errors' in data:
                    self.stdout.write(self.style.ERROR("❌ API returned errors:"))
                    for error in data['errors']:
                        self.stdout.write(self.style.ERROR(f"  - {error.get('message', 'Unknown error')}"))
                    
                    # Check if it's an auth error
                    error_messages = [e.get('message', '') for e in data['errors']]
                    if any('unauthorized' in msg.lower() or 'token' in msg.lower() for msg in error_messages):
                        self.stdout.write("\n" + "="*60)
                        self.stdout.write(self.style.ERROR("TOKEN IS EXPIRED OR INVALID"))
                        self.stdout.write("="*60)
                        self._show_refresh_instructions()
                    
                elif 'data' in data and data['data'].get('account'):
                    account = data['data']['account']
                    self.stdout.write(self.style.SUCCESS("\n✅ CONNECTION SUCCESSFUL!"))
                    self.stdout.write(f"\nAccount ID: {account['id']}")
                    self.stdout.write(f"Account Name: {account['name']}")
                    self.stdout.write(self.style.SUCCESS("\n🎉 Your Jobber token is working!"))
                else:
                    self.stdout.write(self.style.ERROR("❌ Unexpected response format"))
                    self.stdout.write(f"Response: {json.dumps(data, indent=2)}")
            
            elif response.status_code == 401:
                self.stdout.write(self.style.ERROR("❌ UNAUTHORIZED - Token is invalid or expired"))
                self._show_refresh_instructions()
            
            else:
                self.stdout.write(self.style.ERROR(f"❌ API request failed with status {response.status_code}"))
                self.stdout.write(f"Response: {response.text[:500]}")
        
        except requests.exceptions.Timeout:
            self.stdout.write(self.style.ERROR("❌ Request timed out"))
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f"❌ Request failed: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Unexpected error: {e}"))
            import traceback
            self.stdout.write(traceback.format_exc())
    
    def _show_refresh_instructions(self):
        """Show instructions for refreshing the token."""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("HOW TO REFRESH YOUR TOKEN")
        self.stdout.write("="*60)
        
        self.stdout.write("""
Since your app is in DRAFT mode, you need to use the GraphiQL interface:

1. Go to: https://developer.getjobber.com/
2. Click on your app
3. Go to the GraphiQL Explorer tab
4. The interface will show your current token in the Headers section
5. Copy the Bearer token (the long string after "Bearer ")
6. Update your .env file with the new token:
   JOBBER_ACCESS_TOKEN=your_new_token_here

OR run this command to help you refresh:
    python manage.py refresh_jobber_token

The token you have in the screenshot looks like:
    eyJhbGciOi...ImJdZCI...

Make sure to copy the FULL token!
""")