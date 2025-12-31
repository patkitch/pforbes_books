# Forbes Lawn Accounting - File Placement Guide
## Based on Your Current Project Structure

Looking at your current `forbes_lawn_accounting` app structure, here's exactly where each file should go:

## 📁 Your Current Structure

```
forbes_lawn_accounting/                      # Django app (NOT the project root)
├── management/
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── sync_jobber_customers.py        # ✓ Already exists
│   │   ├── sync_jobber_items.py            # ✓ Already exists
│   │   ├── test_jobber_connection.py       # ✓ Already exists
│   │   ├── test_posting.py                 # ✓ Already exists
│   │   ├── sync_all.py                     # ← ADD THIS (new file)
│   │   ├── sync_invoices.py                # ← ADD THIS (new file)
│   │   ├── sync_payments.py                # ← ADD THIS (new file)
│   │   └── sync_service_items.py           # ← ADD THIS (new file)
│   └── __init__.py
│
├── migrations/                              # ✓ Already exists
│   ├── __init__.py
│   ├── 0001_initial.py
│   ├── 0002_serviceitem.py
│   ├── 0003_invoice_invoiceline_invoice_payment_and_more.py
│   ├── 0004_alter_serviceitem_revenue_account.py
│   └── 0005_alter_customer_company_name.py
│
├── services/                                # ✓ Already exists
│   ├── __init__.py
│   ├── customer_sync.py                    # ✓ Already exists
│   ├── jobber_api.py                       # ✓ Already exists
│   ├── ledger_posting.py                   # ✓ Already exists
│   ├── service_item_sync.py                # ✓ Already exists
│   ├── service_items_sync_service.py       # ← ADD THIS (new file)
│   ├── invoice_sync_service.py             # ← ADD THIS (new file)
│   └── payment_sync_service.py             # ← ADD THIS (new file)
│
├── admin.py
├── apps.py
├── models.py
└── __init__.py
```

## 📦 Project Root Structure (pforbes_books)

```
pforbes_books/                               # Project root
├── forbes_lawn_accounting/                  # Your app (see above)
├── forbes_lawn_billing/                     # Another app
├── forbes_lawn_dashboard/                   # Another app
├── accounting/                              # Another app
├── books/                                   # Another app
├── config/                                  # Project settings
├── scripts/                                 # ← CREATE THIS (for standalone scripts)
│   ├── __init__.py
│   ├── setup_check.py                      # ← ADD THIS (new file)
│   └── complete_sync_orchestrator.py       # ← ADD THIS (optional, if you want standalone version)
├── docs/                                    # ← CREATE THIS (for documentation)
│   ├── README.md                           # ← ADD THIS
│   ├── QUICKSTART.md                       # ← ADD THIS
│   └── ARCHITECTURE.md                     # ← ADD THIS
├── manage.py                                # ✓ Already exists
└── requirements.txt                         # ✓ Already exists (update it)
```

## 🎯 Exact File Placement

### 1. Service Files (Core Business Logic)
**Location:** `forbes_lawn_accounting/services/`

Place these 3 files here:
- `service_items_sync_service.py`
- `invoice_sync_service.py`
- `payment_sync_service.py`

**Why here?** This matches your existing pattern - you already have `customer_sync.py`, `jobber_api.py`, `ledger_posting.py`, and `service_item_sync.py` in this folder.

### 2. Django Management Commands
**Location:** `forbes_lawn_accounting/management/commands/`

Place these 4 files here:
- `sync_all.py`
- `sync_invoices.py`
- `sync_payments.py`
- `sync_service_items.py`

**Why here?** This matches your existing pattern - you already have `sync_jobber_customers.py`, `sync_jobber_items.py`, etc. in this folder.

### 3. Standalone Scripts (Optional)
**Location:** `pforbes_books/scripts/` (CREATE THIS FOLDER)

Place these 2 files here:
- `setup_check.py`
- `complete_sync_orchestrator.py` (optional)

**Why here?** These are utility scripts that run outside Django and can be kept separate from the app.

### 4. Documentation
**Location:** `pforbes_books/docs/` (CREATE THIS FOLDER)

Place these 3 files here:
- `README.md`
- `QUICKSTART.md`
- `ARCHITECTURE.md`

### 5. Requirements
**Location:** `pforbes_books/requirements.txt` (ALREADY EXISTS)

