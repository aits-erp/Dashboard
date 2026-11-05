"""Business insights & management alerts.

Every alert is computed from live records and the thresholds in *BI Dashboard Settings*.
An alert the user is not permitted to see is reported as ``restricted`` instead of failing.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt

from business_intelligence_dashboard.business_intelligence_dashboard.api import accounting
from business_intelligence_dashboard.business_intelligence_dashboard.api.cash_flow import _reconciliation
from business_intelligence_dashboard.business_intelligence_dashboard.api.inventory import get_inventory
from business_intelligence_dashboard.business_intelligence_dashboard.api.receivables import (
	run_ageing_report,
	summarise,
)
from business_intelligence_dashboard.business_intelligence_dashboard.api.sales import sales_totals
from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	cached,
	get_settings,
	growth,
	list_route,
	report_route,
)

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "ok": 3}


def _alert(key, title, severity, count=0, amount=None, message="", rows=None, route=None, restricted=False):
	return {
		"key": key,
		"title": title,
		"severity": "ok" if (not count and not restricted and severity != "info") else severity,
		"count": count,
		"amount": None if amount is None else round(flt(amount), 2),
		"message": message,
		"rows": rows or [],
		"route": route,
		"restricted": restricted,
	}


def _restricted(key, title, doctype):
	return _alert(key, title, "info", restricted=True, message=_("Requires read access to {0}.").format(_(doctype)))


@frappe.whitelist()
@cached
def get_insights(f):
	s = get_settings()
	alerts = []
	can = frappe.has_permission
	today = f.today

	# ---- receivables
	if can("Sales Invoice", "read") and can("Payment Ledger Entry", "read"):
		ar = summarise(f, run_ageing_report(f, "Customer"), "customers")
		late = [r for r in ar["overdue_invoices"] if r["days"] >= int(s.overdue_days_alert)]
		alerts.append(
			_alert(
				"overdue_customer_invoices",
				_("Overdue customer invoices"),
				"critical" if late else "ok",
				len(late),
				sum(r["outstanding"] for r in late),
				_("{0} invoices are more than {1} days past due.").format(len(late), s.overdue_days_alert),
				[{"label": r["voucher_no"], "detail": r["party"], "value": r["outstanding"], "days": r["days"]} for r in late[:5]],
				report_route("Accounts Receivable", {"company": f.company, "report_date": str(f.to_date), "ageing_based_on": "Due Date"}),
			)
		)
		high = [p for p in ar["by_party"] if p["outstanding"] >= flt(s.high_outstanding_amount)]
		alerts.append(
			_alert(
				"high_outstanding_customers",
				_("High outstanding customers"),
				"warning" if high else "ok",
				len(high),
				sum(p["outstanding"] for p in high),
				_("{0} customers owe at least {1}.").format(len(high), frappe.format_value(flt(s.high_outstanding_amount), {"fieldtype": "Currency"})),
				[{"label": p["party"], "value": p["outstanding"]} for p in high[:5]],
				report_route("Accounts Receivable", {"company": f.company, "report_date": str(f.to_date), "group_by_party": 1}),
			)
		)
	else:
		alerts.append(_restricted("overdue_customer_invoices", _("Overdue customer invoices"), "Sales Invoice"))

	if can("Purchase Invoice", "read") and can("Payment Ledger Entry", "read"):
		ap = summarise(f, run_ageing_report(f, "Supplier"), "suppliers")
		late = [r for r in ap["overdue_invoices"] if r["days"] >= 1]
		alerts.append(
			_alert(
				"overdue_supplier_payments",
				_("Overdue supplier payments"),
				"critical" if late else "ok",
				len(late),
				sum(r["outstanding"] for r in late),
				_("{0} supplier bills are past their due date.").format(len(late)),
				[{"label": r["voucher_no"], "detail": r["party"], "value": r["outstanding"], "days": r["days"]} for r in late[:5]],
				report_route("Accounts Payable", {"company": f.company, "report_date": str(f.to_date), "ageing_based_on": "Due Date"}),
			)
		)
	else:
		alerts.append(_restricted("overdue_supplier_payments", _("Overdue supplier payments"), "Purchase Invoice"))

	# ---- stock
	if can("Stock Ledger Entry", "read") and can("Item", "read"):
		inv = get_inventory(_raw(f))
		alerts.append(
			_alert(
				"negative_stock", _("Negative stock"), "critical" if inv["negative_count"] else "ok", inv["negative_count"],
				sum(r["value"] for r in inv["negative_stock"]),
				_("{0} item/warehouse combinations have negative stock.").format(inv["negative_count"]),
				[{"label": r["item_code"], "detail": r["warehouse"], "value": r["qty"]} for r in inv["negative_stock"][:5]],
				inv["routes"]["negative"],
			)
		)
		alerts.append(
			_alert(
				"low_stock", _("Low stock"), "warning" if inv["low_stock_count"] or inv["reorder_count"] else "ok",
				inv["low_stock_count"] + inv["reorder_count"], None,
				_("{0} items are below safety stock and {1} are below their reorder level.").format(inv["low_stock_count"], inv["reorder_count"]),
				[{"label": r["item_code"], "detail": _("short by {0}").format(r["shortfall"])} for r in inv["low_stock"][:5]],
				inv["routes"]["projected"],
			)
		)
	else:
		alerts.append(_restricted("negative_stock", _("Negative stock"), "Stock Ledger Entry"))

	# ---- orders
	if can("Sales Order", "read"):
		cutoff = add_days(today, -int(s.pending_order_days))
		so = frappe.db.sql(
			"""select name, customer_name, transaction_date, base_grand_total * (100 - per_delivered) / 100 as pending
			from `tabSales Order` where docstatus = 1 and company = %(company)s
			and status in ('To Deliver and Bill', 'To Deliver') and transaction_date <= %(cutoff)s
			order by transaction_date limit 200""",
			{"company": f.company, "cutoff": cutoff},
			as_dict=True,
		)
		alerts.append(
			_alert(
				"pending_sales_orders", _("Pending sales orders"), "warning" if so else "ok", len(so), sum(flt(r.pending) for r in so),
				_("{0} sales orders are older than {1} days and still undelivered.").format(len(so), s.pending_order_days),
				[{"label": r.name, "detail": r.customer_name, "value": flt(r.pending)} for r in so[:5]],
				list_route("Sales Order", {"status": ["in", ["To Deliver and Bill", "To Deliver"]], "company": f.company, "docstatus": 1}),
			)
		)
	if can("Purchase Order", "read"):
		cutoff = add_days(today, -int(s.delayed_po_days))
		po = frappe.db.sql(
			"""select name, supplier_name, schedule_date, base_grand_total * (100 - per_received) / 100 as pending
			from `tabPurchase Order` where docstatus = 1 and company = %(company)s
			and status in ('To Receive and Bill', 'To Receive') and schedule_date < %(cutoff)s
			order by schedule_date limit 200""",
			{"company": f.company, "cutoff": cutoff},
			as_dict=True,
		)
		alerts.append(
			_alert(
				"delayed_purchase_orders", _("Delayed purchase orders"), "warning" if po else "ok", len(po), sum(flt(r.pending) for r in po),
				_("{0} purchase orders are more than {1} days past their schedule date.").format(len(po), s.delayed_po_days),
				[{"label": r.name, "detail": r.supplier_name, "value": flt(r.pending)} for r in po[:5]],
				list_route("Purchase Order", {"status": ["in", ["To Receive and Bill", "To Receive"]], "company": f.company, "docstatus": 1}),
			)
		)

	# ---- bank
	if can("GL Entry", "read"):
		rec = _reconciliation(f)
		uncleared = sum(a["uncleared_vouchers"] for a in rec["accounts"])
		bt = (rec["transactions"] or {}).get("count", 0)
		amount = sum(a["uncleared_deposits"] + a["uncleared_withdrawals"] for a in rec["accounts"])
		alerts.append(
			_alert(
				"unreconciled_bank", _("Unreconciled bank activity"), "warning" if uncleared or bt else "ok", uncleared + bt, amount,
				_("{0} bank vouchers have no clearance date and {1} bank transactions are unreconciled.").format(uncleared, bt),
				[{"label": a["label"], "value": a["uncleared_deposits"] + a["uncleared_withdrawals"], "detail": _("{0} vouchers").format(a["uncleared_vouchers"])} for a in rec["accounts"] if a["uncleared_vouchers"]][:5],
				{"type": "route", "route": ["bank-reconciliation-tool"]},
			)
		)

	# ---- trends: expenses, sales, profitability
	if can("GL Entry", "read") and can("Account", "read"):
		cur = accounting.profit_and_loss(f, f.from_date, f.to_date)
		prev = accounting.profit_and_loss(f, f.prev_from, f.prev_to)
		prev_by = {x["account"]: x["amount"] for x in prev.expense_leaves}
		floor = max(cur.total_expense * 0.01, 1)
		spikes = []
		for x in cur.expense_leaves:
			p = prev_by.get(x["account"], 0.0)
			g = growth(x["amount"], p)
			if x["amount"] >= floor and p > 0 and g is not None and g >= flt(s.expense_increase_percent):
				spikes.append({"label": x["label"], "value": x["amount"], "detail": f"+{g}%", "growth": g, "delta": x["amount"] - p})
		spikes.sort(key=lambda r: -r["delta"])
		alerts.append(
			_alert(
				"expense_spikes", _("Unusual expense increases"), "warning" if spikes else "ok", len(spikes),
				sum(r["value"] for r in spikes),
				_("{0} expense accounts grew by at least {1}% versus the previous period.").format(len(spikes), s.expense_increase_percent),
				spikes[:5], report_route("Profit and Loss Statement", accounting._report_filters(f)),
			)
		)
		low = cur.total_income > 0 and cur.np_margin < flt(s.low_margin_percent)
		alerts.append(
			_alert(
				"low_profitability", _("Low profitability"), ("critical" if cur.net_profit < 0 else "warning") if low else "ok",
				1 if low else 0, cur.net_profit,
				_("Net profit margin is {0}% (threshold {1}%); gross margin {2}%.").format(cur.np_margin, s.low_margin_percent, cur.gp_margin),
				[], report_route("Profit and Loss Statement", accounting._report_filters(f)),
			)
		)
	if can("Sales Invoice", "read"):
		sc, sp = sales_totals(f), sales_totals(f, previous=True)
		g = growth(sc.net_sales, sp.net_sales)
		declining = g is not None and g <= -flt(s.sales_decline_percent)
		alerts.append(
			_alert(
				"declining_sales", _("Declining sales"), "critical" if declining else "ok", 1 if declining else 0, sc.net_sales - sp.net_sales,
				_("Sales are {0}% versus the previous period.").format(g) if g is not None else _("No previous-period sales to compare against."),
				[], list_route("Sales Invoice", {"company": f.company, "docstatus": 1}),
			)
		)

	alerts.sort(key=lambda a: SEVERITY_ORDER[a["severity"]])
	counts = {k: sum(1 for a in alerts if a["severity"] == k) for k in SEVERITY_ORDER}
	return {"alerts": alerts, "counts": counts, "thresholds": {k: s[k] for k in s}}


def _raw(f):
	"""Filters as the plain dict ``get_inventory`` (a cached endpoint) expects."""
	raw = {"company": f.company, "from_date": str(f.from_date), "to_date": str(f.to_date)}
	for key in ("customer", "supplier", "sales_person", "territory", "item_group", "warehouse", "department", "cost_center"):
		if f.get(key):
			raw[key] = f[key]
	return raw
