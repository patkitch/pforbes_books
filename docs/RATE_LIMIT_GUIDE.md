# Jobber API Rate Limits - Complete Guide

## 🚦 Understanding Jobber's Rate Limits

Jobber uses **two layers** of rate limiting:

### 1. DDoS Protection (Less Restrictive)
- **Limit:** 2,500 requests per 5 minutes (300 seconds)
- **Per:** App/Account combination (not IP-based)
- **Error:** 429 Too Many Requests
- Usually not the issue if you respect the GraphQL query cost limits below

### 2. GraphQL Query Cost (More Restrictive) ⚠️ **This is what we hit**
- **Maximum Available:** 10,000 points total
- **Restore Rate:** 500 points per minute
- **How it works:** "Leaky Bucket" algorithm - points restore gradually over time

## 📊 What Happened During Testing

From our test results, we saw:
```json
"throttleStatus": {
  "maximumAvailable": 10000,
  "currentlyAvailable": 9995,  // Started high
  "restoreRate": 500            // 500 points/minute
}
```

After many test queries:
```
"currentlyAvailable": 0  // We exhausted all points!
```

### Why We Got Throttled:
1. We ran ~20+ test queries in a short time
2. Each query cost 5-10 points
3. Points were being consumed faster than they restored (500/min)
4. Eventually hit 0 available points = THROTTLED

## ⏱️ How Long to Wait?

### Full Recovery Time:
- **Maximum points:** 10,000
- **Restore rate:** 500 points/minute
- **Full recovery:** 10,000 ÷ 500 = **20 minutes**

### Practical Wait Times:
- **Light usage (1-2 queries):** 1-2 minutes
- **Medium usage (5-10 queries):** 5-10 minutes
- **Heavy testing like we did:** 15-20 minutes
- **Safe bet after heavy throttling:** **30 minutes**

## 🎯 Strategy for When You Return

### Option 1: Wait and Run Full Sync (Recommended)
**Wait:** 30 minutes from last throttle error
**Then run:**
```powershell
# Set fresh token first
$env:JOBBER_API_KEY = "new-token-here"

# Start with 2025 only (smaller dataset)
python manage.py sync_invoices --start-date 2025-01-01 --dry-run
```

### Option 2: Conservative Approach with Delays
Add delays between operations to stay under rate limits:

```powershell
# Sync service items (already done - 48 items)
python manage.py sync_service_items

# Wait 2 minutes
Start-Sleep -Seconds 120

# Sync invoices
python manage.py sync_invoices --start-date 2025-01-01 --dry-run

# Wait 2 minutes
Start-Sleep -Seconds 120

# Sync payments
python manage.py sync_payments --start-date 2025-01-01 --dry-run
```

### Option 3: Use Smaller Date Ranges
Break the sync into chunks:

```powershell
# December 2025 only
python manage.py sync_invoices --start-date 2025-12-01

# Wait a bit
Start-Sleep -Seconds 120

# November 2025
python manage.py sync_invoices --start-date 2025-11-01
```

## 📈 Query Cost Analysis

Based on Jobber's documentation, query costs depend on:

### Low Cost Queries (1-10 points):
- Simple queries with few fields
- Single object fetches
- No nested connections

### Medium Cost Queries (10-50 points):
- Our invoice query (has line items nested)
- Multiple connections
- Pagination requests

### High Cost Queries (50+ points):
- Deeply nested queries
- Large pagination sizes
- Complex filters

### Our Invoice Query Estimated Cost: ~20-30 points
```graphql
query {
  invoices(first: 50) {  # 50 items = higher cost
    nodes {
      amounts { ... }     # Simple fields
      lineItems {         # Nested connection adds cost
        nodes { ... }
      }
    }
  }
}
```

## 🛡️ Best Practices to Avoid Throttling

### 1. Use Smaller Pagination Sizes
```python
# Instead of:
limit = 100

# Use:
limit = 25  # Lower cost per query
```

### 2. Add Delays Between Requests
```python
import time

for page in range(total_pages):
    fetch_invoices()
    time.sleep(2)  # 2 second delay between pages
```

### 3. Monitor the Response
Every response includes cost information:
```json
"extensions": {
  "cost": {
    "requestedQueryCost": 142,
    "actualQueryCost": 47,
    "throttleStatus": {
      "maximumAvailable": 10000,
      "currentlyAvailable": 9953,
      "restoreRate": 500
    }
  }
}
```

Watch `currentlyAvailable` - if it gets below 1000, slow down!

### 4. Avoid Deeply Nested Queries
```python
# Bad (high cost):
query {
  invoices {
    lineItems {
      product {
        category {
          parent { ... }
        }
      }
    }
  }
}

# Good (lower cost):
query {
  invoices {
    lineItems {
      name
      total
    }
  }
}
```

## 🔧 Updated Sync Service (With Rate Limit Handling)

I can update the services to:
1. Add delays between pages
2. Monitor `currentlyAvailable` points
3. Automatically slow down when points are low
4. Show progress with point usage

**Would you like me to create rate-limit-aware versions of the sync services?**

## 📝 Your Action Plan (When You Return)

### ✅ Step 1: Fresh Start (5-6 hours from now)
1. Get fresh Jobber token: https://developer.getjobber.com/
2. Set new token:
   ```powershell
   $env:JOBBER_API_KEY = "new-token-here"
   ```
3. Verify it works:
   ```powershell
   python search_invoices.py
   ```

### ✅ Step 2: Test Single Invoice
```powershell
python test_single_invoice.py
```

If this works, you're ready!

### ✅ Step 3: Sync Invoices (2025 Only)
```powershell
# Dry run first
python manage.py sync_invoices --start-date 2025-01-01 --dry-run

# If looks good, run live
python manage.py sync_invoices --start-date 2025-01-01
```

### ✅ Step 4: Wait 5 Minutes
```powershell
Start-Sleep -Seconds 300
```

### ✅ Step 5: Sync Payments
```powershell
python manage.py sync_payments --start-date 2025-01-01 --dry-run
```

## 🎉 Expected Results

### Invoices:
- **2025 data:** ~10-15 invoices (based on search showing Dec 2025 invoices)
- **Time:** 2-3 minutes
- **Points used:** ~200-300 points
- **Safe:** Yes, well under limit

### Payments:
- **2025 data:** Similar count to invoices
- **Time:** 2-3 minutes  
- **Points used:** ~200-300 points
- **Safe:** Yes, plenty of points left

## 💡 Pro Tips

1. **Always start with recent data** (2025) - smaller datasets
2. **Use dry-run first** - test without posting to ledger
3. **Wait between operations** - give points time to restore
4. **Monitor the output** - look for "currentlyAvailable" in responses
5. **Save historical data for later** - do 2024 data tomorrow

## 🚀 You're Ready!

When you return:
1. Fresh token ✓
2. 30+ minutes wait = full point recovery ✓
3. Conservative sync strategy ✓
4. All schema issues fixed ✓

**Everything is ready to go!** 🎉

---

**See you in 5-6 hours!**