**Action:** Add this line to your existing requirements.txt:
```
requests>=2.31.0
```

## 🔧 Setup Commands

### Step 1: Create Missing Directories
```bash
# From your project root (pforbes_books)
mkdir -p scripts docs
touch scripts/__init__.py
```

### Step 2: Move Service Files
```bash
# Move the 3 service files to services/
mv service_items_sync_service.py forbes_lawn_accounting/services/
mv invoice_sync_service.py forbes_lawn_accounting/services/
mv payment_sync_service.py forbes_lawn_accounting/services/
```

### Step 3: Move Django Management Commands
```bash
# Move the 4 command files to management/commands/
mv sync_all.py forbes_lawn_accounting/management/commands/
mv sync_invoices.py forbes_lawn_accounting/management/commands/
mv sync_payments.py forbes_lawn_accounting/management/commands/
mv sync_service_items.py forbes_lawn_accounting/management/commands/
```

### Step 4: Move Scripts (Optional)
```bash
# Move utility scripts
mv setup_check.py scripts/
mv complete_sync_orchestrator.py scripts/  # optional
```

### Step 5: Move Documentation
```bash
# Move documentation files
mv README.md QUICKSTART.md ARCHITECTURE.md docs/
```

### Step 6: Update Requirements
```bash
# Add requests to requirements.txt
echo "requests>=2.31.0" >> requirements.txt
```

## 📝 Import Path Updates

After moving files to the Django app structure, the imports in your Django commands will be:

**In `forbes_lawn_accounting/management/commands/sync_all.py`:**
```python
from forbes_lawn_accounting.services.service_items_sync_service import ServiceItemsSyncService
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService
from forbes_lawn_accounting.services.payment_sync_service import PaymentSyncService
```

**In standalone scripts (`scripts/complete_sync_orchestrator.py`):**
```python
import sys
import os
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from forbes_lawn_accounting.services.service_items_sync_service import ServiceItemsSyncService
from forbes_lawn_accounting.services.invoice_sync_service import InvoiceSyncService
from forbes_lawn_accounting.services.payment_sync_service import PaymentSyncService
```

## ✅ Final Structure

```
pforbes_books/
│
├── forbes_lawn_accounting/
│   ├── management/commands/
│   │   ├── sync_all.py                     # ← NEW
│   │   ├── sync_invoices.py                # ← NEW
│   │   ├── sync_payments.py                # ← NEW
│   │   ├── sync_service_items.py           # ← NEW
│   │   ├── sync_jobber_customers.py        # ✓ Existing
│   │   └── sync_jobber_items.py            # ✓ Existing
│   │
│   └── services/
│       ├── service_items_sync_service.py   # ← NEW
│       ├── invoice_sync_service.py         # ← NEW
│       ├── payment_sync_service.py         # ← NEW
│       ├── customer_sync.py                # ✓ Existing
│       ├── jobber_api.py                   # ✓ Existing
│       ├── ledger_posting.py               # ✓ Existing
│       └── service_item_sync.py            # ✓ Existing
│
├── scripts/                                 # ← NEW FOLDER
│   ├── setup_check.py                      # ← NEW
│   └── complete_sync_orchestrator.py       # ← NEW (optional)
│
├── docs/                                    # ← NEW FOLDER
│   ├── README.md                           # ← NEW
│   ├── QUICKSTART.md                       # ← NEW
│   └── ARCHITECTURE.md                     # ← NEW
│
└── requirements.txt                         # ✓ Update with requests
```

## 🚀 Usage After Setup

### Run via Django Management Commands (Recommended)
```bash
# From project root (pforbes_books)
python manage.py sync_all --start-date 2024-01-01 --dry-run
python manage.py sync_invoices --start-date 2024-01-01
python manage.py sync_payments --dry-run
python manage.py sync_service_items
```

### Run via Standalone Scripts (Optional)
```bash
# From project root (pforbes_books)
python scripts/setup_check.py
python scripts/complete_sync_orchestrator.py
```

## 📊 Summary

**Total NEW files to add:** 10
- 3 service files → `forbes_lawn_accounting/services/`
- 4 command files → `forbes_lawn_accounting/management/commands/`
- 2 script files → `scripts/` (optional)
- 3 doc files → `docs/`

**Folders to CREATE:** 2
- `scripts/`
- `docs/`

This structure matches your existing conventions and integrates seamlessly with your current project!
