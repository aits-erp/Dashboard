"""Accounting analytics and financial statements.

Profit & Loss and Balance Sheet figures are produced with ERPNext's own
``erpnext.accounts.report.financial_statements`` engine (``get_period_list`` /
``get_data``) - the same code the standard *Profit and Loss Statement* and
*Balance Sheet* reports run.  That engine walks the account tree, honours root /
account type, group accounts, opening balances, closing vouchers, fiscal years,
finance books, cost centres, accounting dimensions, cancellation status and
presentation currency.  Nothing here sums GL Entries to build a statement; the
only direct GL queries are for ledger *activity* (debit / credit totals,
cost-centre split) which are not statement lines.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	_fiscal_year_for,
	cached,
	gl_conditions,
	growth,
	list_route,
	locked,
	months_between,
	month_label,
	ratio_pct,
	report_route,
	request_memo,
	require_permission,
	series_by_month,
	top_n,
)

DIRECT_ACCOUNT_TYPES = ("Cost of Goods Sold", "Direct Expense", "Stock Adjustment", "Expenses Included In Valuation")
FIXED_ACCOUNT_TYPES = ("Fixed Asset", "Accumulated Depreciation", "Capital Work in Progress")
NON_CURRENT_ASSET = re.compile(r"fixed|non[\s_-]*current|investment|capital work|intangible", re.I)
EQUITY_LIABILITY = re.compile(r"equity|capital|reserve|surplus|retained|shareholder", re.I)
NON_CURRENT_LIABILITY = re.compile(r"non[\s_-]*current|long[\s_-]*term|loan|secured|debenture|borrowing", re.I)


# ------------------------------------------------------------- ERPNext engine


def _memo(key, fn):
	store = request_memo()
	if key not in store:
		store[key] = fn()
	return store[key]


def fs_filters(f, start, end, accumulated=0):
	"""Filters object understood by ERPNext's financial statement engine."""
	fy = _fiscal_year_for(start, f.company)[0]
	return frappe._dict(
		company=f.company,
		from_fiscal_year=fy,
		to_fiscal_year=fy,
		period_start_date=getdate(start),
		period_end_date=getdate(end),
		filter_based_on="Date Range",
		periodicity="Monthly",
		accumulated_values=accumulated,
		presentation_currency=None,
		finance_book=None,
		include_default_book_entries=1,
		project=None,
		show_zero_values=0,
		cost_center=list(f.cost_centers) if f.cost_centers is not None else None,
	)


def _row_values(row, period_list):
	return [flt(row.get(p.key)) for p in period_list]


def _account_label(row):
	return row.get("account_name") or row.get("account")


def _is_direct(row, by_name):
	if row.get("account_type") in DIRECT_ACCOUNT_TYPES:
		return True
	seen, cur = set(), row
	while cur and cur.get("account") not in seen:
		seen.add(cur.get("account"))
		if re.search(r"\bdirect\b", str(_account_label(cur)), re.I):
			return True
		cur = by_name.get(cur.get("parent_account"))
	return False


def profit_and_loss(f, start, end):
	"""Profit & Loss for [start, end] via ERPNext's engine, with monthly buckets."""
	key = ("pnl", f.company, str(start), str(end), tuple(f.cost_centers or ()) if f.cost_centers is not None else None)
	return _memo(key, lambda: _profit_and_loss(f, start, end))


