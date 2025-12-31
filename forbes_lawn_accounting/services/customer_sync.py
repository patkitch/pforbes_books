"""
Customer Sync Service - Syncs customers from Jobber to Forbes Lawn Accounting.

This service:
1. Fetches clients from Jobber API
2. Creates or updates Customer records in Forbes Lawn Accounting
3. Links to Django Ledger CustomerModel (optional)
"""

from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django_ledger.models.entity import EntityModel
from django_ledger.models.customer import CustomerModel as LedgerCustomerModel
from forbes_lawn_accounting.models import Customer
from forbes_lawn_accounting.services.jobber_api import JobberAPIClient
import logging

logger = logging.getLogger(__name__)


class CustomerSyncService:
    """
    Service for syncing customers from Jobber to Forbes Lawn Accounting.
    
    Usage:
        from django_ledger.models.entity import EntityModel
        
        entity = EntityModel.objects.get(slug='forbes-lawn-spraying-llc-dev-d6qyx55c')
        syncer = CustomerSyncService(entity)
        
        # Sync all customers
        results = syncer.sync_all_customers()
        print(f"Created: {results['created']}, Updated: {results['updated']}")
    """
    
    def __init__(self, entity: EntityModel):
        """
        Initialize the customer sync service.
        
        Args:
            entity: The Forbes Lawn entity to sync customers for
        """
        self.entity = entity
        self.api_client = JobberAPIClient()
    
    @transaction.atomic
    def sync_customer_from_jobber_data(self, jobber_client: dict) -> tuple[Customer, bool]:
        """
        Sync a single customer from Jobber data.
        
        Args:
            jobber_client: Dictionary of client data from Jobber API
            
        Returns:
            Tuple of (Customer instance, created boolean)
        """
        jobber_id = jobber_client['id']
        
        # Extract customer info
        first_name = jobber_client.get('firstName', '')
        last_name = jobber_client.get('lastName', '')
        company_name = jobber_client.get('companyName', '')
        
        # Build customer name
        if company_name:
            customer_name = company_name
        elif first_name or last_name:
            customer_name = f"{first_name} {last_name}".strip()
        else:
            customer_name = f"Jobber Client {jobber_id}"
        
        # Extract email (primary email)
        email = ''
        emails = jobber_client.get('emails', [])
        if emails:
            # Find primary email
            primary_emails = [e for e in emails if e.get('primary')]
            if primary_emails:
                email = primary_emails[0].get('address', '')
            elif emails:
                email = emails[0].get('address', '')
        
        # Extract phone (primary phone)
        phone = ''
        phones = jobber_client.get('phones', [])
        if phones:
            phone = phones[0].get('number', '')
        
        # Extract billing address
        billing = jobber_client.get('billingAddress', {}) or {}
        billing_line1 = billing.get('street1', '')
        billing_line2 = billing.get('street2', '')
        billing_city = billing.get('city', '')
        billing_state = billing.get('province', '')  # Jobber uses 'province'
        billing_zip = billing.get('postalCode', '')
        
        # Extract service address from clientProperties (first property)
        service_line1 = ''
        service_line2 = ''
        service_city = ''
        service_state = ''
        service_zip = ''
        
        client_properties = jobber_client.get('clientProperties', {})
        property_nodes = client_properties.get('nodes', [])
        if property_nodes:
            # Get first property's address
            first_property = property_nodes[0]
            service_address = first_property.get('address', {}) or {}
            service_line1 = service_address.get('street1', '')
            service_line2 = service_address.get('street2', '')
            service_city = service_address.get('city', '')
            service_state = service_address.get('province', '')
            service_zip = service_address.get('postalCode', '')
        
        # Get or create the customer
        customer, created = Customer.objects.update_or_create(
            entity=self.entity,
            jobber_id=jobber_id,
            defaults={
                'name': customer_name,
                'company_name': company_name,
                'email': email[:254] if email else '',  # Django email field max length
                'phone': phone[:20] if phone else '',
                'billing_address_line1': billing_line1[:255] if billing_line1 else '',
                'billing_address_line2': billing_line2[:255] if billing_line2 else '',
                'billing_city': billing_city[:100] if billing_city else '',
                'billing_state': billing_state[:2] if billing_state else '',
                'billing_zip': billing_zip[:10] if billing_zip else '',
                'service_address_line1': service_line1[:255] if service_line1 else '',
                'service_address_line2': service_line2[:255] if service_line2 else '',
                'service_city': service_city[:100] if service_city else '',
                'service_state': service_state[:2] if service_state else '',
                'service_zip': service_zip[:10] if service_zip else '',
                'active': True,
                'synced_at': timezone.now(),
                'jobber_raw': jobber_client,
                'jobber_client_id': jobber_id,  # Store in both fields for now
            }
        )
        
        # Optionally create Django Ledger customer (if not already exists)
        # We'll skip this for now and do it manually when needed
        
        return customer, created
    
    def sync_all_customers(self, max_pages: int = 100) -> dict:
        """
        Sync all customers from Jobber.
        
        Args:
            max_pages: Maximum number of pages to fetch (safety limit)
            
        Returns:
            Dictionary with sync statistics:
            - created: Number of customers created
            - updated: Number of customers updated
            - errors: Number of errors
            - total: Total customers processed
        """
        stats = {
            'created': 0,
            'updated': 0,
            'errors': 0,
            'total': 0,
        }
        
        cursor = None
        page_count = 0
        
        logger.info("Starting customer sync from Jobber...")
        
        while page_count < max_pages:
            try:
                # Fetch page of clients
                result = self.api_client.get_all_clients(cursor=cursor)
                
                clients = result.get('nodes', [])
                page_info = result.get('pageInfo', {})
                
                logger.info(f"Fetched {len(clients)} clients from Jobber (page {page_count + 1})")
                
                # Process each client
                for client_data in clients:
                    try:
                        customer, created = self.sync_customer_from_jobber_data(client_data)
                        
                        if created:
                            stats['created'] += 1
                            logger.info(f"Created customer: {customer.name}")
                        else:
                            stats['updated'] += 1
                            logger.info(f"Updated customer: {customer.name}")
                        
                        stats['total'] += 1
                    
                    except Exception as e:
                        stats['errors'] += 1
                        logger.error(f"Error syncing client {client_data.get('id')}: {e}")
                
                # Check if there are more pages
                if not page_info.get('hasNextPage', False):
                    break
                
                cursor = page_info.get('endCursor')
                page_count += 1
            
            except Exception as e:
                logger.error(f"Error fetching clients from Jobber: {e}")
                break
        
        logger.info(f"Customer sync complete: {stats}")
        return stats