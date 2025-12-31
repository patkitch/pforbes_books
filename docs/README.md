# Forbes Lawn Accounting - Phase 1 Part 3: Invoice & Payment Sync

Complete implementation of invoice and payment synchronization from Jobber to LedgerLink.

## 📋 Status Overview

### ✅ Completed
- Customer sync (83 customers)
- Ledger posting service
- All Django models and migrations
- Service items sync service
- Invoice sync service
- Payment sync service
- Complete orchestrator

### 🔄 Ready to Execute
- Service items sync
- Invoice sync (with proper accounting entries)
- Payment sync (with proper accounting entries)

## 🏗️ Architecture

### Files Structure
```
forbes-lawn-accounting/
├── service_items_sync_service.py    # Sync service items from Jobber
├── invoice_sync_service.py          # Sync invoices and post to ledger
├── payment_sync_service.py          # Sync payments and post to ledger
├── complete_sync_orchestrator.py    # Orchestrates all sync operations
└── README.md                        # This file
```

### Accounting Flow

#### Invoice Posting
When an invoice is created in Jobber, the system posts:
```
DR  Accounts Receivable (1200)      $XXX.XX
  CR  Revenue - Taxable (4024)      $XXX.XX
  CR  Sales Tax Payable (2011)      $XX.XX
```

#### Payment Posting
When a payment is received in Jobber, the system posts:
```
DR  Cash/Deposit Clearing (1000/1050)  $XXX.XX
  CR  Accounts Receivable (1200)       $XXX.XX
```

## 🚀 Setup Instructions

### Prerequisites
- Python 3.8+
- Valid Jobber API token
- Valid LedgerLink API token
- Network access to both APIs

### Installation

1. **Install dependencies**:
```bash
pip install requests --break-system-packages
```

2. **Set environment variables**:
```bash
export JOBBER_API_KEY="your-jobber-api-key-here"
export LEDGERLINK_API_KEY="your-ledgerlink-api-key-here"
```

### Getting a Fresh Jobber Token

If your Jobber token has expired, you'll need to refresh it:

1. Go to Jobber Developer Console: https://developer.getjobber.com/
2. Navigate to your app
3. Go to OAuth settings
4. Generate a new access token
5. Update your environment variable:
```bash
export JOBBER_API_KEY="new-token-here"
```

## 📖 Usage Guide

### Option 1: Complete Sync (Recommended)

Run the complete sync orchestrator to sync everything at once:

```bash
python complete_sync_orchestrator.py
```

This will:
1. Sync service items from Jobber (saved to `service_items.json`)
2. Sync and post all invoices to the ledger
3. Sync and post all payments to the ledger

**Configuration Options** (edit in `main()` function):
```python
START_DATE = "2024-01-01"      # Sync from this date forward
DRY_RUN = False                # Set True to test without posting
SKIP_SERVICE_ITEMS = False     # Set True if already synced
```

### Option 2: Individual Services

#### Sync Service Items Only
```bash
python service_items_sync_service.py
```
This fetches all products/services from Jobber and saves them to `service_items.json`.

#### Sync Invoices Only
```bash
python invoice_sync_service.py
```
This syncs invoices from Jobber and posts them to the LedgerLink ledger.

#### Sync Payments Only
```bash
python payment_sync_service.py
```
This syncs payments from Jobber and posts them to the LedgerLink ledger.

### Testing with Dry Run

Before running a live sync, test with dry run mode:

```python
# In complete_sync_orchestrator.py
DRY_RUN = True
```

This will:
- Fetch all data from Jobber
- Show what would be synced
- NOT post anything to the ledger

## 🔧 Configuration

### Entity Configuration
```python
ENTITY_SLUG = "forbes-lawn-spraying-llc-dev-d6qyx55c"
```

### Account Numbers
Default account configuration:

| Account | Number | Description |
|---------|--------|-------------|
| Accounts Receivable | 1200 | Customer invoices |
| Cash | 1000 | Direct deposits (credit card, ACH) |
| Deposit Clearing | 1050 | Undeposited funds (cash, check) |
| Revenue - Taxable | 4024 | Taxable services |
| Revenue - Non-Taxable | 4025 | Non-taxable services |
| Sales Tax Payable | 2011 | Kansas sales tax |

To change these, modify the initialization in each service:

```python
service = InvoiceSyncService(
    jobber_api_key=JOBBER_API_KEY,
    ledgerlink_api_key=LEDGERLINK_API_KEY,
    entity_slug=ENTITY_SLUG,
    revenue_account_taxable="4024",    # Change here
    revenue_account_nontaxable="4025", # Change here
    tax_account="2011",                # Change here
    ar_account="1200"                  # Change here
)
```

