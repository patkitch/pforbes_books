"""
Simple Payment Sync - Fetch and Display Payments from Jobber
"""
from django.core.management.base import BaseCommand, CommandError
import os
from decimal import Decimal
from django.utils.dateparse import parse_datetime
from django_ledger.models import EntityModel
import requests
import json


class Command(BaseCommand):
    help = 'Fetch payments from Jobber and display them'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (YYYY-MM-DD)',
            default=None
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of payments to sync',
            default=None
        )
        parser.add_argument(
            '--entity-slug',
            type=str,
            help='Entity slug for payments',
            default='forbes-lawn-spraying-llc-dev-d6qyx55c'
        )

    def handle(self, *args, **options):
        jobber_api_key = os.environ.get("JOBBER_API_KEY")
        
        if not jobber_api_key:
            raise CommandError("JOBBER_API_KEY not set")
        
        start_date = options.get('start_date')
        limit = options.get('limit', 5)  # Default to 5 for testing
        entity_slug = options.get('entity_slug')
        
        self.stdout.write(f"Syncing payments to database...")
        if start_date:
            self.stdout.write(f"Start date: {start_date}")
        self.stdout.write(f"Limit: {limit}")
        self.stdout.write(f"Entity: {entity_slug}")
        
        # Fetch payments from Jobber
        payments = self.fetch_payments(jobber_api_key, start_date, limit)
        
        self.stdout.write(f"\nFetched {len(payments)} payments:")
        self.stdout.write("="*60)
        
        for payment_data in payments:
            payment_type = payment_data['__typename']
            amount = payment_data['amount']
            entry_date = payment_data.get('entryDate', 'N/A')
            payment_method = self.get_payment_method(payment_data)
            reference = self.get_reference_number(payment_data)
            
            self.stdout.write(f"\n💰 Payment: ${amount}")
            self.stdout.write(f"   Type: {payment_type}")
            self.stdout.write(f"   Date: {entry_date}")
            self.stdout.write(f"   Method: {payment_method}")
            if reference:
                self.stdout.write(f"   Reference: {reference}")
            self.stdout.write(f"   Jobber ID: {payment_data['id']}")
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(f"Total payments fetched: {len(payments)}")
        self.stdout.write("="*60)
    
    def fetch_payments(self, api_key, start_date=None, limit=5):
        """Fetch payments from Jobber API"""
        
        query = """
        query FetchPayments($first: Int!, $entryDateFilter: Iso8601DateTimeRangeInput) {
          paymentRecords(
            first: $first, 
            filter: {
              entryDate: $entryDateFilter
            }
          ) {
            nodes {
              __typename
              id
              amount
              entryDate
              ... on CashPaymentRecord { paymentType }
              ... on CheckPaymentRecord { checkNumber }
              ... on JobberPaymentsCreditCardPaymentRecord { lastDigits }
              ... on JobberPaymentsACHPaymentRecord { lastDigits }
              ... on OtherPaymentRecord { paymentType }
            }
          }
        }
        """
        
        variables = {
            "first": limit
        }
        
        if start_date:
            variables["entryDateFilter"] = {
                "after": f"{start_date}T00:00:00Z"
            }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": "2025-04-16",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
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
        
        return data['data']['paymentRecords']['nodes']
    
    def get_payment_method(self, payment_data):
        """Extract payment method from payment data"""
        payment_type = payment_data['__typename']
        
        if payment_type == 'CashPaymentRecord':
            return payment_data.get('paymentType') or 'Cash'
        elif payment_type == 'CheckPaymentRecord':
            return 'Check'
        elif payment_type == 'JobberPaymentsCreditCardPaymentRecord':
            return f"Credit Card ending in {payment_data.get('lastDigits', '****')}"
        elif payment_type == 'JobberPaymentsACHPaymentRecord':
            return f"ACH ending in {payment_data.get('lastDigits', '****')}"
        elif payment_type == 'OtherPaymentRecord':
            return payment_data.get('paymentType') or 'Other'
        else:
            return 'Unknown'
    
    def get_reference_number(self, payment_data):
        """Extract reference number from payment data"""
        payment_type = payment_data['__typename']
        
        if payment_type == 'CheckPaymentRecord':
            return payment_data.get('checkNumber', '')
        elif payment_type in ['JobberPaymentsCreditCardPaymentRecord', 'JobberPaymentsACHPaymentRecord']:
            return f"****{payment_data.get('lastDigits', '****')}"
        
        return ''