# Payment Sync Service - Predicted Schema Updates

## Based on Invoice Schema Changes

Following the same pattern we discovered for invoices, here are the likely changes needed for the payment sync service:

## 🔄 Predicted Changes

### 1. Date Filter (HIGH CONFIDENCE)
```python
# CURRENT (WRONG):
query FetchPayments($startDate: ISO8601DateTime) {
  payments(filter: {receivedAfter: $startDate}) {
    ...
  }
}

variables = {"startDate": "2024-01-01"}

# PREDICTED (CORRECT):
query FetchPayments($receivedDateFilter: Iso8601DateTimeRangeInput) {
  payments(filter: {receivedDate: $receivedDateFilter}) {
    ...
  }
}

variables = {
    "receivedDateFilter": {
        "after": "2024-01-01T00:00:00Z"
    }
}
```

**Reasoning:** Same pattern as invoices - no more `receivedAfter`, use `receivedDate` with range input.

### 2. Payment Status (MEDIUM CONFIDENCE)
```python
# CURRENT (WRONG):
status {
  label
  value
}

# PREDICTED (CORRECT):
paymentStatus  # Enum like invoiceStatus
```

**Reasoning:** Invoices changed from `status { label, value }` to `invoiceStatus` enum.

### 3. Date Field Format (LOW CONFIDENCE - might not have changed)
```python
# CURRENT:
receivedOn

# MIGHT BE:
receivedDate  # Following invoice pattern (issuedAt → issuedDate)

# OR STILL:
receivedOn    # Payments might keep old naming
```

**Reasoning:** Invoices changed `issuedAt` → `issuedDate`, but payments might be different.

### 4. Amount Field (LOW CONFIDENCE - probably unchanged)
```python
# CURRENT:
amount

# LIKELY STAYS:
amount  # Payments are simpler than invoices, probably just a float

# UNLIKELY:
amounts { total }  # Would be overkill for payments
```

**Reasoning:** Payments are simpler than invoices. Unlikely to have complex amounts object.

## 📋 What We'll Discover When Rate Limit Resets

Run `python test_payments_schema.py` to find:

1. ✅ **Confirmed:** Exact field names (receivedOn vs receivedDate)
2. ✅ **Confirmed:** Status format (status object vs paymentStatus enum)
3. ✅ **Confirmed:** Filter attributes (receivedAfter vs receivedDate range)
4. ✅ **Confirmed:** Amount structure (simple float vs object)

## 🎯 Most Likely Changes Needed

### HIGH PRIORITY (99% will need to change):
```python
# Filter format
"filter": {
    "receivedDate": {  # Not receivedAfter
        "after": "2025-01-01T00:00:00Z"
    }
}
```

### MEDIUM PRIORITY (75% will need to change):
```python
# Status field
paymentStatus  # Instead of status { label, value }

# Check for "SUCCEEDED", "FAILED", "VOIDED" etc.
if payment["paymentStatus"] == "SUCCEEDED":
    ...
```

### LOW PRIORITY (25% might need to change):
```python
# Date field name
receivedDate  # Instead of receivedOn (maybe)
```

## 🔧 Updated Query (Predicted)

```graphql
query FetchPayments(
  $after: String, 
  $first: Int!, 
  $receivedDateFilter: Iso8601DateTimeRangeInput
) {
  payments(
    after: $after, 
    first: $first, 
    filter: {receivedDate: $receivedDateFilter}
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      amount
      receivedOn              # Or receivedDate
      paymentMethod
      referenceNumber
      notes
      client {
        id
        firstName
        lastName
        companyName
      }
      invoice {
        id
        invoiceNumber
      }
      paymentStatus          # Instead of status { label, value }
    }
  }
}
```

## 📊 Comparison Table

| Field | Current | Predicted | Confidence |
|-------|---------|-----------|------------|
| Filter param | `receivedAfter` | `receivedDate: {after: ...}` | 99% |
| Date variable | `$startDate: ISO8601DateTime` | `$receivedDateFilter: Iso8601DateTimeRangeInput` | 99% |
| Status | `status { label, value }` | `paymentStatus` (enum) | 75% |
| Date field | `receivedOn` | `receivedOn` or `receivedDate` | 50% |
| Amount | `amount` | `amount` (unchanged) | 90% |

## 🚀 Action Plan

### Step 1: When Rate Limit Resets (30 min)
```powershell
python test_payments_schema.py
```

### Step 2: Compare Results to Predictions
See which predictions were correct!

### Step 3: Update payment_sync_service.py
Based on actual schema discovered.

### Step 4: Test
```powershell
python manage.py sync_payments --start-date 2025-01-01 --dry-run
```

## 💡 Why This Analysis Helps

1. **We know what to look for** - Not surprised by errors
2. **Faster fixes** - Can update quickly when we see the schema
3. **Pattern recognition** - Understand Jobber's API evolution
4. **Confidence** - Know the invoice fixes apply to payments too

---

**Ready to test when rate limit resets!** ⏰
