"""
Jobber API Client for GraphQL queries.

Handles all communication with the Jobber GraphQL API.
"""

import requests
from django.conf import settings
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class JobberAPIError(Exception):
    """Custom exception for Jobber API errors."""
    pass


class JobberAPIClient:
    """
    Client for interacting with Jobber's GraphQL API.
    
    Usage:
        client = JobberAPIClient()
        customers = client.get_all_clients()
    """
    
    def __init__(self):
        """Initialize the Jobber API client with credentials from settings."""
        self.access_token = getattr(settings, 'JOBBER_ACCESS_TOKEN', None)
        self.api_url = 'https://api.getjobber.com/api/graphql'
        self.api_version = '2025-04-16'
        
        if not self.access_token:
            raise JobberAPIError("JOBBER_ACCESS_TOKEN not found in settings")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'X-JOBBER-GRAPHQL-VERSION': self.api_version,
            'Content-Type': 'application/json',
        }
    
    def _execute_query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """
        Execute a GraphQL query against the Jobber API.
        
        Args:
            query: GraphQL query string
            variables: Optional variables for the query
            
        Returns:
            Response data dictionary
            
        Raises:
            JobberAPIError: If the request fails or returns errors
        """
        payload = {'query': query}
        if variables:
            payload['variables'] = variables
        
        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            
            if response.status_code != 200:
                raise JobberAPIError(
                    f"API request failed with status {response.status_code}: {response.text}"
                )
            
            data = response.json()
            
            # Check for GraphQL errors
            if 'errors' in data:
                error_messages = [e.get('message', 'Unknown error') for e in data['errors']]
                raise JobberAPIError(f"GraphQL errors: {', '.join(error_messages)}")
            
            return data.get('data', {})
        
        except requests.exceptions.RequestException as e:
            raise JobberAPIError(f"Request failed: {str(e)}")
    
    def get_all_clients(self, cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all clients (customers) from Jobber.
        
        Jobber uses cursor-based pagination. This method returns one page at a time.
        
        Args:
            cursor: Optional cursor for pagination
            
        Returns:
            Dictionary with 'nodes' (list of clients) and 'pageInfo'
        """
        query = """
        query GetClients($cursor: String) {
            clients(first: 50, after: $cursor) {
                nodes {
                    id
                    firstName
                    lastName
                    companyName
                    isCompany
                    emails {
                        primary
                        address
                    }
                    phones {
                        number
                        description
                    }
                    billingAddress {
                        street1
                        street2
                        city
                        province
                        postalCode
                        country
                    }
                    clientProperties(first: 1) {
                        nodes {
                            address {
                                street1
                                street2
                                city
                                province
                                postalCode
                                country
                            }
                        }
                    }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        
        variables = {'cursor': cursor} if cursor else {}
        data = self._execute_query(query, variables)
        
        return data.get('clients', {})
    
    def get_all_products(self, cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all products/services from Jobber.
        
        Args:
            cursor: Optional cursor for pagination
            
        Returns:
            Dictionary with 'nodes' (list of products) and 'pageInfo'
        """
        query = """
        query GetProducts($cursor: String) {
            products(first: 50, after: $cursor) {
                nodes {
                    id
                    name
                    description
                    defaultUnitCost
                    taxable
                    visible
                    category {
                        id
                        name
                    }
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        
        variables = {'cursor': cursor} if cursor else {}
        data = self._execute_query(query, variables)
        
        return data.get('products', {})
    
    def get_invoices(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get invoices from Jobber.
        
        Args:
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            cursor: Optional cursor for pagination
            
        Returns:
            Dictionary with 'nodes' (list of invoices) and 'pageInfo'
        """
        # Note: Jobber's invoice query structure may vary
        # This is a basic structure - we'll refine it when testing
        query = """
        query GetInvoices($cursor: String) {
            invoices(first: 50, after: $cursor) {
                nodes {
                    id
                    invoiceNumber
                    subject
                    message
                    issueDate
                    dueDate
                    client {
                        id
                    }
                    lineItems {
                        name
                        description
                        quantity
                        unitPrice
                        total
                        taxable
                    }
                    subtotal
                    total
                    amountPaid
                    amountDue
                    taxRate
                    taxTotal
                }
                pageInfo {
                    hasNextPage
                    endCursor
                }
            }
        }
        """
        
        variables = {'cursor': cursor} if cursor else {}
        data = self._execute_query(query, variables)
        
        return data.get('invoices', {})
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test the API connection by getting account info.
        
        Returns:
            Dictionary with account information
        """
        query = """
        query {
            account {
                id
                name
            }
        }
        """
        
        data = self._execute_query(query)
        return data.get('account', {})