# Business Intelligence Dashboard

Enterprise business-intelligence and financial-analytics dashboard for **ERPNext / Frappe v15**.
One Frappe Page (`/app/business-dashboard`) with eleven sections, global filters, drill-down into
standard ERPNext lists / reports, role-based access and a configurable default landing page.
No new transaction tables: every number is read from standard ERPNext records.

Version 1.0.0 - tested on Frappe 15.108.0 / ERPNext 15.108.3 (MariaDB, Python 3.11).

## Sections

| Section | Contents |
|---|---|
| Executive Dashboard | 25 KPI cards (financial, sales, purchase, cash) with previous-period comparison, growth %, good/bad indicator; income vs expense, profit trend, sales vs purchases, cash flow, top customers |
| Sales Analytics | monthly / daily / year-wise trend, by customer / item / item group / territory / salesperson, target vs achievement, order & invoice status, pending delivery, returns |
| Purchase Analytics | monthly trend, by supplier / item group, PO / PR / PI status, pending POs, goods received not invoiced, returns, sales vs purchase |
| Accounting Analytics | P&L, Balance Sheet ratios, General Ledger activity, expense analysis (account, cost centre, department, direct vs indirect) |
| Financial Statements | full hierarchical P&L and Balance Sheet, plus *Verify against standard reports* |
| Receivables / Payables | outstanding, not due, overdue, ageing, top parties, collection trend / DSO, upcoming obligations |
| Cash Flow & Banking | opening/closing, inflow/outflow, monthly flow, account balances, bank reconciliation status, pending payments |
| Inventory Analytics | stock value/qty, warehouse split, high-value / fast / slow / non-moving items, negative / low / reorder alerts, ageing, valuation trend, in transit |
| GST Analytics | output / input / net, CGST / SGST / IGST, collected / paid / payable, monthly trend, tax-account summary |
| Business Insights | 11 alerts driven by configurable thresholds |

## How the numbers are produced (accuracy)

* **Profit & Loss and Balance Sheet** call ERPNext's own `financial_statements.get_data` /
  `get_period_list` - the engine behind the standard reports - so they respect the account tree,
  root / account type, groups, opening balances, closing vouchers, fiscal year, cost centres,
  accounting dimensions, cancellation and currency. The dashboard never sums GL Entries to build a statement.
* **Receivables / Payables** run the standard *Accounts Receivable / Payable* report engine (Payment Ledger),
  so allocations, credit notes, returns and advances are netted. Ageing: Due Date basis, 30/60/90/120, evaluated at the *To Date*
  (as in the standard report the 0-30 bucket also holds not-yet-due amounts; Not Due and Overdue are shown separately).
* **Cash flow** uses the GL as the single source of truth and nets per voucher, so Payment + Journal entries are never
  double counted and transfers between own accounts are not shown as inflow *and* outflow.
* **Stock** uses Stock Ledger Entry (`actual_qty`, `stock_value_difference`) like *Stock Balance*; ageing uses *Stock Ageing*.
* **GST** accounts come from *GST Settings > GST Accounts*; figures are GL based, so credit notes / returns are included.
* Sales / purchase figures are net of tax (`base_net_amount`), in company currency; returns carry their negative sign.

`Financial Statements > Verify against standard reports` (and `api.validation.get_reconciliation`) re-runs the standard reports
and independent ledger queries and shows every difference.

## Install

```bash
cd ~/frappe-bench
bench get-app /path/to/business_intelligence_dashboard      # or copy into apps/ and: ./env/bin/pip install -e apps/business_intelligence_dashboard
bench --site <site> install-app business_intelligence_dashboard
bench build --app business_intelligence_dashboard
bench --site <site> clear-cache && bench restart             # production: restart supervisor / systemd
```

`install-app` creates the role **BI Dashboard User**, the Workspace **Business Intelligence**, the page and the settings record.
Later upgrades: `bench --site <site> migrate` (idempotent). Take a backup first on any shared or production site.

