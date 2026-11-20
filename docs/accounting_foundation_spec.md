# P. Forbes Art Accounting — Foundation specification (draft)
Date: 2026-11-14
Status: agreed workflow requirements; tax/implementation details noted as open.
Target first use: 2027-01-01.

## Boundaries
- Sole proprietorship P. Forbes Art only. Forbes Lawn remains in QuickBooks Online.
- New, independent Django accounting app within pforbes_books; do not restore Django Ledger.
- Keep art_inventory and website automation working unchanged. Inventory-to-ledger sync comes later.
- Start with zero opening *business* balances on 2027-01-01; do not import 2026 transactions or personal balances. Personal bank/card feeds will not reconcile to their full real-life balances under this policy.
- No payroll in v1. Keep production data separate from synthetic local test data.

## Accounts
- Use approved QuickBooks COA mapping as seed data, with familiar four-digit series: assets 1xxx, liabilities 2xxx, equity 3xxx, income 4xxx, COGS 5xxx, operating expenses 6xxx, other income 7xxx, other expenses 8xxx.
- Preserve account name, type, detail type, parent/child and numbering; allow active/inactive, renaming, and new accounts. Account identity must be a stable ID, not the editable account number.
- Inactive accounts remain in historical reports; prevent posting to inactive accounts. Allow search by name/number and collapsing account trees.
- Schedule C mapping is separate from COA and must be validated; tracking expenses for management does not itself establish tax deductibility.

## Import and review workflow
- Import bank/card activity into a staging inbox, without posting automatically.
- Statuses: Pending, Posted, Excluded; with safe Undo/reversal.
- Categorize from a COA dropdown; support split lines; suggest prior vendor codes but always permit correction (one vendor can use many accounts).
- Match imported lines to existing transactions with amount, date, account, and reference review; never match/post solely on amount.
- Excluded personal purchases and corresponding nonbusiness reimbursements stay in import history but do not touch the business ledger.
- Preserve source identifiers and prevent duplicate imports/postings; source edits/voids must maintain audit trail.

## Posting cases
- All posted journal entries must balance; use decimal money, atomic posting, reversible corrections, and period locks.
- Expenses charged on tracked credit cards raise a business card liability.
- When personally paid business card charges are confirmed paid, user manually records Owner Contribution to clear the paid business portion: Dr card liability / Cr owner equity. Do not recognize a second expense; do not automatically clear card balance. Continue to permit tracked business-account transfers if needed.
- Personal bank/card accounts may include mixed activity. A net business-only card liability is **not** the full external card balance; do not imply full personal-statement reconciliation.
- Stripe/WooCommerce payout split: gross sales and separately identified fees, taxes, shipping/refunds where applicable; match resulting net deposit and prevent double-counting order and payout imports.
- Images Art Gallery deposits: user enters a split allocating gross art sales and actual commission withheld (normally 30%, editable) to arrive at net bank deposit. Sales-tax obligations require verification by actual selling arrangement.
- Reimbursements for purchases made solely on behalf of the gallery: exclude the purchase and reimbursement from P. Forbes Art books.
- MPix purchases may be assigned to COGS by user. No automatic artwork production costing in v1; confirm any needed tax/inventory rules before implementing Schedule C mapping.
- Refund/credit should link to original transaction where feasible.

## Contacts and reports
- Vendors: names, suggested coding, spending summary, transaction list.
- Customer directory: WooCommerce source and manual customers; people and organizations; billing/shipping addresses, contact information, purchase history. Design in foundation; detailed customer/order integration later. Avoid duplicate customer imports.
- Launch reports: cash-basis P&L with Schedule C mapping and account drill-down; account transaction report with running balance, general ledger, trial balance, balance sheet; PDF and Excel/CSV exports and print view.
- Future reports: transaction list by vendor, monthly/quarterly comparison, expenses by vendor, customer sales/purchase history and repeat buyers, sales by product/variation, favorites.
- Report numbers must reflect ledger records and exclude staged/excluded imports.

## Build sequence
1. Verify working local checkout and independent test DB; inspect settings/routes and migrations.
2. Finalize COA seed and tax mapping; write transaction examples and expected journal lines.
3. Implement isolated accounting app models (Account, JournalEntry, JournalLine, AuditEvent) with balance controls and tests.
4. Build manual entry screens and reports; test against synthetic cases.
5. Only then add staged imports, matching and deduplication; later WooCommerce/customer imports.
6. Production deployment only after backup, migration review, local acceptance and explicit release choice.

## Open items before ledger coding
- Confirm official IRS/Kansas guidance for Schedule C treatment, COGS/inventory, sales tax and nondeductible gallery support; no automatic tax deductions based solely on COA category.
- Define business-only personal account display and reconciliation limitations.
- Agree rounding/split validation, refund/sales-tax test cases, and period lock/unlock permissions.
- Confirm local checkout and test DB access; verify live DigitalOcean deployment branch, migration method and fresh backup status separately (GitHub source cannot confirm deployed state).

## Repository inspection 2026-11-14
- Main SHA: 41cb11fd2787a9ff64b5faf7c0b9493f5205c64a (manual packaging supply tracking).
- Django 5.2.5; PostgreSQL configured, settings in config/settings.py, routes in config/urls.py.
- Installed apps: admin/auth/session/static, automation_logs, web_automation, art_inventory.
- Existing art inventory: Artwork, Original, PrintOption, PrintStock, InventoryActivity, StudioSupply; preserve untouched.
- No open pull requests found; feature/accounting-foundation was created from main.
- Deployment safety follow-up: inspect actual DigitalOcean environment; repository .do/app.yaml includes placeholder values and may not reflect live settings. Never commit credentials.
