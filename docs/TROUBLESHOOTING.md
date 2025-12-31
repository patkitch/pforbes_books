# Troubleshooting Guide - Forbes Lawn Accounting

## Error: "Invalid line: ﻿# =============="

This error is caused by a **BOM (Byte Order Mark)** character at the beginning of your `requirements.txt` file.

### Fix Option 1: Re-save the file
1. Open `requirements.txt` in VS Code or Notepad++
2. Look for encoding in the bottom right (it might say "UTF-8 with BOM")
3. Click on it and select "UTF-8" (without BOM)
4. Save the file

### Fix Option 2: Create a clean requirements.txt
```powershell
# Delete the old one
Remove-Item requirements.txt

# Create a new one
"requests>=2.31.0" | Out-File -Encoding utf8 requirements.txt
```

### Fix Option 3: Edit with Python
```python
# Run this in Python
with open('requirements.txt', 'r', encoding='utf-8-sig') as f:
    content = f.read()

with open('requirements.txt', 'w', encoding='utf-8') as f:
    f.write(content)
```

---

## Error: "No module named 'accounting.services.payment_sync_service'"

This means the Django command files have the wrong import paths.

### The Problem
The commands were trying to import from:
```python
from accounting.services.payment_sync_service import PaymentSyncService
```

But your app is named `forbes_lawn_accounting`, not `accounting`.

### The Fix
Update all Django command files to use:
```python
from forbes_lawn_accounting.services.payment_sync_service import PaymentSyncService
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService
from forbes_lawn_accounting.services.service_items_sync_service import ServiceItemsSyncService
```

The fixed files have been updated and are ready to download again.

---

## Setting Environment Variables in PowerShell

Since you're on Windows, use PowerShell syntax:

### Temporary (Current Session Only)
```powershell
$env:JOBBER_API_KEY = "your-jobber-api-key-here"
$env:LEDGERLINK_API_KEY = "your-ledgerlink-api-key-here"
```

### Permanent (All Sessions)
```powershell
[System.Environment]::SetEnvironmentVariable('JOBBER_API_KEY', 'your-jobber-api-key-here', 'User')
[System.Environment]::SetEnvironmentVariable('LEDGERLINK_API_KEY', 'your-ledgerlink-api-key-here', 'User')
```

After setting permanently, restart PowerShell.

### Verify They're Set
```powershell
echo $env:JOBBER_API_KEY
echo $env:LEDGERLINK_API_KEY
```

---

## Complete Setup Checklist

### ✅ Step 1: File Placement
Make sure files are in the correct locations:

```
pforbes_books/
├── forbes_lawn_accounting/
│   ├── services/
│   │   ├── service_items_sync_service.py    # ← Place here
│   │   ├── invoice_sync_service.py          # ← Place here
│   │   └── payment_sync_service.py          # ← Place here
│   │
│   └── management/commands/
│       ├── sync_all.py                      # ← Place here
│       ├── sync_invoices.py                 # ← Place here
│       ├── sync_payments.py                 # ← Place here
│       └── sync_service_items.py            # ← Place here
│
└── scripts/
    └── setup_check.py                       # ← Place here
```

### ✅ Step 2: Fix requirements.txt
Remove the BOM character (see above).

### ✅ Step 3: Set API Keys
```powershell
$env:JOBBER_API_KEY = "your-key"
$env:LEDGERLINK_API_KEY = "your-key"
```

### ✅ Step 4: Verify Setup
```powershell
python scripts/setup_check.py
```

### ✅ Step 5: Test Sync
```powershell
python manage.py sync_service_items
python manage.py sync_invoices --start-date 2024-01-01 --dry-run
python manage.py sync_payments --dry-run
```

### ✅ Step 6: Run Complete Sync
```powershell
python manage.py sync_all --start-date 2024-01-01 --dry-run
```

---

## Quick Command Reference

### Individual Syncs
```powershell
# Service items (no dates needed)
python manage.py sync_service_items

# Invoices (with date filter)
python manage.py sync_invoices --start-date 2024-01-01

# Payments (with date filter)
python manage.py sync_payments --start-date 2024-01-01

# Dry run (test mode)
python manage.py sync_invoices --start-date 2024-01-01 --dry-run
```

### Complete Sync
```powershell
# Sync everything
python manage.py sync_all --start-date 2024-01-01

# Test mode
python manage.py sync_all --start-date 2024-01-01 --dry-run

# Skip service items if already synced
python manage.py sync_all --start-date 2024-01-01 --skip-service-items
```

### Check Status
```powershell
# Verify environment
python scripts/setup_check.py

# Check if files are in place
Get-ChildItem forbes_lawn_accounting/services/*.py
Get-ChildItem forbes_lawn_accounting/management/commands/sync_*.py
```

---

## Common Errors and Fixes

### Error: "ModuleNotFoundError: No module named 'forbes_lawn_accounting'"
**Fix:** Make sure you're in the project root (`pforbes_books`) when running commands.

### Error: "JOBBER_API_KEY environment variable not set"
**Fix:** Set the environment variables (see above).

### Error: "401 Unauthorized" from Jobber
**Fix:** Your token expired. Get a new one from https://developer.getjobber.com/

### Error: "ImportError: cannot import name 'ServiceItemsSyncService'"
**Fix:** Make sure the service files are in `forbes_lawn_accounting/services/`

---

## Getting a Fresh Jobber Token

1. Go to: https://developer.getjobber.com/
2. Log in with your Jobber account
3. Go to your app → OAuth settings
4. Click "Generate Access Token"
5. Copy the token
6. Set it in PowerShell:
   ```powershell
   $env:JOBBER_API_KEY = "paste-token-here"
   ```

---

## Need Help?

1. Run setup check: `python scripts/setup_check.py`
2. Check file locations: See FILE_PLACEMENT_GUIDE.md
3. Verify imports: Make sure all imports use `forbes_lawn_accounting` (not `accounting`)
4. Check API keys: `echo $env:JOBBER_API_KEY`