## Access and roles

The page is open to: System Manager, Accounts Manager, Accounts User, Sales Manager, Purchase Manager, Stock Manager,
Auditor, BI Dashboard User. Inside the page every section additionally checks DocType read permission
(e.g. a Sales Manager sees Sales Analytics but Accounting shows a "no access" panel); the API enforces the same.
Companies and Customer / Supplier / Territory / Item Group / Warehouse / Cost Center / Sales Person / Department
**User Permissions** are applied to every query.

## Default landing page

Two supported Frappe v15 mechanisms work together (no Frappe / ERPNext file is modified):

1. **Apps screen entry** (`add_to_apps_screen` + `has_permission`): after login Frappe sends the user to
   `get_default_path()`. With ERPNext as the only desk app that is `/app/home`, which ignores the home page setting; with the
   dashboard registered as a second desk app it is `/app`. The entry is shown only to users who may open the page.
2. **`boot_session` hook** sets `frappe.boot.home_page` for users who hold a role listed in
   **BI Dashboard Settings > Roles landing on the dashboard**; `/app` then opens the dashboard.

Fresh installs seed the roles *BI Dashboard User, System Manager, Accounts Manager, Sales Manager, Purchase Manager,
Stock Manager, Auditor* (Administrator holds every role, so it lands there too). Edit the table to change who lands on the
dashboard; empty it to switch the redirect off. Everyone else keeps their normal home page and is never sent to a page they cannot
open. A one-time patch widens sites that were seeded with the old single-role default (it never overrides a customised list).
`get_website_user_home_page` provides the same fallback for the website `/` route.

If another app also redirects after login (for example a custom script sending `/app` to a different page), that app wins or
races with this one - remove its redirect.

## Configuration

*BI Dashboard Settings* (System Manager): cache duration, Top-N size, overdue / high-outstanding / margin / expense-spike /
sales-decline / pending-order / delayed-PO thresholds, inventory movement window, landing roles.

Caching: results are cached per user + filters for the configured minutes and are invalidated immediately when a Sales / Purchase
Invoice, Order, Receipt, Delivery Note, Payment / Journal / Stock Entry, Stock Reconciliation, Period Closing Voucher or Bank
Transaction is submitted or cancelled. *Refresh* bypasses the cache.

## Known limitations

* The first uncached load of the financial sections is dominated by ERPNext's own statement queries (about 15 s on 40k GL rows on
  the development MariaDB); later loads come from the cache.
* A single company is analysed at a time (statements cannot be consolidated across currencies).
* Department-wise expense needs *Department* to be an Accounting Dimension (GL Entry has no department otherwise) - the panel says so.
* Salesperson views need a Sales Team on the documents; target vs achievement needs Sales Person targets (Target Detail). Both show an explanatory empty state otherwise.
* Bank reconciliation status counts bank postings without a clearance date; if clearance dates are not recorded these numbers are large by design.
* Charts use the frappe-charts library bundled with Frappe (no external CDN).

## Tests

```bash
bench --site <site> run-tests --module business_intelligence_dashboard.business_intelligence_dashboard.tests.test_api --skip-test-records --skip-before-tests
```
The tests only read data and assert input validation and accounting identities (balance sheet balances, ledger balances,
cash roll-forward, equality with the standard P&L report).

## Layout

```
business_intelligence_dashboard/
  hooks.py, install.py, boot.py
  business_intelligence_dashboard/            # the Frappe module
    api/        dashboard sales purchase accounting receivables payables cash_flow inventory gst insights validation utils
    page/business_dashboard/    page json / js / css / py
    workspace/business_intelligence/
    doctype/    bi_dashboard_settings, bi_dashboard_home_role
    tests/
  public/js/bi_dashboard.bundle.js, public/js/bi/*.js   # front-end modules (esbuild bundle)
```