def _profit_and_loss(f, start, end):
	from erpnext.accounts.report.financial_statements import get_data, get_period_list

	fil = fs_filters(f, start, end)
	period_list = get_period_list(
		fil.from_fiscal_year, fil.to_fiscal_year, start, end, "Date Range", "Monthly", company=f.company
	)
	income = get_data(
		f.company, "Income", "Credit", period_list, filters=fil, accumulated_values=0, ignore_closing_entries=True, total=False
	) or []
	expense = get_data(
		f.company, "Expense", "Debit", period_list, filters=fil, accumulated_values=0, ignore_closing_entries=True, total=False
	) or []

	n = len(period_list)
	zero = [0.0] * n

	def root_sum(rows):
		out = list(zero)
		for r in rows:
			if not r.get("parent_account"):
				for i, v in enumerate(_row_values(r, period_list)):
					out[i] += v
		return out

	by_name = {r["account"]: r for r in income + expense}
	direct = list(zero)
	for r in expense:
		if not r.get("is_group") and _is_direct(r, by_name):
			for i, v in enumerate(_row_values(r, period_list)):
				direct[i] += v

	income_m, expense_m = root_sum(income), root_sum(expense)
	gross_m = [a - b for a, b in zip(income_m, direct)]
	net_m = [a - b for a, b in zip(income_m, expense_m)]
	total_income, total_expense, total_direct = sum(income_m), sum(expense_m), sum(direct)

	leaves = []
	for r in expense:
		if not r.get("is_group") and abs(flt(r.get("total"))) > 0:
			leaves.append({"account": r["account"], "label": _account_label(r), "amount": flt(r["total"]), "direct": _is_direct(r, by_name)})
	income_leaves = [
		{"account": r["account"], "label": _account_label(r), "amount": flt(r["total"])}
		for r in income
		if not r.get("is_group") and abs(flt(r.get("total"))) > 0
	]

	return frappe._dict(
		period_list=period_list,
		income_rows=income,
		expense_rows=expense,
		months=[p.key for p in period_list],
		labels=[p.label for p in period_list],
		total_income=total_income,
		total_expense=total_expense,
		direct_expense=total_direct,
		indirect_expense=total_expense - total_direct,
		gross_profit=total_income - total_direct,
		net_profit=total_income - total_expense,
		gp_margin=ratio_pct(total_income - total_direct, total_income),
		np_margin=ratio_pct(total_income - total_expense, total_income),
		income_m=income_m,
		expense_m=expense_m,
		direct_m=direct,
		gross_m=gross_m,
		net_m=net_m,
		expense_leaves=sorted(leaves, key=lambda x: -abs(x["amount"])),
		income_leaves=sorted(income_leaves, key=lambda x: -abs(x["amount"])),
	)


def _classify_asset(row, by_name):
	if row.get("account_type") in FIXED_ACCOUNT_TYPES:
		return "fixed"
	cur = row
	while cur:
		if cur.get("parent_account") and not by_name.get(cur["parent_account"], {}).get("parent_account"):
			# cur is a child of the root: its name classifies the branch
			return "fixed" if NON_CURRENT_ASSET.search(str(_account_label(cur))) and not re.search(r"current assets$", str(_account_label(cur)).strip(), re.I) or re.search(r"non[\s_-]*current", str(_account_label(cur)), re.I) else "current"
		if not cur.get("parent_account"):
			break
		cur = by_name.get(cur["parent_account"])
	return "current"


def _classify_liability(row, by_name):
	cur = row
	while cur:
		parent = cur.get("parent_account")
		if parent and not by_name.get(parent, {}).get("parent_account"):
			label = str(_account_label(cur))
			if EQUITY_LIABILITY.search(label):
				return "equity"
			if NON_CURRENT_LIABILITY.search(label):
				return "long_term"
			return "current"
		if not parent:
			break
		cur = by_name.get(parent)
	return "current"


def balance_sheet(f, asof):
	key = ("bs", f.company, str(asof), tuple(f.cost_centers or ()) if f.cost_centers is not None else None)
	return _memo(key, lambda: _balance_sheet(f, asof))


def _balance_sheet(f, asof):
	from erpnext.accounts.report.financial_statements import get_data, get_period_list

	asof = getdate(asof)
	fy, fy_start, fy_end = _fiscal_year_for(asof, f.company)
	fil = fs_filters(f, fy_start, asof, accumulated=1)
	fil.periodicity = "Yearly"
	period_list = get_period_list(fy, fy, fy_start, asof, "Date Range", "Yearly", company=f.company)
	kw = dict(filters=fil, accumulated_values=1, only_current_fiscal_year=False, total=False)
	assets = get_data(f.company, "Asset", "Debit", period_list, **kw) or []
	liabilities = get_data(f.company, "Liability", "Credit", period_list, **kw) or []
	equity_root = get_data(f.company, "Equity", "Credit", period_list, **kw) or []
	key = period_list[-1].key

	def leaf_val(r):
		return flt(r.get(key))

	by_name = {r["account"]: r for r in assets + liabilities + equity_root}
	cur_assets = fixed_assets = stock = 0.0
	for r in assets:
		if r.get("is_group"):
			continue
		kind = _classify_asset(r, by_name)
		if kind == "fixed":
			fixed_assets += leaf_val(r)
		else:
			cur_assets += leaf_val(r)
			if r.get("account_type") == "Stock":
				stock += leaf_val(r)
		r["bid_class"] = kind
	cur_liab = long_liab = equity_accounts = 0.0
	for r in liabilities:
		if r.get("is_group"):
			continue
		kind = _classify_liability(r, by_name)
		r["bid_class"] = kind
		if kind == "equity":
			equity_accounts += leaf_val(r)
		elif kind == "long_term":
			long_liab += leaf_val(r)
		else:
			cur_liab += leaf_val(r)
	for r in equity_root:
		if not r.get("is_group"):
			equity_accounts += leaf_val(r)
			r["bid_class"] = "equity"

	root_total = lambda rows: sum(leaf_val(r) for r in rows if not r.get("parent_account"))  # noqa: E731
	total_assets = root_total(assets)
	root_liab_total = root_total(liabilities)
	root_equity_total = root_total(equity_root)
	total_liabilities = cur_liab + long_liab
	equity = total_assets - total_liabilities  # accounts + unclosed / provisional profit
	return frappe._dict(
		asof=asof,
		key=key,
		assets=assets,
		liabilities=liabilities,
		equity_rows=equity_root,
		total_assets=total_assets,
		current_assets=cur_assets,
		fixed_assets=fixed_assets,
		stock_assets=stock,
		current_liabilities=cur_liab,
		long_term_liabilities=long_liab,
		total_liabilities=total_liabilities,
		equity_accounts=equity_accounts,
		equity=equity,
		retained=equity - equity_accounts,
		provisional=total_assets - root_liab_total - root_equity_total,
		working_capital=cur_assets - cur_liab,
		current_ratio=round(cur_assets / cur_liab, 2) if cur_liab else None,
		quick_ratio=round((cur_assets - stock) / cur_liab, 2) if cur_liab else None,
		debt_to_equity=round(total_liabilities / equity, 2) if equity > 0 else None,
	)


