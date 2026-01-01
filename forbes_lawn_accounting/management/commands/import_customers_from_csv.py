"""
Import Customers from CSV files exported from Jobber
Handles both contact info and property data
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from decimal import Decimal
import csv
import os

from forbes_lawn_accounting.models import Customer
from django_ledger.models import EntityModel


class Command(BaseCommand):
    help = 'Import customers from Jobber CSV exports'

    def add_arguments(self, parser):
        parser.add_argument(
            '--contact-file',
            type=str,
            required=True,
            help='Path to Client_Contact_Info.csv'
        )
        parser.add_argument(
            '--properties-file',
            type=str,
            required=True,
            help='Path to Client_Properties.csv'
        )
        parser.add_argument(
            '--entity-slug',
            type=str,
            help='Entity slug',
            default='forbes-lawn-spraying-llc-dev-d6qyx55c'
        )

    def handle(self, *args, **options):
        """Import customers from CSV files"""
        
        contact_file = options['contact_file']
        properties_file = options['properties_file']
        entity_slug = options['entity_slug']
        
        # Validate files exist
        if not os.path.exists(contact_file):
            raise CommandError(f"Contact file not found: {contact_file}")
        
        if not os.path.exists(properties_file):
            raise CommandError(f"Properties file not found: {properties_file}")
        
        # Get entity
        try:
            entity = EntityModel.objects.get(slug=entity_slug)
        except EntityModel.DoesNotExist:
            raise CommandError(f"Entity with slug '{entity_slug}' not found")
        
        self.stdout.write("=" * 70)
        self.stdout.write("CUSTOMER IMPORT FROM CSV FILES")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Entity: {entity_slug}")
        self.stdout.write(f"Contact file: {contact_file}")
        self.stdout.write(f"Properties file: {properties_file}")
        self.stdout.write("")
        
        # Step 1: Read contact info
        self.stdout.write("Reading contact information...")
        contacts = self.read_contact_info(contact_file)
        self.stdout.write(f"  Found {len(contacts)} contacts")
        
        # Step 2: Read properties
        self.stdout.write("Reading property information...")
        properties = self.read_properties(properties_file)
        self.stdout.write(f"  Found {len(properties)} properties")
        
        # Step 3: Import customers
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("IMPORTING CUSTOMERS")
        self.stdout.write("=" * 70)
        
        created_count = 0
        updated_count = 0
        error_count = 0
        
        for contact_name, contact_data in contacts.items():
            try:
                # Get properties for this contact (may be multiple)
                customer_properties = properties.get(contact_name, [])
                
                # Use first property for service address, or billing if no properties
                if customer_properties:
                    main_property = customer_properties[0]
                else:
                    main_property = None
                
                customer, is_new = self.import_customer(
                    entity,
                    contact_name,
                    contact_data,
                    main_property
                )
                
                if is_new:
                    created_count += 1
                    self.stdout.write(f"✓ Created: {customer.name}")
                else:
                    updated_count += 1
                    self.stdout.write(f"↻ Updated: {customer.name}")
                
                # Show if customer has multiple properties
                if len(customer_properties) > 1:
                    self.stdout.write(f"  → Has {len(customer_properties)} properties")
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f"✗ Error importing {contact_name}: {e}"))
        
        # Summary
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("IMPORT COMPLETE")
        self.stdout.write("=" * 70)
        self.stdout.write(f"✓ Created: {created_count}")
        self.stdout.write(f"↻ Updated: {updated_count}")
        self.stdout.write(f"✗ Errors: {error_count}")
        self.stdout.write(f"📊 Total: {created_count + updated_count}")
        self.stdout.write("=" * 70)
    
    def read_contact_info(self, filepath):
        """Read contact info CSV file"""
        contacts = {}
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row['Contact'].strip()
                if name:
                    contacts[name] = {
                        'company': row.get('Company', '').strip(),
                        'phone': row.get('Phone', '').strip(),
                        'email': row.get('Email', '').strip(),
                        'billing_address': row.get('Billing address', '').strip(),
                        'is_lead': row.get('Lead (as of 2026-01-01 10:12)', '').strip().lower() == 'yes',
                    }
        
        return contacts
    
    def read_properties(self, filepath):
        """Read properties CSV file - may have multiple properties per client"""
        properties = {}
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                client_name = row['Client Name'].strip()
                if client_name:
                    if client_name not in properties:
                        properties[client_name] = []
                    
                    properties[client_name].append({
                        'property_name': row.get('Property Name', '').strip(),
                        'street1': row.get('Street 1', '').strip(),
                        'street2': row.get('Street 2', '').strip(),
                        'city': row.get('City', '').strip(),
                        'state': row.get('State', '').strip(),
                        'zip': row.get('ZIP code', '').strip(),
                        'tax_name': row.get('Tax name', '').strip(),
                        'tax_rate': row.get('Tax rate (%)', '').strip(),
                        'lawn_sqft': row.get('Lawn square footage', '').strip(),
                    })
        
        return properties
    
    def import_customer(self, entity, contact_name, contact_data, property_data):
        """Import a single customer"""
        
        # Parse billing address (format: "Street, City, State ZIP")
        billing_parts = self.parse_address(contact_data.get('billing_address', ''))
        
        # Service address from property
        if property_data:
            service_street = property_data['street1']
            service_street2 = property_data['street2']
            service_city = property_data['city']
            service_state = property_data['state']
            service_zip = property_data['zip']
        else:
            # If no property, use billing address for service
            service_street = billing_parts.get('street', '')
            service_street2 = ''
            service_city = billing_parts.get('city', '')
            service_state = billing_parts.get('state', '')
            service_zip = billing_parts.get('zip', '')
        
        # Generate unique jobber_id from name
        # (since we don't have real Jobber IDs from CSV)
        unique_id = f"csv-{contact_name.lower().replace(' ', '-').replace('&', 'and').replace('.', '').replace(',', '')}"
        
        # Create or update
        customer, is_new = Customer.objects.update_or_create(
            jobber_id=unique_id,
            defaults={
                'entity': entity,
                'name': contact_name,
                'jobber_client_id': unique_id,  # Set this too for consistency
                'company_name': contact_data.get('company', ''),
                'email': contact_data.get('email', ''),
                'phone': contact_data.get('phone', ''),
                
                # Billing address (from contact info)
                'billing_address_line1': billing_parts.get('street', ''),
                'billing_address_line2': '',
                'billing_city': billing_parts.get('city', ''),
                'billing_state': billing_parts.get('state', ''),
                'billing_zip': billing_parts.get('zip', ''),
                
                # Service address (from property)
                'service_address_line1': service_street,
                'service_address_line2': service_street2,
                'service_city': service_city,
                'service_state': service_state,
                'service_zip': service_zip,
                
                # Status
                'active': not contact_data.get('is_lead', False),
                'synced_at': timezone.now(),
            }
        )
        
        return customer, is_new
    
    def parse_address(self, address_str):
        """Parse Jobber's address format: '123 Main St, City, State ZIP'"""
        if not address_str:
            return {'street': '', 'city': '', 'state': '', 'zip': ''}
        
        parts = [p.strip() for p in address_str.split(',')]
        
        if len(parts) >= 3:
            street = parts[0]
            city = parts[1]
            
            # Last part is "State ZIP"
            state_zip = parts[2].split()
            state = state_zip[0] if len(state_zip) > 0 else ''
            zip_code = state_zip[1] if len(state_zip) > 1 else ''
            
            return {
                'street': street,
                'city': city,
                'state': state,
                'zip': zip_code
            }
        
        # Fallback
        return {'street': address_str, 'city': '', 'state': '', 'zip': ''}