## 📊 Understanding the Output

### Service Items Sync
```
SERVICE ITEMS SYNC SUMMARY
============================================================
Total Items:     127
Taxable:         98
Non-Taxable:     29

By Category:
  Lawn Care: 45
  Pest Control: 32
  Fertilization: 28
  Other: 22
```

### Invoice Sync
```
INVOICE SYNC SUMMARY
============================================================
Total Fetched: 245
Posted:        240
Skipped:       5
Errors:        0

✓ Posted invoice #1001 as entry #LE-001
✓ Posted invoice #1002 as entry #LE-002
...
```

### Payment Sync
```
PAYMENT SYNC SUMMARY
============================================================
Total Fetched: 198
Posted:        195
Skipped:       3
Errors:        0

✓ Posted $150.00 payment from John Doe as entry #LE-250
✓ Posted $275.00 payment from ABC Corp as entry #LE-251
...
```

## 🔍 Troubleshooting

### Common Issues

#### 1. Token Expired Error
```
Error: 401 Unauthorized
```
**Solution**: Refresh your Jobber API token (see "Getting a Fresh Jobber Token" above)

#### 2. Network Access Error
```
Error: Network request denied
```
**Solution**: Ensure network access is enabled in your environment

#### 3. Missing Account Error
```
Error: Account 4024 not found
```
**Solution**: Verify account numbers exist in your Chart of Accounts

#### 4. Duplicate Entry Error
```
Error: External ID already exists
```
**Solution**: The invoice/payment was already synced. This is normal for re-runs.

### Debug Mode

To enable detailed debugging, add this at the top of your script:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📝 Data Model

### Invoice Structure (from Jobber)
```json
{
  "id": "gid://jobber/Invoice/12345",
  "invoiceNumber": "1001",
  "issuedAt": "2024-12-01T00:00:00Z",
  "total": "165.00",
  "subtotal": "150.00",
  "taxAmount": "15.00",
  "client": {
    "id": "gid://jobber/Client/67890",
    "firstName": "John",
    "lastName": "Doe"
  },
  "lineItems": [
    {
      "name": "Lawn Mowing",
      "quantity": "1",
      "unitCost": "50.00",
      "total": "50.00",
      "taxable": true
    }
  ],
  "status": {
    "value": "sent",
    "label": "Sent"
  }
}
```

### Payment Structure (from Jobber)
```json
{
  "id": "gid://jobber/Payment/54321",
  "amount": "165.00",
  "receivedOn": "2024-12-15T00:00:00Z",
  "paymentMethod": "credit_card",
  "referenceNumber": "CH-12345",
  "client": {
    "id": "gid://jobber/Client/67890"
  },
  "invoice": {
    "id": "gid://jobber/Invoice/12345",
    "invoiceNumber": "1001"
  },
  "status": {
    "value": "succeeded"
  }
}
```

## 🎯 Next Steps (Phase 2)

After completing Phase 1 Part 3:

1. **Verify Ledger Entries**
   - Review posted entries in LedgerLink
   - Verify account balances
   - Check for any errors or discrepancies

2. **Schedule Automated Sync**
   - Set up daily/weekly sync schedule
   - Monitor for sync failures
   - Set up alerts for errors

3. **Build Reports**
   - Accounts Receivable aging
   - Revenue by service type
   - Tax liability report

4. **Create Django Admin Interface**
   - View sync history
   - Manually trigger syncs
   - Review and resolve errors

## 💡 Tips & Best Practices

### 1. Always Test with Dry Run First
```python
DRY_RUN = True  # Test first!
```

### 2. Sync in Order
1. Service items (reference only)
2. Invoices (creates AR)
3. Payments (reduces AR)

### 3. Use Date Filtering
```python
START_DATE = "2024-01-01"  # Only sync recent data
```

### 4. Monitor Output Files
- `service_items.json` - Service catalog
- `sync_results.json` - Complete sync results

### 5. Handle Errors Gracefully
The system will:
- Skip already-synced items
- Log errors without stopping
- Provide detailed error messages

## 📞 Support & Resources

- **Jobber API Docs**: https://developer.getjobber.com/docs/
- **LedgerLink API Docs**: https://api.ledgerlink.io/docs/
- **Django Docs**: https://docs.djangoproject.com/

## 📄 License

Internal use only - Forbes Lawn Spraying LLC

---

**Last Updated**: December 30, 2024
**Version**: 1.0.0
**Status**: Ready for Production Testing
