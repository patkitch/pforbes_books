# Forbes Lawn Accounting - Django Project Structure

## 📁 Complete Directory Structure

```
forbes_lawn_accounting/                 # Django project root
├── manage.py
├── requirements.txt                    # ← Place requirements.txt here
│
├── forbes_lawn_accounting/             # Django project settings folder
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── accounting/                         # Main Django app
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── tests.py
│   │
│   ├── migrations/
│   │   ├── __init__.py
│   │   └── 000X_...py
│   │
│   ├── management/                     # Django management commands
│   │   ├── __init__.py
│   │   └── commands/
│   │       ├── __init__.py
│   │       ├── sync_invoices.py       # ← Command wrapper for invoice sync
│   │       ├── sync_payments.py       # ← Command wrapper for payment sync
│   │       └── sync_all.py            # ← Command wrapper for complete sync
│   │
│   └── services/                       # Business logic services
│       ├── __init__.py
│       ├── service_items_sync_service.py    # ← Place service_items_sync here
│       ├── invoice_sync_service.py          # ← Place invoice_sync here
│       ├── payment_sync_service.py          # ← Place payment_sync here
│       └── ledger_posting_service.py        # (Already exists)
│
├── scripts/                            # Standalone utility scripts
│   ├── __init__.py
│   ├── setup_check.py                  # ← Place setup_check here
│   └── complete_sync_orchestrator.py   # ← Place orchestrator here
│
├── docs/                               # Documentation
│   ├── README.md                       # ← Main documentation
│   └── QUICKSTART.md                   # ← Quick start guide
│
└── logs/                               # Log files (create if needed)
    └── sync_logs/
```

## 📋 File Placement Guide

### Core Services (Business Logic)
**Location:** `accounting/services/`

These are your core business logic services that do the actual work:

```
accounting/services/
├── __init__.py
├── service_items_sync_service.py
├── invoice_sync_service.py
├── payment_sync_service.py
└── ledger_posting_service.py
```

**Why here?** 
- Part of the Django app's business logic
- Can be imported by views, commands, and other services
- Follow Django best practices for service layer

### Django Management Commands
**Location:** `accounting/management/commands/`

Create Django management commands to run the syncs:

```
accounting/management/commands/
├── __init__.py
├── sync_invoices.py
├── sync_payments.py
├── sync_service_items.py
└── sync_all.py
```

**Usage:**
```bash
python manage.py sync_all
python manage.py sync_invoices --start-date 2024-01-01
python manage.py sync_payments --dry-run
```

### Standalone Scripts
**Location:** `scripts/` (project root level)

Utility scripts that can run independently:

```
scripts/
├── __init__.py
├── setup_check.py
└── complete_sync_orchestrator.py
```

**Usage:**
```bash
python scripts/setup_check.py
python scripts/complete_sync_orchestrator.py
```

### Documentation
**Location:** `docs/` (project root level)

```
docs/
├── README.md
├── QUICKSTART.md
└── ARCHITECTURE.md
```

### Dependencies
**Location:** Project root

```
forbes_lawn_accounting/
└── requirements.txt
```

## 🔧 Setting Up the Structure

### Step 1: Create Missing Directories

```bash
# From project root
cd forbes_lawn_accounting

# Create scripts directory
mkdir -p scripts

# Create docs directory
mkdir -p docs

# Create management commands directory
mkdir -p accounting/management/commands

# Create __init__.py files
touch scripts/__init__.py
touch accounting/management/__init__.py
touch accounting/management/commands/__init__.py
```

### Step 2: Place the Files

```bash
# Place service files
mv service_items_sync_service.py accounting/services/
mv invoice_sync_service.py accounting/services/
mv payment_sync_service.py accounting/services/

# Place scripts
mv setup_check.py scripts/
mv complete_sync_orchestrator.py scripts/

# Place documentation
mv README.md docs/
mv QUICKSTART.md docs/

# Place requirements
mv requirements.txt .
```

### Step 3: Update Import Paths

After moving files to Django structure, update imports:

**In scripts/complete_sync_orchestrator.py:**
```python
# Old imports (standalone):
from service_items_sync_service import ServiceItemsSyncService
from invoice_sync_service import InvoiceSyncService
from payment_sync_service import PaymentSyncService

# New imports (Django):
import sys
import os
import django

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'forbes_lawn_accounting.settings')
django.setup()

from accounting.services.service_items_sync_service import ServiceItemsSyncService
from accounting.services.invoice_sync_service import InvoiceSyncService
from accounting.services.payment_sync_service import PaymentSyncService
```

