# Ledger Posting Service - Testing Guide

## 🎯 What We Just Built

The **LedgerPostingService** - the core logic that posts Forbes Lawn transactions to Django Ledger!

### Files Created:
```
forbes_lawn_accounting/
├── services/
│   ├── __init__.py
│   └── ledger_posting.py          ← The posting service (main logic)
└── management/
    └── commands/
        └── test_posting.py         ← Test command
```

---

## 🧠 How It Works

### Invoice Posting Logic:
```
When you post an invoice:

1. Creates a NEW Ledger for that invoice
   Name: "Invoice: {invoice_number}"

2. Creates a Journal Entry in that ledger

3. Creates transactions:
   DR 1010 Accounts Receivable        [total]
   CR 4024 Service Income-Taxable     [taxable services]
   CR 4025 Service Income-NonTaxable  [non-taxable services]
   CR 2024 Sales Tax to Pay           [tax amount]

4. Marks invoice as posted
```

### Payment Posting Logic:
```
When you post a payment:

1. Creates a NEW Ledger for that payment
   Name: "Payment: Invoice {invoice_number}"

2. Creates a Journal Entry in that ledger

3. Creates transactions:
   DR 1024 Payments to Deposit  [amount]
   CR 1010 Accounts Receivable  [amount]

4. Marks payment as posted
5. Updates invoice totals
```

---

## 🧪 How to Test

### Step 1: Make sure .env has entity slug
```bash
# In your .env file:
FORBES_LAWN_ENTITY_SLUG=forbes-lawn-spraying-llc-dev-d6qyx55c
```

### Step 2: Run the test command
```bash
python manage.py test_posting
```

### What the test does:
1. ✅ Finds your entity
2. ✅ Initializes posting service with your COA
3. ✅ Creates a test customer
4. ✅ Creates a test service item
5. ✅ Creates a test invoice with 2 line items:
   - Line 1: $85.00 (fertilization - front lawn)
   - Line 2: $65.00 (fertilization - back lawn)
   - Subtotal: $150.00
   - Tax (8.65%): $12.98
   - Total: $162.98
6. ✅ Posts invoice to ledger
7. ✅ Shows all journal entry transactions
8. ✅ Verifies debits = credits
9. ✅ Creates a test payment ($100.00)
10. ✅ Posts payment to ledger
11. ✅ Shows updated invoice balance

---

## ✅ Expected Output

You should see something like:

```
✓ Found entity: Forbes Lawn Spraying LLC-DEV
✓ Posting service initialized with COA: FLS DEV COA DEFAULT
✓ Created test customer: Test Customer
✓ Created test service: Test Fertilization Service

============================================================
Creating test invoice...
============================================================
✓ Created invoice: TEST-20241229-153045
✓ Added 2 line items

Invoice Totals:
  Subtotal:        $150.00
  Taxable:         $150.00
  Tax (8.65%):     $12.98
  Total:           $162.98

============================================================
Posting invoice to ledger...
============================================================
✓ Posted to ledger!
  Ledger: Invoice: TEST-20241229-153045
  Journal Entry: Invoice TEST-20241229-153045 - Test Customer

  Transactions:
    DR 1010 Accounts Receivable                       $    162.98
    CR 4024 Service Income - Taxable                  $    150.00
    CR 2024 Sales Tax to Pay                          $     12.98

============================================================
Verifying posting...
============================================================
✓ All verifications passed!
  Debits:  $162.98
  Credits: $162.98
  Balance: ✓

============================================================
Creating and posting test payment...
============================================================
✓ Created payment: $100.00
✓ Posted payment to ledger!
  Ledger: Payment: Invoice TEST-20241229-153045

  Transactions:
    DR 1024 Payments to Deposit                       $    100.00
    CR 1010 Accounts Receivable                       $    100.00

  Updated Invoice Status:
    Total:        $162.98
    Amount Paid:  $100.00
    Balance Due:  $62.98
    Status:       Partially Paid

============================================================
✓ ALL TESTS PASSED!
============================================================

Test invoice created: TEST-20241229-153045
View in admin: /admin/forbes_lawn_accounting/invoice/1/change/
```

---

## 🔍 Verify in Django Admin

After running the test:

1. **Go to Django Admin** → Forbes Lawn Accounting → Invoices
2. **Find the test invoice** (starts with "TEST-")
3. **Click to view details:**
   - Should show 2 line items
   - Should show 1 payment
   - Should show "Posted to Ledger: Yes"
   - Should show journal entry link

4. **Click the journal entry link:**
   - Should see the ledger name: "Invoice: TEST-..."
   - Should see all DR/CR transactions
   - Debits should equal credits

5. **Go to Django Ledger** → Ledgers
   - Should see 2 new ledgers:
     - "Invoice: TEST-..." (with invoice posting)
     - "Payment: Invoice TEST-..." (with payment posting)

---

## 🧹 Clean Up Test Data

After verifying everything works, delete the test data:

1. Django Admin → Forbes Lawn Accounting → Invoices
2. Find test invoice (TEST-...)
3. Delete it (will cascade delete lines, payments, journal entries, ledgers)

Or keep it to study the structure!

---

## ❌ Troubleshooting

### Error: "Account code 'XXXX' not found"
**Solution:** Make sure you've created ALL GL codes in your COA. Check the critical ones:
- 1010: Accounts Receivable
- 1024: Payments to Deposit
- 4024: Service Income - Taxable
- 4025: Service Income - Non-Taxable
- 2024: Sales Tax to Pay

### Error: "Entity not found"
**Solution:** Check your .env file has the correct entity slug:
```bash
FORBES_LAWN_ENTITY_SLUG=forbes-lawn-spraying-llc-dev-d6qyx55c
```

### Error: "Entity does not have a Chart of Accounts"
**Solution:** Make sure your entity has a COA assigned in Django Ledger admin.

---

## 🎯 What This Proves

If the test passes, you've proven:

✅ Ledger posting service works
✅ Can create invoices programmatically
✅ Can post invoices to ledger
✅ Journal entries are created correctly
✅ Debits = Credits (balanced)
✅ Can post payments
✅ Invoice totals update correctly
✅ Each transaction gets its own ledger (not shared!)

**You're ready for Phase 1 completion!** 🎉

Next step: Build the Jobber sync service to pull real data from Jobber API!

---

## 💡 Using the Service in Your Code

After this test works, you can use the service like this:

```python
from django_ledger.models.entity import EntityModel
from forbes_lawn_accounting.models import Invoice
from forbes_lawn_accounting.services.ledger_posting import LedgerPostingService
import os

# Get entity
entity_slug = os.getenv('FORBES_LAWN_ENTITY_SLUG')
entity = EntityModel.objects.get(slug=entity_slug)

# Initialize service
poster = LedgerPostingService(entity)

# Post an invoice
invoice = Invoice.objects.get(invoice_number='492')
je = poster.post_invoice_to_ledger(invoice)

# Post a payment
payment = invoice.payments.first()
je_payment = poster.post_payment_to_ledger(payment)

# Verify
results = poster.verify_posting(invoice)
print(results)
```

---

Ready to test? Run: `python manage.py test_posting` 🚀