# -------------------------------------------------------------- GL activity


def _gl_activity(f):
	cond, params = gl_conditions(f)
	totals = frappe.db.sql(
		f"select ifnull(sum(gle.debit),0) as debit, ifnull(sum(gle.credit),0) as credit, count(*) as entries "
		f"from `tabGL Entry` gle where {cond}",
		params,
		as_dict=True,
	)[0]
	monthly = frappe.db.sql(
		f"select date_format(gle.posting_date, '%%Y-%%m') as month, sum(gle.debit) as debit, "
		f"sum(gle.credit) as credit, count(*) as entries from `tabGL Entry` gle where {cond} group by 1 order by 1",
		params,
		as_dict=True,
	)
	cond_to, params_to = gl_conditions(f, with_dates=False)
	params_to["to_date"] = f.to_date
	balances = frappe.db.sql(
		f"""select gle.account, acc.root_type, acc.account_type, sum(gle.debit - gle.credit) as balance
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where {cond_to} and gle.posting_date <= %(to_date)s and acc.is_group = 0
		group by gle.account, acc.root_type, acc.account_type
		having abs(sum(gle.debit - gle.credit)) > 0.005
		order by abs(sum(gle.debit - gle.credit)) desc limit %(limit)s""",
		{**params_to, "limit": top_n() * 2},
		as_dict=True,
	)
	months = months_between(f.from_date, f.to_date)
	by_month = {r["month"]: r for r in monthly}
	return {
		"total_debit": flt(totals.debit),
		"total_credit": flt(totals.credit),
		"entries": cint(totals.entries),
		"difference": round(flt(totals.debit) - flt(totals.credit), 2),
		"trend": {
			"labels": [month_label(m) for m in months],
			"debit": [round(flt(by_month.get(m, {}).get("debit")), 2) for m in months],
			"credit": [round(flt(by_month.get(m, {}).get("credit")), 2) for m in months],
			"entries": [cint(by_month.get(m, {}).get("entries")) for m in months],
		},
		"account_balances": [
			{"account": r.account, "root_type": r.root_type, "account_type": r.account_type, "balance": flt(r.balance)}
			for r in balances
		],
	}


def _expense_by_cost_center(f):
	cond, params = gl_conditions(f)
	return frappe.db.sql(
		f"""select ifnull(gle.cost_center, 'Not set') as cost_center, sum(gle.debit - gle.credit) as amount
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where {cond} and acc.root_type = 'Expense' and gle.voucher_type != 'Period Closing Voucher'
		group by 1 having abs(sum(gle.debit - gle.credit)) > 0.005 order by 2 desc limit %(limit)s""",
		{**params, "limit": top_n() + 5},
		as_dict=True,
	)


def _expense_by_department(f):
	if not frappe.db.has_column("GL Entry", "department"):
		return None
	cond, params = gl_conditions(f)
	return frappe.db.sql(
		f"""select ifnull(nullif(gle.department, ''), 'Not set') as department, sum(gle.debit - gle.credit) as amount
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where {cond} and acc.root_type = 'Expense' and gle.voucher_type != 'Period Closing Voucher'
		group by 1 having abs(sum(gle.debit - gle.credit)) > 0.005 order by 2 desc limit %(limit)s""",
		{**params, "limit": top_n() + 5},
		as_dict=True,
	)