## 🎯 Recommended Approach: Django Management Commands

Instead of running standalone scripts, create Django management commands for better integration:

### Create: `accounting/management/commands/sync_all.py`

```python
from django.core.management.base import BaseCommand
from accounting.services.service_items_sync_service import ServiceItemsSyncService
from accounting.services.invoice_sync_service import InvoiceSyncService
from accounting.services.payment_sync_service import PaymentSyncService
import os


class Command(BaseCommand):
    help = 'Sync all data from Jobber to LedgerLink'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date for sync (YYYY-MM-DD)',
            default='2024-01-01'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without posting to ledger',
        )
        parser.add_argument(
            '--skip-service-items',
            action='store_true',
            help='Skip service items sync',
        )

    def handle(self, *args, **options):
        jobber_key = os.environ.get('JOBBER_API_KEY')
        ledgerlink_key = os.environ.get('LEDGERLINK_API_KEY')
        
        if not jobber_key or not ledgerlink_key:
            self.stdout.write(self.style.ERROR('Missing API keys!'))
            return
        
        # Run sync
        self.stdout.write(self.style.SUCCESS('Starting complete sync...'))
        
        # Initialize services
        service_items = ServiceItemsSyncService(jobber_key)
        invoices = InvoiceSyncService(
            jobber_key, 
            ledgerlink_key,
            'forbes-lawn-spraying-llc-dev-d6qyx55c'
        )
        payments = PaymentSyncService(
            jobber_key,
            ledgerlink_key, 
            'forbes-lawn-spraying-llc-dev-d6qyx55c'
        )
        
        # Execute syncs
        if not options['skip_service_items']:
            self.stdout.write('Syncing service items...')
            service_items.sync_service_items()
        
        self.stdout.write('Syncing invoices...')
        invoice_stats = invoices.sync_invoices(
            start_date=options['start_date'],
            dry_run=options['dry_run']
        )
        
        self.stdout.write('Syncing payments...')
        payment_stats = payments.sync_payments(
            start_date=options['start_date'],
            dry_run=options['dry_run']
        )
        
        self.stdout.write(self.style.SUCCESS('Sync complete!'))
```

### Usage:
```bash
# Run complete sync
python manage.py sync_all

# With options
python manage.py sync_all --start-date 2024-01-01 --dry-run

# Skip service items
python manage.py sync_all --skip-service-items
```

## 📊 Final Structure Overview

```
forbes_lawn_accounting/
│
├── accounting/services/              # ← Your sync services go here
│   ├── service_items_sync_service.py
│   ├── invoice_sync_service.py
│   ├── payment_sync_service.py
│   └── ledger_posting_service.py
│
├── accounting/management/commands/   # ← Django commands (recommended)
│   ├── sync_all.py
│   ├── sync_invoices.py
│   └── sync_payments.py
│
├── scripts/                          # ← Standalone scripts (optional)
│   ├── setup_check.py
│   └── complete_sync_orchestrator.py
│
├── docs/                             # ← Documentation
│   ├── README.md
│   └── QUICKSTART.md
│
└── requirements.txt                  # ← Dependencies
```

## 🎉 Benefits of This Structure

1. **Django Integration**: Services can access Django ORM, settings, etc.
2. **Management Commands**: Run syncs via `python manage.py`
3. **Reusable Services**: Import services anywhere in your Django app
4. **Clean Separation**: Business logic separate from infrastructure
5. **Testable**: Easy to write tests for each service
6. **Scalable**: Add new sync services easily

## 🚀 Quick Setup

```bash
# 1. Create directories
mkdir -p accounting/services accounting/management/commands scripts docs

# 2. Create __init__.py files
touch accounting/management/__init__.py
touch accounting/management/commands/__init__.py
touch scripts/__init__.py

# 3. Move files to correct locations
mv *_service.py accounting/services/
mv setup_check.py complete_sync_orchestrator.py scripts/
mv *.md docs/

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run via Django
python manage.py sync_all --dry-run
```

This structure follows Django best practices and makes your code maintainable and scalable!
