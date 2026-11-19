# Contacts and Receipts Integration — 2027 Test Program

Development branch: `feature/accounting-foundation`
Status: integrated development candidate, **no DigitalOcean deployment**.

## Three linked modules

**Vendors** store name, email, phone, website, mailing address, notes, active status, and a suggested account number. Suggested coding does not automatically post a journal entry. Vendor detail displays linked posted accounting activity net of refunds and the vendor's receipts.

**Customers** store name, individual/organization, email, phone, billing and shipping addresses, notes, active status, and (when present) a unique registered WooCommerce customer ID. Customer detail displays linked posted income net of refunds and receipts.

**Receipts** store description/title, type (purchase, sale, refund, other), date, amount, source/reference, optional vendor/customer, optional numeric journal entry identifier, and optional uploaded PDF/JPG/PNG/WebP (10 MB maximum, signature checked). Uploaded documents download only through an authenticated staff-only route. **A receipt does not itself post a journal entry.** Add a receipt either from the Receipts directory or by choosing Attach Receipt on a transaction. Assigning a receipt to a journal with a vendor/customer automatically connects the contact to that journal if no conflicting association exists.

## Transaction contacts

The simple income/expense, split income/expense, and refund forms support optional contact selection during manual entry. Vendor selection is valid for purchases and purchase refunds; customer selection is valid for sales and sales refunds. A transaction also has a Link Vendor/Customer action in the register, with an audit event; this does not alter posted debit/credit amounts. Existing historical payee text is not automatically treated as an authoritative identity.

Contact associations are stored in the **new independent app** `accounting_contacts`, using `journal_entry_id` numeric references and service-level existence validation. This deliberately avoids fragile migration dependencies on `accounting`, whose original migration was generated only in the user's local test environment. A future production hardening phase should consider database-level referential integrity after migrations are consolidated.

## WooCommerce readiness (not an active integration)

`accounting_contacts/woo_receipts.py` has a tested function `stage_woo_order_receipt(order)`. It accepts a supplied WooCommerce order dictionary, matches registered customers using nonzero WooCommerce customer ID, or creates a separate guest customer for each unique order; it creates an idempotent order sales-receipt record. The same order ID does not create duplicate customers/receipts. **This function does not call WooCommerce, import orders on its own, or make a journal entry.** The approved inbox, deduplication, sales-tax/fees mapping, and posting logic remain in the later import phase.

## Local test installation

The branch includes `scripts/install_accounting_test.ps1` to run from an extracted ZIP. The installer:
1. Checks prerequisites and backs up the existing accounting code, local test settings, plus accounting-data JSON.
2. Copies accounting source while retaining local accounting migrations, installs `accounting_contacts` including its independent `0001_initial.py`.
3. Appends only the local test app setting if needed, checks migrations, applies the new contacts migration and runs `accounting` and `accounting_contacts` automated tests.
4. Does not modify the production settings, `main`, DigitalOcean deployments, or inventory app.

Receipt attachment binaries persist in the separate local media directory, not in the accounting source folder. Real file privacy requires verified private storage configuration before a future production release.

## Acceptance scenarios

- Manually create a vendor and customer; verify search and editing.
- Link a posted transaction to the vendor; confirm spending history and no change to journal amounts.
- Record an artwork sale with a selected customer; confirm the customer shows the sale.
- Add PDF receipt attached to an existing transaction; confirm staff-only access and auto-association.
- Verify duplicate Woo registered customer and order IDs do not create duplicate records.
- Check P&L, Balance Sheet and Trial Balance have exactly the same figures as before adding contact/receipt modules.

## Explicit future work

- Actual WooCommerce/Stripe transaction inbox, source matching, taxes/fees/shipping, and net deposits.
- Bank and credit-card statement imports and receipt matching/approval.
- Owner identity/subaccounts, additional vendor and customer reporting, contact merging reviewed by users.
- Dashboard/sidebar/form redesign including Add Line controls.
- Production-ready role permissions, retention/encryption/privacy strategy for receipt documents, stronger database referential constraints.

This development candidate is not a tax-deductibility engine and must remain local until a separately approved production release.

## Consolidated improvement update (November 2026)

This branch now also includes the following improvements, **not yet installed on the user's local machine**:

1. Reversing a posted transaction automatically carries its linked vendor or customer to the reversal, preserving contact spending/revenue totals without manual linking. This also works when the original contact has since been marked inactive.
2. Optional itemized artwork rows on sales receipts: artwork title, original/print/other, size, quantity, and unit price. The customer detail page shows the items beneath its receipt. Receipt amounts and posted accounting balances remain unchanged.
3. Receipt links and protected document-download links are visible directly in the accounting transaction register.
4. Exact duplicate manual receipts (same name, type, date, amount and contact) are rejected; genuine PDF/JPEG/PNG/WebP signatures are checked.
5. The installer only registers the contacts app in `config.settings` when the local test settings inherit that file, preventing duplicate application labels. The installer migrates the local PostgreSQL database and runs the 121-test suite against the isolated test settings. The installer is ASCII-only, and GitHub CI checks its PowerShell parser syntax and encoding to prevent repeat PowerShell 5.1 errors.

The new migration `accounting_contacts/migrations/0002_receiptitem.py` **creates a new table**. It does not rewrite the existing `accounting` or `accounting_contacts` records. The revised installation script backs up accounting and contact data before applying migrations.

Before local installation, stop the :8003 Django server, refresh the extracted development-branch ZIP into `C:\accounting _download\pforbes_books-feature-accounting-foundation`, then run `scripts/install_accounting_test.ps1` **once**. Check for the successful migrations and test suite output before restarting. Never copy the extracted repository into the local app manually or run the script against DigitalOcean.
