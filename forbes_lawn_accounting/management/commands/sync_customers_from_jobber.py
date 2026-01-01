"""
Sync Customers from Jobber to Forbes Lawn Accounting
Imports all Jobber clients into the Customer model
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import os
import requests

from forbes_lawn_accounting.models import Customer
from django_ledger.models import EntityModel


class Command(BaseCommand):
    help = 'Sync customers from Jobber to database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of customers to sync (for testing)',
            default=None
        )
        parser.add_argument(
            '--entity-slug',
            type=str,
            help='Entity slug',
            default='forbes-lawn-spraying-llc-dev-d6qyx55c'
        )

    def handle(self, *args, **options):
        """Import customers from Jobber"""
        
        # Get API key
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY environment variable not set")
        
        limit = options.get('limit')
        entity_slug = options.get('entity_slug')
        
        # Get entity
        try:
            entity = EntityModel.objects.get(slug=entity_slug)
        except EntityModel.DoesNotExist:
            raise CommandError(f"Entity with slug '{entity_slug}' not found")
        
        self.stdout.write("=" * 70)
        self.stdout.write("CUSTOMER IMPORT FROM JOBBER")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Entity: {entity_slug}")
        if limit:
            self.stdout.write(f"Limit: {limit} customers")
        self.stdout.write("")
        
        # Fetch customers from Jobber
        customers = self.fetch_customers_from_jobber(jobber_api_key, limit)
        
        self.stdout.write(f"\n📥 Fetched {len(customers)} customers from Jobber")
        self.stdout.write("=" * 70)
        
        # Import to database
        created_count = 0
        updated_count = 0
        error_count = 0
        
        for customer_data in customers:
            try:
                customer, is_new = self.import_customer(entity, customer_data)
                
                if is_new:
                    created_count += 1
                    self.stdout.write(f"✓ Created: {customer.name}")
                else:
                    updated_count += 1
                    self.stdout.write(f"↻ Updated: {customer.name}")
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f"✗ Error: {customer_data.get('id', 'Unknown')} - {e}"))
        
        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("IMPORT COMPLETE")
        self.stdout.write("=" * 70)
        self.stdout.write(f"✓ Created: {created_count}")
        self.stdout.write(f"↻ Updated: {updated_count}")
        self.stdout.write(f"✗ Errors: {error_count}")
        self.stdout.write(f"📊 Total: {created_count + updated_count}")
        self.stdout.write("=" * 70)
    
    def fetch_customers_from_jobber(self, api_key, limit=None):
        """Fetch all customers from Jobber GraphQL API"""
        
        # GraphQL query for clients
        query = """
        query FetchClients($first: Int!, $after: String) {
          clients(first: $first, after: $after) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              firstName
              lastName
              companyName
              emails {
                address
                primary
              }
              phones {
                number
                primary
              }
              billingAddress {
                street1
                street2
                city
                province
                postalCode
              }
              propertyAddress {
                street1
                street2
                city
                province
                postalCode
              }
            }
          }
        }
        """
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": "2025-04-16",
        }
        
        all_customers = []
        cursor = None
        batch_size = 50  # Jobber's recommended batch size
        
        # If limit is set, adjust batch size
        if limit and limit < batch_size:
            batch_size = limit
        
        self.stdout.write("Fetching customers from Jobber...")
        
        while True:
            variables = {
                "first": batch_size,
                "after": cursor
            }
            
            response = requests.post(
                "https://api.getjobber.com/graphql",
                headers=headers,
                json={"query": query, "variables": variables}
            )
            
            if response.status_code != 200:
                raise CommandError(f"Jobber API error: {response.status_code} - {response.text}")
            
            data = response.json()
            
            if 'errors' in data:
                raise CommandError(f"GraphQL errors: {data['errors']}")
            
            clients = data['data']['clients']['nodes']
            page_info = data['data']['clients']['pageInfo']
            
            all_customers.extend(clients)
            
            self.stdout.write(f"  Fetched batch: {len(clients)} customers (Total: {len(all_customers)})")
            
            # Check if we hit the limit
            if limit and len(all_customers) >= limit:
                all_customers = all_customers[:limit]
                break
            
            # Check if there are more pages
            if not page_info['hasNextPage']:
                break
            
            cursor = page_info['endCursor']
        
        return all_customers
    
    def import_customer(self, entity, customer_data):
        """Import a single customer to database"""
        
        # Build customer name
        if customer_data.get('companyName'):
            name = customer_data['companyName']
        else:
            first = customer_data.get('firstName', '')
            last = customer_data.get('lastName', '')
            name = f"{first} {last}".strip()
        
        if not name:
            name = "Unknown Customer"
        
        # Get primary email
        email = ''
        if customer_data.get('emails'):
            for email_obj in customer_data['emails']:
                if email_obj.get('primary'):
                    email = email_obj.get('address', '')
                    break
            # If no primary, use first one
            if not email and customer_data['emails']:
                email = customer_data['emails'][0].get('address', '')
        
        # Get primary phone
        phone = ''
        if customer_data.get('phones'):
            for phone_obj in customer_data['phones']:
                if phone_obj.get('primary'):
                    phone = phone_obj.get('number', '')
                    break
            # If no primary, use first one
            if not phone and customer_data['phones']:
                phone = customer_data['phones'][0].get('number', '')
        
        # Billing address
        billing = customer_data.get('billingAddress', {}) or {}
        
        # Service/Property address
        service = customer_data.get('propertyAddress', {}) or {}
        
        # Create or update customer
        customer, is_new = Customer.objects.update_or_create(
            jobber_client_id=customer_data['id'],
            defaults={
                'entity': entity,
                'name': name,
                'company_name': customer_data.get('companyName', ''),
                'email': email,
                'phone': phone,
                
                # Billing address
                'billing_address_line1': billing.get('street1', ''),
                'billing_address_line2': billing.get('street2', ''),
                'billing_city': billing.get('city', ''),
                'billing_state': billing.get('province', ''),
                'billing_zip': billing.get('postalCode', ''),
                
                # Service address (property address in Jobber)
                'service_address_line1': service.get('street1', ''),
                'service_address_line2': service.get('street2', ''),
                'service_city': service.get('city', ''),
                'service_state': service.get('province', ''),
                'service_zip': service.get('postalCode', ''),
                
                'active': True,
                'synced_at': timezone.now(),
            }
        )
        
        return customer, is_new
