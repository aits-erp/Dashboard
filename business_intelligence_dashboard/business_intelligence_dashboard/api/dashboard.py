"""Executive dashboard: filter metadata and the KPI card / overview chart payload."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from business_intelligence_dashboard.business_intelligence_dashboard.api import accounting
from business_intelligence_dashboard.business_intelligence_dashboard.api.cash_flow import cash_flows, cash_summary
from business_intelligence_dashboard.business_intelligence_dashboard.api.purchase import purchase_totals
from business_intelligence_dashboard.business_intelligence_dashboard.api.receivables import outstanding_total
from business_intelligence_dashboard.business_intelligence_dashboard.api.sales import sales_totals
from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	DASHBOARD_ROLES,
	_fiscal_year_for,
	cached,
	default_company,
	get_permitted_companies,
	get_settings,
	growth,
	list_route,
	month_label,
	months_between,
	report_route,
	require_dashboard_access,
	sales_invoice_scope,
)


@frappe.whitelist()
def get_filter_options(company=None):
	"""Metadata for the filter bar and the sections the current user may open."""
	require_dashboard_access()
	companies = get_permitted_companies()
	company = company if company in companies else default_company(companies)
	today = getdate(frappe.utils.nowdate())
	fy_name, fy_start, fy_end = _fiscal_year_for(today, company)
	fiscal_years = frappe.get_all(
		"Fiscal Year",
		filters={"disabled": 0},
		fields=["name", "year_start_date", "year_end_date"],
		order_by="year_start_date desc",
	)
	# hide placeholder fiscal years created by test fixtures far in the future
	fiscal_years = [f for f in fiscal_years if getdate(f.year_start_date).year <= today.year + 1 and not f.name.startswith("_Test")]
	can = frappe.has_permission
	return {
		"companies": companies,
		"company": company,
		"currency": frappe.get_cached_value("Company", company, "default_currency"),
		"fiscal_years": [
			{"name": f.name, "from_date": str(f.year_start_date), "to_date": str(f.year_end_date)} for f in fiscal_years
		],
		"fiscal_year": fy_name,
		"from_date": str(fy_start),
		"to_date": str(min(today, fy_end)),
		"has_department_dimension": bool(frappe.db.has_column("GL Entry", "department")),
		"sections": {
			"executive": True,
			"sales": can("Sales Invoice", "read"),
			"purchase": can("Purchase Invoice", "read"),
			"accounting": can("GL Entry", "read") and can("Account", "read"),
			"statements": can("GL Entry", "read") and can("Account", "read"),
			"receivables": can("Sales Invoice", "read") and can("Payment Ledger Entry", "read"),
			"payables": can("Purchase Invoice", "read") and can("Payment Ledger Entry", "read"),
			"cashflow": can("GL Entry", "read"),
			"inventory": can("Stock Ledger Entry", "read") and can("Item", "read"),
			"gst": can("GL Entry", "read"),
			"insights": True,
		},
		"can_configure": "System Manager" in frappe.get_roles(),
		"thresholds": dict(get_settings()),
	}


def card(key, label, value, previous, fmt, icon, group, good="up", route=None, hint=None, show_growth=True):
	return {
		"key": key,
		"label": label,
		"group": group,
		"value": None if value is None else round(flt(value), 2),
		"previous": None if previous is None else round(flt(previous), 2),
		"growth": growth(value, previous) if show_growth and value is not None and previous is not None else None,
		"format": fmt,
		"icon": icon,
		"good": good,
		"route": route,
		"hint": hint,
	}


@frappe.whitelist()
@cached
def get_executive_dashboard(f):
	can = frappe.has_permission
	cards, restricted, charts = [], [], {}
	period = {"from_date": str(f.from_date), "to_date": str(f.to_date)}
	inv_filters = {"company": f.company, "docstatus": 1, "posting_date": ["Between", [str(f.from_date), str(f.to_date)]]}

	# ------------------------------------------------------------ financial
	if can("GL Entry", "read") and can("Account", "read"):
		cur = accounting.profit_and_loss(f, f.from_date, f.to_date)
		prev = accounting.profit_and_loss(f, f.prev_from, f.prev_to)
		bs, bs_prev = accounting.balance_sheet(f, f.to_date), accounting.balance_sheet(f, f.prev_to)
		pl_route = accounting.report_route("Profit and Loss Statement", accounting._report_filters(f))
		bs_route = report_route("Balance Sheet", {**accounting._report_filters(f), "period_start_date": str(bs.asof), "periodicity": "Yearly"})
		g = "financial"
		cards += [
			card("revenue", _("Total Revenue"), cur.total_income, prev.total_income, "currency", "trending-up", g, route=pl_route),
			card("expenses", _("Total Expenses"), cur.total_expense, prev.total_expense, "currency", "receipt", g, "down", pl_route),
			card("gross_profit", _("Gross Profit"), cur.gross_profit, prev.gross_profit, "currency", "layers", g, route=pl_route),
			card("net_profit", _("Net Profit"), cur.net_profit, prev.net_profit, "currency", "award", g, route=pl_route),
			card("gp_margin", _("Gross Profit Margin"), cur.gp_margin, prev.gp_margin, "percent", "percent", g, route=pl_route),
			card("np_margin", _("Net Profit Margin"), cur.np_margin, prev.np_margin, "percent", "pie-chart", g, route=pl_route),
			card("assets", _("Total Assets"), bs.total_assets, bs_prev.total_assets, "currency", "briefcase", g, route=bs_route),
			card("liabilities", _("Total Liabilities"), bs.total_liabilities, bs_prev.total_liabilities, "currency", "scale", g, "down", bs_route),
		]
		charts["income_vs_expense"] = {
			"labels": cur.labels,
			"income": [round(v, 2) for v in cur.income_m],
			"expense": [round(v, 2) for v in cur.expense_m],
		}
		charts["profit_trend"] = {"labels": cur.labels, "values": [round(v, 2) for v in cur.net_m]}
	else:
		restricted.append("financial")

	# ---------------------------------------------------------------- sales
	if can("Sales Invoice", "read"):
		s, sp = sales_totals(f), sales_totals(f, previous=True)
		g = "sales"
		ar_total = ar_prev = None
		if can("Payment Ledger Entry", "read"):
			ar_total = outstanding_total(f, "Customer", f.to_date)
			ar_prev = outstanding_total(f, "Customer", f.prev_to)
		cards += [
			card("sales", _("Total Sales"), s.net_sales, sp.net_sales, "currency", "shopping-cart", g, route=list_route("Sales Invoice", inv_filters), hint=_("Net of returns, before tax")),
			card("sales_orders", _("Sales Orders"), s.orders, sp.orders, "number", "clipboard", g, route=list_route("Sales Order", {"company": f.company, "docstatus": 1, "transaction_date": inv_filters["posting_date"]})),
			card("sales_invoices", _("Sales Invoices"), s.invoices, sp.invoices, "number", "file-text", g, route=list_route("Sales Invoice", {**inv_filters, "is_return": 0})),
			card("sales_returns", _("Sales Returns"), abs(s.returns_amount), abs(sp.returns_amount), "currency", "rotate-ccw", g, "down", list_route("Sales Invoice", {**inv_filters, "is_return": 1})),
			card("sales_growth", _("Sales Growth"), growth(s.net_sales, sp.net_sales), None, "percent", "activity", g, route=list_route("Sales Invoice", inv_filters), hint=_("vs previous period"), show_growth=False),
		]
		if ar_total is not None:
			cards.append(
				card("receivables", _("Outstanding Receivables"), ar_total, ar_prev, "currency", "inbox", g, "down", report_route("Accounts Receivable", {"company": f.company, "report_date": str(f.to_date), "ageing_based_on": "Due Date"}))
			)
		months = months_between(f.from_date, f.to_date)
		by_month = {r.month: flt(r.value) for r in sales_invoice_scope(f).query("date_format(h.posting_date,'%%Y-%%m') as month, sum(i.base_net_amount) as value", "group by 1")}
		charts["sales_monthly"] = {"labels": [month_label(m) for m in months], "values": [round(by_month.get(m, 0.0), 2) for m in months]}
		top = sales_invoice_scope(f).query(
			"h.customer_name as label, sum(i.base_net_amount) as value", "group by h.customer, h.customer_name order by value desc limit 5"
		)
		charts["top_customers"] = [{"label": r.label, "value": round(flt(r.value), 2)} for r in top]
	else:
		restricted.append("sales")

	# ------------------------------------------------------------- purchase
	if can("Purchase Invoice", "read"):
		p, pp = purchase_totals(f), purchase_totals(f, previous=True)
		g = "purchase"
		cards += [
			card("purchases", _("Total Purchases"), p.net_purchases, pp.net_purchases, "currency", "truck", g, "down", list_route("Purchase Invoice", inv_filters), _("Net of returns, before tax")),
			card("purchase_orders", _("Purchase Orders"), p.orders, pp.orders, "number", "clipboard-list", g, "neutral", list_route("Purchase Order", {"company": f.company, "docstatus": 1, "transaction_date": inv_filters["posting_date"]})),
			card("purchase_invoices", _("Purchase Invoices"), p.invoices, pp.invoices, "number", "file-minus", g, "neutral", list_route("Purchase Invoice", {**inv_filters, "is_return": 0})),
			card("purchase_returns", _("Purchase Returns"), abs(p.returns_amount), abs(pp.returns_amount), "currency", "corner-up-left", g, "neutral", list_route("Purchase Invoice", {**inv_filters, "is_return": 1})),
		]
		if can("Payment Ledger Entry", "read"):
			ap = outstanding_total(f, "Supplier", f.to_date)
			ap_prev = outstanding_total(f, "Supplier", f.prev_to)
			cards.append(card("payables", _("Outstanding Payables"), ap, ap_prev, "currency", "credit-card", g, "down", report_route("Accounts Payable", {"company": f.company, "report_date": str(f.to_date), "ageing_based_on": "Due Date"})))
	else:
		restricted.append("purchase")

	# ----------------------------------------------------------------- cash
	if can("GL Entry", "read"):
		c = cash_summary(f)
		g = "cash"
		acc_route = list_route("Bank Account", {"company": f.company})
		gl_route = report_route("General Ledger", {"company": f.company, "from_date": str(f.from_date), "to_date": str(f.to_date)})
		cards += [
			card("cash", _("Cash Balance"), c.cash, c.p_cash, "currency", "dollar-sign", g, route=gl_route),
			card("bank", _("Bank Balance"), c.bank, c.p_bank, "currency", "landmark", g, route=acc_route),
			card("cash_bank", _("Total Cash & Bank"), c.total, c.p_total, "currency", "wallet", g, route=acc_route),
			card("inflow", _("Cash Inflow"), c.inflow, c.p_inflow, "currency", "arrow-down-circle", g, route=gl_route),
			card("outflow", _("Cash Outflow"), c.outflow, c.p_outflow, "currency", "arrow-up-circle", g, "down", gl_route),
			card("net_cash", _("Net Cash Flow"), c.net, c.p_net, "currency", "repeat", g, route=gl_route),
		]
		_i, _o, monthly = cash_flows(f, f.from_date, f.to_date)
		months = months_between(f.from_date, f.to_date)
		charts["cash_flow"] = {
			"labels": [month_label(m) for m in months],
			"inflow": [round(monthly.get(m, (0, 0))[0], 2) for m in months],
			"outflow": [round(monthly.get(m, (0, 0))[1], 2) for m in months],
		}
	else:
		restricted.append("cash")

	if "sales_monthly" in charts and can("Purchase Invoice", "read"):
		from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import purchase_invoice_scope

		months = months_between(f.from_date, f.to_date)
		pm = {r.month: flt(r.value) for r in purchase_invoice_scope(f).query("date_format(h.posting_date,'%%Y-%%m') as month, sum(i.base_net_amount) as value", "group by 1")}
		charts["sales_vs_purchase"] = {
			"labels": charts["sales_monthly"]["labels"],
			"sales": charts["sales_monthly"]["values"],
			"purchases": [round(pm.get(m, 0.0), 2) for m in months],
		}

	return {"cards": cards, "charts": charts, "restricted": restricted, "filters_applied": period}