# ------------------------------------------------------------------- payload


def pnl_payload(f):
	cur = profit_and_loss(f, f.from_date, f.to_date)
	prev = profit_and_loss(f, f.prev_from, f.prev_to)
	metrics = {}
	for key in (
		"total_income",
		"direct_expense",
		"gross_profit",
		"indirect_expense",
		"total_expense",
		"net_profit",
		"gp_margin",
		"np_margin",
	):
		metrics[key] = {"value": round(cur[key], 2), "previous": round(prev[key], 2), "growth": growth(cur[key], prev[key])}
	return {
		"metrics": metrics,
		"monthly": {
			"labels": cur.labels,
			"income": [round(v, 2) for v in cur.income_m],
			"expense": [round(v, 2) for v in cur.expense_m],
			"gross_profit": [round(v, 2) for v in cur.gross_m],
			"net_profit": [round(v, 2) for v in cur.net_m],
		},
		"top_income_accounts": [
			{"account": r["account"], "label": r["label"], "amount": round(r["amount"], 2)} for r in cur.income_leaves[: top_n()]
		],
		"route": report_route("Profit and Loss Statement", _report_filters(f)),
	}


def _report_filters(f):
	# Order matters: the report applies route options one by one and refreshes, so the dates must
	# be in place before filter_based_on flips to "Date Range" (else it validates empty dates).
	return {
		"company": f.company,
		"period_start_date": str(f.from_date),
		"period_end_date": str(f.to_date),
		"periodicity": "Monthly",
		"from_fiscal_year": f.fiscal_year,
		"to_fiscal_year": f.fiscal_year,
		"filter_based_on": "Date Range",
	}


def bs_payload(f):
	cur = balance_sheet(f, f.to_date)
	prev = balance_sheet(f, f.prev_to)
	metrics = {}
	for key in (
		"total_assets",
		"current_assets",
		"fixed_assets",
		"total_liabilities",
		"current_liabilities",
		"long_term_liabilities",
		"equity",
		"working_capital",
		"current_ratio",
		"quick_ratio",
		"debt_to_equity",
	):
		c, p = cur[key], prev[key]
		metrics[key] = {
			"value": None if c is None else round(c, 2),
			"previous": None if p is None else round(p, 2),
			"growth": growth(c, p) if c is not None and p is not None else None,
		}
	return {
		"metrics": metrics,
		"asof": str(cur.asof),
		"prev_asof": str(prev.asof),
		"composition": {
			"labels": [_("Current Assets"), _("Fixed / Non-Current Assets")],
			"values": [round(cur.current_assets, 2), round(cur.fixed_assets, 2)],
		},
		"funding": {
			"labels": [_("Current Liabilities"), _("Long-Term Liabilities"), _("Equity")],
			"values": [round(cur.current_liabilities, 2), round(cur.long_term_liabilities, 2), round(cur.equity, 2)],
		},
		"route": report_route("Balance Sheet", {**_report_filters(f), "period_start_date": str(cur.asof), "periodicity": "Yearly"}),
	}


