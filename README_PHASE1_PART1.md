# Forbes Lawn Accounting - Phase 1 Part 1: Customer Model

## ✅ What We Just Built

We've created the **foundation** of the new Forbes Lawn accounting system:

### Files Created
```
forbes_lawn_accounting/
├── __init__.py          ← App initialization
├── apps.py              ← Django app configuration
├── models.py            ← Customer model (CORE)
└── admin.py             ← Django admin interface
```

---

## 📊 Customer Model Overview

The `Customer` model is the **foundation** of the entire system. Everything else (invoices, payments, etc.) links to customers.

### Key Features

#### 1. **Triple Integration**
```
Jobber Client → Customer → Django Ledger CustomerModel
```

- **Jobber side**: Stores `jobber_id` for sync/deduplication
- **Our side**: Business logic, display, workflows  
- **Ledger side**: Links to Django Ledger for accounting

#### 2. **Complete Customer Data**
- Basic info: Name, company, email, phone
- Billing address (for invoices)
- Service address (where work is performed)
- Active status

#### 3. **Sync Tracking**
- `synced_at`: When last updated from Jobber
- `jobber_raw`: Raw API response (for debugging)
- `jobber_id`: Unique identifier (prevents duplicates)

#### 4. **Smart Properties**
- `full_billing_address`: Formatted address string
- `full_service_address`: Formatted address string
- `get_balance()`: Current AR balance (will work once invoices exist)

---

## 🔧 How to Install & Test

### Step 1: Add to settings.py

Edit `config/settings.py`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    # ... other apps ...
    'django_ledger',
    'forbes_lawn_billing',      # Keep old app
    'forbes_lawn_accounting',   # ADD THIS - New app
    'jobber_sync',
    # ...
]
```

### Step 2: Create Migrations

```bash
cd /path/to/pforbes_books
python manage.py makemigrations forbes_lawn_accounting
```

Expected output:
```
Migrations for 'forbes_lawn_accounting':
  forbes_lawn_accounting/migrations/0001_initial.py
    - Create model Customer
```

### Step 3: Run Migrations

```bash
python manage.py migrate forbes_lawn_accounting
```

Expected output:
```
Running migrations:
  Applying forbes_lawn_accounting.0001_initial... OK
```

### Step 4: Test in Django Admin

```bash
python manage.py runserver
```

Go to: http://localhost:8003/admin/forbes_lawn_accounting/customer/

You should see:
- Empty customer list (no data yet - that's fine!)
- "Add Customer" button
- Search and filter options

---

## 🧪 Manual Testing (Optional)

Let's create a test customer manually to verify everything works:

### In Django Shell:
```bash
python manage.py shell
```

```python
from django_ledger.models import EntityModel
from forbes_lawn_accounting.models import Customer
from django.utils import timezone

# Get the new entity (you'll need to create this first - we'll do that next)
# For now, just test with an existing entity
entity = EntityModel.objects.first()

# Create test customer
customer = Customer.objects.create(
    entity=entity,
    jobber_id='TEST-001',
    name='Test Customer',
    email='test@example.com',
    phone='555-1234',
    billing_city='Kansas City',
    billing_state='KS',
    active=True,
    synced_at=timezone.now()
)

print(f"Created: {customer.name}")
print(f"Balance: {customer.get_balance()}")
print(f"Billing: {customer.full_billing_address}")
```

Expected output:
```
Created: Test Customer
Balance: 0.00
Billing: Kansas City, KS
```

### Clean Up Test Data:
```python
customer.delete()
```

---

## 🎯 What This Enables

With the Customer model in place, we can now:

1. ✅ Sync customers from Jobber
2. ✅ Link to Django Ledger CustomerModel
3. ✅ Track customer addresses
4. ✅ View customers in admin
5. ✅ Calculate customer balances (once invoices exist)

---

## 📝 Next Steps

Now that we have the Customer foundation, we'll build:

### Next: ServiceItem Model
- Represents lawn care services (from Jobber)
- Links to Django Ledger ItemModel
- Maps to revenue accounts (4024 Taxable, 4025 Non-Taxable)

### Then: Invoice Models
- Invoice header (customer, dates, amounts)
- InvoiceLine (services performed)
- InvoicePayment (payments received)

### Finally: Posting Logic
- Auto-post invoices to ledger (DR AR, CR Revenue, CR Tax)
- Auto-post payments to ledger (DR Payments to Deposit, CR AR)

---

## 🐛 Troubleshooting

### Error: "No module named 'forbes_lawn_accounting'"
**Solution:** Make sure you added the app to `INSTALLED_APPS` in settings.py

### Error: "django_ledger not found"
**Solution:** Django Ledger should already be installed. Check requirements.txt

### Error: "Table doesn't exist"
**Solution:** Run migrations: `python manage.py migrate`

### Can't see customers in admin
**Solution:** 
1. Make sure you're logged in as superuser
2. Check that migrations ran successfully
3. Verify app is in INSTALLED_APPS

---

## 💡 Design Decisions Explained

### Why separate Customer model from Django Ledger CustomerModel?

**Benefits:**
1. **Store Jobber metadata** (jobber_id, sync times, raw JSON)
2. **Business logic** separate from accounting logic
3. **Addresses** for service vs billing
4. **Easy to extend** without modifying Django Ledger

**Trade-off:**
- Need to keep two models in sync (but we handle this automatically)

### Why store jobber_raw JSON?

**Benefits:**
1. **Debugging** - see exactly what Jobber sent
2. **Audit trail** - prove what data looked like at sync time
3. **Recovery** - if something breaks, we can re-process

**Trade-off:**
- Uses more database space (minimal impact)

### Why both billing_address and service_address?

**Real-world need:**
- Billing address: Where to send invoices (often customer's office)
- Service address: Where work is performed (the actual lawn)
- These are often different!

---

## ✅ Validation Checklist

Before moving to next step, verify:

- [ ] App added to INSTALLED_APPS
- [ ] Migrations created successfully
- [ ] Migrations ran successfully  
- [ ] Can see "Customers" in Django admin
- [ ] Can manually create a test customer
- [ ] Test customer appears in admin
- [ ] No errors in console

---

## 🚀 Ready for Next Step?

Once you've:
1. Added the app to settings.py
2. Run migrations
3. Verified it works in admin

Let me know and we'll build the **ServiceItem model** next!

That will let us represent the actual lawn care services (fertilization, weed control, etc.) that you invoice for.
