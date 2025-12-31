# Quick Start Guide - Forbes Lawn Accounting Sync

## 🚀 Get Started in 5 Minutes

### Step 1: Set Your API Keys
```bash
export JOBBER_API_KEY="your-jobber-token-here"
export LEDGERLINK_API_KEY="your-ledgerlink-token-here"
```

**Getting a Fresh Jobber Token:**
1. Visit: https://developer.getjobber.com/
2. Navigate to your app → OAuth settings
3. Generate new access token
4. Copy and export it

### Step 2: Run Environment Check
```bash
python setup_check.py
```

This verifies:
- ✓ Python version
- ✓ Dependencies installed
- ✓ API keys set
- ✓ API connectivity
- ✓ All files present

### Step 3: Test with Dry Run
```bash
# Edit complete_sync_orchestrator.py
# Set: DRY_RUN = True

python complete_sync_orchestrator.py
```

This will show what would be synced without actually posting to the ledger.

### Step 4: Run Live Sync
```bash
# Edit complete_sync_orchestrator.py
# Set: DRY_RUN = False

python complete_sync_orchestrator.py
```

---

## 📋 Common Commands

### Run Complete Sync
```bash
python complete_sync_orchestrator.py
```

### Run Individual Services
```bash
# Service items only
python service_items_sync_service.py

# Invoices only
python invoice_sync_service.py

# Payments only
python payment_sync_service.py
```

### Install Dependencies
```bash
pip install requests --break-system-packages
```

---

## ⚙️ Quick Configuration

Edit these variables in `complete_sync_orchestrator.py`:

```python
# What date to sync from
START_DATE = "2024-01-01"

# Test mode (doesn't post to ledger)
DRY_RUN = False

# Skip service items if already synced
SKIP_SERVICE_ITEMS = False

# Your entity
ENTITY_SLUG = "forbes-lawn-spraying-llc-dev-d6qyx55c"
```

---

## 🔧 Account Configuration

Default accounts used:

| Purpose | Account | Number |
|---------|---------|--------|
| Accounts Receivable | AR | 1200 |
| Cash | Cash | 1000 |
| Undeposited Funds | Deposit Clearing | 1050 |
| Taxable Revenue | Revenue - Taxable | 4024 |
| Non-Taxable Revenue | Revenue - Non-Taxable | 4025 |
| Sales Tax | Sales Tax Payable | 2011 |

To change these, edit the initialization in each service file.

---

## 📊 Expected Output

### Complete Sync Output
```
======================================================================
FORBES LAWN ACCOUNTING - COMPLETE SYNC
======================================================================
Started at: 2024-12-30 10:30:00
Entity: forbes-lawn-spraying-llc-dev-d6qyx55c
Start Date: 2024-01-01
Mode: LIVE
======================================================================

======================================================================
STEP 1: SYNCING SERVICE ITEMS
======================================================================
Fetching service items from Jobber...
Fetched 127 products (total: 127)
✓ Fetched 127 total products from Jobber
✓ Saved 127 service items to service_items.json

======================================================================
STEP 2: SYNCING INVOICES
======================================================================
Fetching invoices from Jobber...
Fetched 50 invoices (total: 50)
Fetched 50 invoices (total: 100)
...
✓ Fetched 245 total invoices from Jobber

Posting 245 invoices to LedgerLink...
✓ Posted invoice #1001 as entry #LE-001
✓ Posted invoice #1002 as entry #LE-002
...

INVOICE SYNC SUMMARY
============================================================
Total Fetched: 245
Posted:        240
Skipped:       5
Errors:        0

======================================================================
STEP 3: SYNCING PAYMENTS
======================================================================
Fetching payments from Jobber...
✓ Fetched 198 total payments from Jobber

Posting 198 payments to LedgerLink...
✓ Posted $150.00 payment from John Doe as entry #LE-250
...

PAYMENT SYNC SUMMARY
============================================================
Total Fetched: 198
Posted:        195
Skipped:       3
Errors:        0

======================================================================
COMPLETE SYNC SUMMARY
======================================================================

📦 Service Items:
   Total: 127
   Taxable: 98
   Non-Taxable: 29

📄 Invoices:
   Fetched: 245
   Posted: 240
   Skipped: 5
   Errors: 0
   Total Revenue Posted: $45,234.56

💰 Payments:
   Fetched: 198
   Posted: 195
   Skipped: 3
   Errors: 0
   Total Payments Posted: $42,103.22

======================================================================
✓ SYNC COMPLETED SUCCESSFULLY
======================================================================

📊 Results saved to sync_results.json
```

---

## ❓ Troubleshooting

### Problem: Token Expired
```
Error: 401 Unauthorized
```
**Fix:** Get a fresh token from https://developer.getjobber.com/

### Problem: Missing Dependency
```
ModuleNotFoundError: No module named 'requests'
```
**Fix:** `pip install requests --break-system-packages`

### Problem: Account Not Found
```
Error: Account 4024 not found
```
**Fix:** Verify account exists in your Chart of Accounts in LedgerLink

### Problem: Duplicate Entry
```
Error: External ID already exists
```
**Fix:** This is normal - the item was already synced. The system skips it automatically.

---

## 📞 Need Help?

1. Run the environment check: `python setup_check.py`
2. Review the full README: `README.md`
3. Check sync results: `sync_results.json`
4. Review service items: `service_items.json`

---

**Last Updated:** December 30, 2024
