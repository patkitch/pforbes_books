"""
Import Properties from CSV file exported from Jobber
Handles property data and links to customers
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from decimal import Decimal
import csv
import os

from forbes_lawn_accounting.models import Customer, Property
from django_ledger.models import EntityModel


class Command(BaseCommand):
    help = 'Import properties from Jobber CSV export'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to Client_Properties.csv'
        )
        parser.add_argument(
            '--entity-slug',
            type=str,
            help='Entity slug',
            default='forbes-lawn-spraying-llc-elg3zg1u'
        )

    def handle(self, *args, **options):
        """Import properties from CSV file"""
        
        filepath = options['file']
        entity_slug = options['entity_slug']
        
        # Validate file exists
        if not os.path.exists(filepath):
            raise CommandError(f"File not found: {filepath}")
        
        # Get entity
        try:
            entity = EntityModel.objects.get(slug=entity_slug)
        except EntityModel.DoesNotExist:
            raise CommandError(f"Entity with slug '{entity_slug}' not found")
        
        self.stdout.write("=" * 70)
        self.stdout.write("PROPERTY IMPORT FROM CSV")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Entity: {entity_slug}")
        self.stdout.write(f"File: {filepath}")
        self.stdout.write("")
        
        # Read CSV
        properties_data = self.read_properties(filepath)
        self.stdout.write(f"Found {len(properties_data)} property records")
        
        # Import
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("IMPORTING PROPERTIES")
        self.stdout.write("=" * 70)
        
        created_count = 0
        updated_count = 0
        error_count = 0
        
        for prop_data in properties_data:
            try:
                customer_name = prop_data['client_name']
                
                # Find customer
                try:
                    customer = Customer.objects.get(
                        entity=entity,
                        name=customer_name
                    )
                except Customer.DoesNotExist:
                    self.stdout.write(self.style.ERROR(
                        f"✗ Customer not found: {customer_name} - Skipping property"
                    ))
                    error_count += 1
                    continue
                
                # Create or update property
                prop, is_new = self.import_property(entity, customer, prop_data)
                
                if is_new:
                    created_count += 1
                    self.stdout.write(f"✓ Created: {customer.name} - {prop.street1}")
                else:
                    updated_count += 1
                    self.stdout.write(f"↻ Updated: {customer.name} - {prop.street1}")
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(
                    f"✗ Error: {prop_data.get('client_name', 'Unknown')} - {e}"
                ))
        
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
    
    def read_properties(self, filepath):
        """Read properties CSV file"""
        properties = []
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                properties.append({
                    'client_name': row.get('Client Name', '').strip(),
                    'property_name': row.get('Property Name', '').strip(),
                    'street1': row.get('Street 1', '').strip(),
                    'street2': row.get('Street 2', '').strip(),
                    'city': row.get('City', '').strip(),
                    'state': row.get('State', '').strip(),
                    'country': row.get('Country', '').strip(),
                    'zip_code': row.get('ZIP code', '').strip(),
                    'tax_name': row.get('Tax name', '').strip(),
                    'tax_rate': row.get('Tax rate (%)', '').strip(),
                    'lawn_sqft': row.get('Lawn square footage', '').strip(),
                })
        
        return properties
    
    def import_property(self, entity, customer, prop_data):
        """Import a single property"""
        
        # Parse lawn square footage (format: "5974.0 Sq ft")
        lawn_sqft = None
        if prop_data['lawn_sqft']:
            try:
                # Remove " Sq ft" and convert
                sqft_str = prop_data['lawn_sqft'].replace(' Sq ft', '').strip()
                if sqft_str:
                    lawn_sqft = Decimal(sqft_str)
            except:
                pass
        
        # Parse tax rate
        tax_rate = None
        if prop_data['tax_rate']:
            try:
                tax_rate = Decimal(prop_data['tax_rate'])
            except:
                pass
        
        # Generate unique identifier for deduplication
        unique_id = f"{customer.name.lower()}-{prop_data['street1'].lower()}".replace(' ', '-')
        
        # Check if customer already has a primary property
        has_primary = customer.properties.filter(is_primary=True).exists()
        
        # Create or update
        prop, is_new = Property.objects.update_or_create(
            jobber_property_id=unique_id,
            defaults={
                'customer': customer,
                'entity': entity,
                'property_name': prop_data['property_name'],
                'street1': prop_data['street1'],
                'street2': prop_data['street2'],
                'city': prop_data['city'],
                'state': prop_data['state'],
                'country': prop_data['country'],
                'zip_code': prop_data['zip_code'],
                'tax_name': prop_data['tax_name'],
                'tax_rate': tax_rate,
                'lawn_square_footage': lawn_sqft,
                'is_primary': not has_primary,  # First property is primary
                'active': True,
                'synced_at': timezone.now(),
            }
        )
        
        return prop, is_new
