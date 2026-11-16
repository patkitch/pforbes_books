# P. Forbes Art — manual-accounting core integration candidate
Date: 2026-11-15
Branch: `feature/accounting-foundation`
Deployment: **development branch only**. Production Django settings/routes and DigitalOcean app have not been intentionally changed.

## Scope assembled in this branch
- Existing chart of accounts, account hierarchy/edit/deactivate, transaction register and account ledger.
- Existing manual purchases, income receipts, split transactions (2–5 categories), draft/edit/post.
- Existing posted-only Profit & Loss and Balance Sheet, Excel/PDF downloads.
- Owner cash contributions and personal-funded business expenses, including draft/edit/post.
- Business-to-business bank transfers, business-bank payment of card liabilities, owner draws, purchase refunds, sales refunds.
- Personal-funds card payment: debit business-card liability and credit owner equity, never an additional expense.
- Advanced balanced manual journal for atypical adjustments, up to eight journal lines.
- Separate audit-preserving reversed journal entry for posted errors; original posted journal lines retained and double reversal blocked.
- Trial Balance and CSV download; only direct ledger balances are included (avoid doubling parent/child accounts).
- Optional posting-period closure setting `ACCOUNTING_LOCK_THROUGH_DATE` (a date or YYYY-MM-DD). Form validation and posting service enforce the cutoff. No user-facing lock administration yet.
- Account search in all manual accounting forms.
- Isolated `config.settings_accounting_ci` and `config.urls_accounting_ci` for test execution without requiring local test machine settings.
- Development-branch GitHub Actions workflow: `.github/workflows/accounting-core-tests.yml`.

## Financial accounting rules verified by tests when test runner passes
1. Purchase on business card: Dr expense/COGS, Cr card liability.
2. Business bank card payment: Dr card liability, Cr bank. Never a duplicate expense.
3. Personal funds pay business card: Dr card liability, Cr owner contribution equity. Never a duplicate expense.
4. Owner deposits personal funds: Dr bank, Cr owner equity. Not revenue.
5. Personal funds buy business supplies: Dr expense/COGS, Cr owner equity.
6. Bank-to-bank transfer: Dr receiving bank, Cr paying bank; P&L unchanged.
7. Owner draw: Dr owner equity, Cr bank; P&L unchanged.
8. Purchase refund: Dr receiving asset/card liability, Cr expense/COGS category.
9. Customer refund: Dr income category, Cr payment account.
10. Sale: Dr bank/cash, Cr income.
11. Reversal: post equal-and-opposite lines dated in an open period; preserve original, reason and audit event.
12. General journal: minimum two lines, equal positive debit and credit totals.

## Test and release gates — still required
- GitHub branch code has been committed, but **all newly added tests have not yet been confirmed to pass** in the user's Windows environment.
- Run consolidated accounting suite using the existing working local settings:
  `python manage.py test accounting --settings=config.settings_accounting_test`
- If a local test is discovered under `pforbes_books_accounting_test.accounting.*` rather than `accounting.*`, investigate local top-level `__init__.py`, nested copies, current working directory and test discovery; avoid replacing local config/migrations.
- Also run independent test settings from a clean branch checkout:
  `python manage.py test accounting --settings=config.settings_accounting_ci`
- Test from browser with synthetic 2027 data: one each of income, expense, split, owner contribution, owner-paid supplies, card payment, transfer, refund, owner draw, general journal and reversing error.
- Verify cash basis applies as entered (the app does not yet provide accrual-to-cash conversion).
- Balance P&L, Balance Sheet and Trial Balance after test entries; inspect exports.
- Make no production deployment or migrations until local review, backup and explicit release decision.

## Deliberately not included in manual posting core
- Bank and card transaction import inbox, matching/deduplication and transaction approval (next phase).
- External bank integrations, WooCommerce/Stripe imports, automatic gallery sale/commission matching, automatic sales-tax computations.
- Schedule C automatic mapping/deductibility: requires IRS/Kansas review before implementing.
- Customer/vendor persistent directories and contact deduplication; names may be recorded as payee manually, dedicated directories are future modules.
- User-facing period lock/unlock workflow, permissions beyond staff access, and financial reconciliation against full personal bank/card statements.
- Final dashboard/sidebar/form visual design and mobile usability work (lipstick phase).
- Historical year-close retained earnings transfer for post-2027 years.
- App-level protections against **direct ORM/database edits** to posted lines; current UI prevents edits and the posting service validates entries. More hardening required before production.

## Scope and safety
This is a synthetic-data **manual-accounting integration candidate**, not a certified bookkeeping or tax package. Reports summarize what was posted. The new ledger starts with zero balances in 2027 and does not import historic QuickBooks data. The original deployed site, inventory and automation applications remain out of scope.