@frappe.whitelist()
@cached
def get_accounting_analytics(f):
	"""Profit & Loss, Balance Sheet, General Ledger and Expense analytics."""
	if not (frappe.has_permission("GL Entry", "read") and frappe.has_permission("Account", "read")):
		return locked(["GL Entry", "Account"])
	cur = profit_and_loss(f, f.from_date, f.to_date)
	gl = _gl_activity(f)

	leaves = cur.expense_leaves
	n = top_n()
	top = leaves[:n]
	rest = sum(x["amount"] for x in leaves[n:])
	expense_accounts = [{"account": x["account"], "label": x["label"], "amount": round(x["amount"], 2)} for x in top]
	if rest:
		expense_accounts.append({"account": None, "label": _("Others"), "amount": round(rest, 2)})

	prev = profit_and_loss(f, f.prev_from, f.prev_to)
	cost_centers = _expense_by_cost_center(f)
	departments = _expense_by_department(f)
	return {
		"profit_and_loss": pnl_payload(f),
		"balance_sheet": bs_payload(f),
		"general_ledger": {
			**gl,
			"major_expense_accounts": [
				{"account": x["account"], "label": x["label"], "amount": round(x["amount"], 2)} for x in leaves[:n]
			],
			"major_income_accounts": [
				{"account": x["account"], "label": x["label"], "amount": round(x["amount"], 2)} for x in cur.income_leaves[:n]
			],
			"route": report_route(
				"General Ledger",
				{"company": f.company, "from_date": str(f.from_date), "to_date": str(f.to_date), "group_by": "Group by Voucher (Consolidated)"},
			),
		},
		"expenses": {
			"total": {"value": round(cur.total_expense, 2), "previous": round(prev.total_expense, 2), "growth": growth(cur.total_expense, prev.total_expense)},
			"by_account": expense_accounts,
			"monthly": {"labels": cur.labels, "values": [round(v, 2) for v in cur.expense_m]},
			"by_cost_center": [{"label": r.cost_center, "amount": round(flt(r.amount), 2)} for r in cost_centers],
			"by_department": None
			if departments is None
			else [{"label": r.department, "amount": round(flt(r.amount), 2)} for r in departments],
			"department_note": None
			if departments is not None
			else _("Department is not an accounting dimension on this site, so GL expenses cannot be split by department."),
			"direct_vs_indirect": {
				"labels": [_("Direct Expenses"), _("Indirect Expenses")],
				"values": [round(cur.direct_expense, 2), round(cur.indirect_expense, 2)],
			},
		},
	}


def _statement_rows(rows, period_list, extra=None):
	out = []
	for r in rows:
		out.append(
			{
				"account": r["account"],
				"label": _account_label(r),
				"indent": cint(r.get("indent")),
				"is_group": cint(r.get("is_group")),
				"account_type": r.get("account_type"),
				"total": round(flt(r.get("total")), 2),
				"values": [round(v, 2) for v in _row_values(r, period_list)],
				**(extra(r) if extra else {}),
			}
		)
	return out


@frappe.whitelist()
@cached
def get_financial_statements(f):
	"""Hierarchical Profit & Loss and Balance Sheet (same rows as the standard reports)."""
	if not (frappe.has_permission("GL Entry", "read") and frappe.has_permission("Account", "read")):
		return locked(["GL Entry", "Account"])
	pl = profit_and_loss(f, f.from_date, f.to_date)
	bs = balance_sheet(f, f.to_date)
	bs_prev = balance_sheet(f, f.prev_to)

	def with_prev(section):
		prev_rows = {r["account"]: r for r in bs_prev[section]}
		key, prev_key = bs.key, bs_prev.key
		return lambda r: {"previous": round(flt(prev_rows.get(r["account"], {}).get(prev_key)), 2)}

	def bs_rows(section):
		rows = bs[section]
		out = _statement_rows(rows, [frappe._dict(key=bs.key)], with_prev(section))
		for o, r in zip(out, rows):
			o["total"] = round(flt(r.get(bs.key)), 2)
			o["class"] = r.get("bid_class")
		return out

	return {
		"profit_and_loss": {
			"labels": pl.labels,
			"income": _statement_rows(pl.income_rows, pl.period_list),
			"expenses": _statement_rows(pl.expense_rows, pl.period_list),
			"summary": {
				"total_income": round(pl.total_income, 2),
				"direct_expenses": round(pl.direct_expense, 2),
				"gross_profit": round(pl.gross_profit, 2),
				"indirect_expenses": round(pl.indirect_expense, 2),
				"net_profit": round(pl.net_profit, 2),
				"gross_margin": pl.gp_margin,
				"net_margin": pl.np_margin,
			},
			"route": report_route("Profit and Loss Statement", _report_filters(f)),
		},
		"balance_sheet": {
			"asof": str(bs.asof),
			"prev_asof": str(bs_prev.asof),
			"assets": bs_rows("assets"),
			"liabilities": bs_rows("liabilities"),
			"equity_accounts": bs_rows("equity_rows"),
			"summary": {
				"total_assets": round(bs.total_assets, 2),
				"current_assets": round(bs.current_assets, 2),
				"fixed_assets": round(bs.fixed_assets, 2),
				"current_liabilities": round(bs.current_liabilities, 2),
				"long_term_liabilities": round(bs.long_term_liabilities, 2),
				"total_liabilities": round(bs.total_liabilities, 2),
				"equity": round(bs.equity, 2),
				"equity_accounts": round(bs.equity_accounts, 2),
				"retained_earnings_and_unclosed": round(bs.retained, 2),
				"working_capital": round(bs.working_capital, 2),
			},
			"route": report_route("Balance Sheet", {**_report_filters(f), "period_start_date": str(bs.asof), "periodicity": "Yearly"}),
		},
	}
