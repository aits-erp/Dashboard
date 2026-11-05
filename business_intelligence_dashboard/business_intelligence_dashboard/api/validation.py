"""Reconciliation of the dashboard against ERPNext's standard reports.

``get_reconciliation`` re-runs the standard Profit and Loss Statement, Balance Sheet,
Accounts Receivable / Payable and Stock Balance reports (and independent ledger queries)
and compares them with what the dashboard reports.  Available to accounting roles so
finance can prove the figures at any time (Accounts > Business Intelligence).
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt

from business_intelligence_dashboard.business_intelligence_dashboard.api import accounting
from business_intelligence_dashboard.business_intelligence_dashboard.api.cash_flow import (
	balances_as_of,
	cash_bank_accounts,
	cash_flows,
	cash_position,
)
from business_intelligence_dashboard.business_intelligence_dashboard.api.inventory import stock_totals
from business_intelligence_dashboard.business_intelligence_dashboard.api.receivables import run_ageing_report
from business_intelligence_dashboard.business_intelligence_dashboard.api.sales import sales_totals
from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import cached, locked

TOLERANCE = 0.01


def _check(name, dashboard, standard, source):
	diff = round(flt(dashboard) - flt(standard), 2)
	return {
		"check": name,
		"dashboard": round(flt(dashboard), 2),
		"standard": round(flt(standard), 2),
		"difference": diff,
		"ok": abs(diff) <= TOLERANCE,
		"source": source,
	}


def _row_total(data, label):
	for r in data:
		if r and str(r.get("account", "")).strip("'") == label:
			return flt(r.get("total"))
	return 0.0


@frappe.whitelist()
@cached
def get_reconciliation(f):
	if not any(r in frappe.get_roles() for r in ("System Manager", "Accounts Manager", "Auditor", "Accounts User")):
		return locked(["GL Entry"], _("Reconciliation is available to accounting roles only."))
	checks = []

	# --- Profit and Loss vs the standard report
	from erpnext.accounts.report.profit_and_loss_statement import profit_and_loss_statement as pl_report

	pl = accounting.profit_and_loss(f, f.from_date, f.to_date)
	fil = accounting.fs_filters(f, f.from_date, f.to_date)
	data = pl_report.execute(fil)[1]
	checks += [
		_check("Total Income", pl.total_income, _row_total(data, "Total Income (Credit)"), "Profit and Loss Statement"),
		_check("Total Expense", pl.total_expense, _row_total(data, "Total Expense (Debit)"), "Profit and Loss Statement"),
		_check("Net Profit", pl.net_profit, _row_total(data, "Profit for the year"), "Profit and Loss Statement"),
	]

	# --- Balance Sheet vs the standard report
	from erpnext.accounts.report.balance_sheet import balance_sheet as bs_report

	bs = accounting.balance_sheet(f, f.to_date)
	fy_start = accounting._fiscal_year_for(f.to_date, f.company)[1]
	fil = accounting.fs_filters(f, fy_start, f.to_date, accumulated=1)
	fil.periodicity = "Yearly"
	data = bs_report.execute(fil)[1]
	std_assets = _row_total(data, "Total Asset (Debit)")
	std_liab = _row_total(data, "Total Liability (Credit)")
	std_equity = _row_total(data, "Total Equity (Credit)")
	std_provisional = _row_total(data, "Provisional Profit / Loss (Credit)")
	std_unclosed = _row_total(data, "Unclosed Fiscal Years Profit / Loss (Credit)")
	checks += [
		_check("Total Assets", bs.total_assets, std_assets, "Balance Sheet"),
		_check(
			"Liabilities + Equity (incl. provisional P&L) = Assets",
			bs.total_liabilities + bs.equity,
			std_liab + std_equity + std_provisional + std_unclosed,
			"Balance Sheet",
		),
		_check("Balance sheet balances (Assets - Liabilities - Equity)", bs.total_assets - bs.total_liabilities - bs.equity, 0, "Accounting equation"),
	]

	# --- Receivables / payables vs the Payment Ledger
	# Payment Ledger amounts are positive for invoices on both sides (debit-positive for
	# receivables, credit-positive for payables), so no sign flip is needed.
	for party_type, account_type, sign in (("Customer", "Receivable", 1), ("Supplier", "Payable", 1)):
		rows = run_ageing_report(f, party_type)
		report_total = sum(flt(r.get("outstanding")) for r in rows)
		ledger = frappe.db.sql(
			"""select ifnull(sum(amount), 0) from `tabPayment Ledger Entry`
			where delinked = 0 and company = %s and account_type = %s and posting_date <= %s and party_type = %s""",
			(f.company, account_type, f.to_date, party_type),
		)[0][0]
		checks.append(
			_check(
				f"Outstanding {'Receivables' if party_type == 'Customer' else 'Payables'}",
				report_total,
				sign * flt(ledger),
				"Payment Ledger (independent query)",
			)
		)

	# --- cash & bank vs ERPNext's get_balance_on
	from erpnext.accounts.utils import get_balance_on

	accounts = cash_bank_accounts(f.company)
	cash, bank = cash_position(f, f.to_date)
	std = sum(flt(get_balance_on(account=a.name, date=f.to_date, company=f.company)) for a in accounts)
	checks.append(_check("Cash + Bank balance", cash + bank, std, "erpnext.accounts.utils.get_balance_on"))
	opening = sum(cash_position(f, add_days(f.from_date, -1)))
	inflow, outflow, _m = cash_flows(f, f.from_date, f.to_date)
	checks.append(_check("Opening + Inflow - Outflow = Closing", opening + inflow - outflow, cash + bank, "Cash flow identity"))

	# --- stock vs the standard Stock Balance report and Bin
	from erpnext.stock.report.stock_balance.stock_balance import execute as stock_balance

	value, qty = stock_totals(f, f.to_date)
	data = stock_balance(frappe._dict(company=f.company, from_date=f.from_date, to_date=f.to_date))[1]
	checks.append(_check("Stock value", value, sum(flt(r.get("bal_val")) for r in data), "Stock Balance report"))
	checks.append(_check("Stock quantity", qty, sum(flt(r.get("bal_qty")) for r in data), "Stock Balance report"))
	bin_value = frappe.db.sql(
		"""select ifnull(sum(b.stock_value),0) from `tabBin` b join `tabWarehouse` w on w.name = b.warehouse where w.company = %s""",
		f.company,
	)[0][0]
	bin_check = _check("Stock value vs Bin (current, informational)", stock_totals(f, f.today)[0], bin_value, "Bin (cached valuation)")
	# Bin is a cache that can drift from the ledger on old data; the ledger is authoritative.
	bin_check["informational"] = True
	checks.append(bin_check)

	# --- ledger integrity and sales
	gl = frappe.db.sql(
		"""select ifnull(sum(debit),0), ifnull(sum(credit),0) from `tabGL Entry`
		where company = %s and is_cancelled = 0 and posting_date between %s and %s""",
		(f.company, f.from_date, f.to_date),
	)[0]
	checks.append(_check("GL debit = credit", gl[0], gl[1], "General Ledger"))
	if f.customers is None and f.territories is None and f.item_groups is None and f.warehouses is None and f.cost_centers is None:
		header = frappe.db.sql(
			"""select ifnull(sum(base_net_total),0) from `tabSales Invoice`
			where docstatus = 1 and company = %s and posting_date between %s and %s""",
			(f.company, f.from_date, f.to_date),
		)[0][0]
		checks.append(_check("Net sales (items) = Sales Invoice base_net_total", sales_totals(f).net_sales, header, "Sales Invoice headers"))

	return {"checks": checks, "all_ok": all(c["ok"] for c in checks if not c.get("informational"))}
