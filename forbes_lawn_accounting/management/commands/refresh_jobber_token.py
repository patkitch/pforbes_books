"""
Refresh Jobber Access Token
Uses refresh token to get a new access token before it expires
"""
from django.core.management.base import BaseCommand, CommandError
import os
import requests
from datetime import datetime


class Command(BaseCommand):
    help = 'Refresh Jobber API access token using refresh token'

    def handle(self, *args, **options):
        """Refresh the access token"""
        
        # Get credentials from environment
        client_id = os.environ.get("JOBBER_CLIENT_ID")
        client_secret = os.environ.get("JOBBER_CLIENT_SECRET")
        refresh_token = os.environ.get("JOBBER_REFRESH_TOKEN")
        
        if not all([client_id, client_secret, refresh_token]):
            raise CommandError(
                "Missing required environment variables:\n"
                "  JOBBER_CLIENT_ID\n"
                "  JOBBER_CLIENT_SECRET\n"
                "  JOBBER_REFRESH_TOKEN"
            )
        
        self.stdout.write("=" * 70)
        self.stdout.write("JOBBER TOKEN REFRESH")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Client ID: {client_id[:20]}...")
        self.stdout.write(f"Refresh Token: {refresh_token[:20]}...")
        self.stdout.write("")
        
        # Call Jobber token endpoint
        token_url = "https://api.getjobber.com/api/oauth/token"
        
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        
        self.stdout.write("🔄 Requesting new access token from Jobber...")
        
        try:
            response = requests.post(token_url, json=payload)
            
            if response.status_code != 200:
                raise CommandError(
                    f"Token refresh failed: {response.status_code}\n"
                    f"Response: {response.text}"
                )
            
            data = response.json()
            
            # Extract new tokens
            new_access_token = data.get('access_token')
            new_refresh_token = data.get('refresh_token')  # Jobber rotates refresh tokens
            expires_in = data.get('expires_in')
            
            if not new_access_token:
                raise CommandError("No access_token in response")
            
            self.stdout.write("")
            self.stdout.write("=" * 70)
            self.stdout.write("✅ TOKEN REFRESH SUCCESSFUL")
            self.stdout.write("=" * 70)
            self.stdout.write(f"New Access Token: {new_access_token[:50]}...")
            self.stdout.write(f"Token expires in: {expires_in} seconds ({expires_in // 3600} hours)")
            
            if new_refresh_token:
                self.stdout.write(f"New Refresh Token: {new_refresh_token[:50]}...")
                self.stdout.write("")
                self.stdout.write("⚠️  IMPORTANT: Jobber rotated your refresh token!")
                self.stdout.write("   Update your .env file with BOTH new tokens:")
            else:
                self.stdout.write("")
                self.stdout.write("📝 Update your .env file with the new access token:")
            
            self.stdout.write("")
            self.stdout.write("-" * 70)
            self.stdout.write("Add these to your .env file:")
            self.stdout.write("-" * 70)
            self.stdout.write(f"JOBBER_API_KEY={new_access_token}")
            
            if new_refresh_token:
                self.stdout.write(f"JOBBER_REFRESH_TOKEN={new_refresh_token}")
            
            self.stdout.write("-" * 70)
            self.stdout.write("")
            
            # Show when token will expire
            from datetime import timedelta
            expiry_time = datetime.now() + timedelta(seconds=expires_in)
            self.stdout.write(f"⏰ Token will expire at: {expiry_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.stdout.write("")
            
        except requests.exceptions.RequestException as e:
            raise CommandError(f"Network error during token refresh: {e}")
