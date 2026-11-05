"""Sales analytics - all figures from submitted Sales Invoice / Sales Order records.

Sales are measured on ``base_net_amount`` of invoice items (company currency, net of
tax and discounts).  Returns (credit notes) are included with their negative sign in
net figures and reported separately in the returns analysis.
"""

import frappe
from frappe import _
from frappe.utils import add_years, flt

from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	cached,
	date_range,
	growth,
	list_route,
	locked,
	months_between,
	month_label,
	require_permission,
	sales_invoice_scope,
	sales_order_scope,
	series_by_month,
	top_n,
)


def sales_totals(f, previous=False):
	"""Headline sales numbers for a period (used by the executive dashboard as well)."""
	sc = sales_invoice_scope(f, previous)
	row = sc.query(
		"ifnull(sum(i.base_net_amount),0) as net_sales, "
		"ifnull(sum(case when h.is_return = 0 then i.base_net_amount else 0 end),0) as gross_sales, "
		"ifnull(sum(case when h.is_return = 1 then i.base_net_amount else 0 end),0) as returns_amount, "
		"count(distinct case when h.is_return = 0 then h.name end) as invoices, "
		"count(distinct case when h.is_return = 1 then h.name end) as returns"
	)[0]
	so = sales_order_scope(f, previous)
	orders = so.query(
		"count(distinct h.name) as orders, ifnull(sum(i.base_net_amount),0) as order_value",
		extra_where="and h.status != 'Cancelled'",
	)[0]
	return frappe._dict(
		net_sales=flt(row.net_sales),
		gross_sales=flt(row.gross_sales),
		returns_amount=flt(row.returns_amount),
		invoices=row.invoices,
		returns=row.returns,
		orders=orders.orders,
		order_value=flt(orders.order_value),
	)


@frappe.whitelist()
@cached
def get_sales_analytics(f):
	if not frappe.has_permission("Sales Invoice", "read"):
		return locked(["Sales Invoice"])
	n = top_n()
	sc = sales_invoice_scope(f)
	months = months_between(f.from_date, f.to_date)

	monthly = sc.query("date_format(h.posting_date,'%%Y-%%m') as month, sum(i.base_net_amount) as value", "group by 1")
	daily = sc.query("h.posting_date as day, sum(i.base_net_amount) as value", "group by 1 order by 1")

	# year-wise: month-of-year series per fiscal year across the whole selected company history
	# year-wise: whole fiscal years (this one and the two before), months aligned to the fiscal year start
	wide = frappe._dict(f)
	wide.from_date, wide.to_date = add_years(f.fy_start, -2), f.fy_end
	wsc = sales_invoice_scope(wide)
	wsc.sql_from += (
		" join `tabFiscal Year` fy on h.posting_date between fy.year_start_date and fy.year_end_date"
		" and left(fy.name, 1) != '_'"
	)
	start_month = f.fy_start.month
	yearly = {}
	for r in wsc.query("fy.name as fy, month(h.posting_date) as m, sum(i.base_net_amount) as value", "group by 1, 2 order by fy.name"):
		yearly.setdefault(r.fy, [0.0] * 12)[(int(r.m) - start_month) % 12] += flt(r.value)

	by_customer = sc.query(
		"h.customer, h.customer_name, sum(i.base_net_amount) as value",
		"group by h.customer, h.customer_name having sum(i.base_net_amount) != 0 order by value desc limit %(limit)s",
		extra_params={"limit": 200},
	)
	by_item = sc.query(
		"i.item_code, i.item_name, sum(i.base_net_amount) as value, sum(i.stock_qty) as qty",
		"group by i.item_code, i.item_name having sum(i.base_net_amount) != 0 order by value desc limit %(limit)s",
		extra_params={"limit": 200},
	)
	by_group = sc.query(
		"ifnull(i.item_group,'Not set') as label, sum(i.base_net_amount) as value", "group by 1 order by 2 desc limit %(limit)s",
		extra_params={"limit": n + 5},
	)
	by_territory = sc.query(
		"ifnull(h.territory,'Not set') as label, sum(i.base_net_amount) as value", "group by 1 order by 2 desc limit %(limit)s",
		extra_params={"limit": n + 5},
	)

	# sales person: allocated share from the Sales Team of each invoice
	team_where, team_params = "", {}
	if f.sales_persons is not None:
		team_where, team_params = "and st.sales_person in %(sps)s", {"sps": tuple(f.sales_persons) or ("",)}
	sp = frappe.db.sql(
		f"""select st.sales_person as label,
			sum(inv.net * ifnull(st.allocated_percentage, 100) / 100) as value
		from (select h.name, sum(i.base_net_amount) as net {sc.sql_from} where {sc.where} group by h.name) inv
		join `tabSales Team` st on st.parent = inv.name and st.parenttype = 'Sales Invoice'
		where 1=1 {team_where}
		group by st.sales_person order by value desc limit %(limit)s""",
		{**sc.params, **team_params, "limit": n + 10},
		as_dict=True,
	)

	target = _target_vs_achievement(f, sp)

	so_status = sales_order_scope(f).query(
		"h.status as label, count(distinct h.name) as count, sum(i.base_net_amount) as value",
		"group by h.status order by count desc",
		extra_where="and h.status != 'Cancelled'",
	)

	pending = sales_order_scope(f).query(
		"h.name, h.customer, h.customer_name, h.delivery_date, h.transaction_date, "
		"sum((i.qty - i.delivered_qty) * i.base_net_rate) as pending_value, sum(i.qty - i.delivered_qty) as pending_qty, "
		"datediff(%(today)s, h.delivery_date) as days_late",
		"group by h.name, h.customer, h.customer_name, h.delivery_date, h.transaction_date "
		"having pending_qty > 0 order by h.delivery_date limit %(limit)s",
		extra_where="and h.status not in ('Closed','Completed','Cancelled','Draft','On Hold')",
		extra_params={"today": f.today, "limit": 100},
	)

	si_status = sc.query(
		"h.status as label, count(distinct h.name) as count, sum(i.base_net_amount) as value", "group by h.status order by count desc"
	)

	returns = sc.query(
		"date_format(h.posting_date,'%%Y-%%m') as month, sum(i.base_net_amount) as value, count(distinct h.name) as count",
		"group by 1",
		extra_where="and h.is_return = 1",
	)
	ret_cust = sc.query(
		"h.customer, h.customer_name, sum(i.base_net_amount) as value, count(distinct h.name) as count",
		"group by h.customer, h.customer_name order by value limit %(limit)s",
		extra_where="and h.is_return = 1",
		extra_params={"limit": n},
	)

	cur, prev = sales_totals(f), sales_totals(f, previous=True)
	drill = {"posting_date": ["Between", [str(f.from_date), str(f.to_date)]], "docstatus": 1, "company": f.company}

	return {
		"kpis": {
			"net_sales": {"value": cur.net_sales, "previous": prev.net_sales, "growth": growth(cur.net_sales, prev.net_sales)},
			"invoices": {"value": cur.invoices, "previous": prev.invoices, "growth": growth(cur.invoices, prev.invoices)},
			"orders": {"value": cur.orders, "previous": prev.orders, "growth": growth(cur.orders, prev.orders)},
			"returns": {"value": cur.returns_amount, "previous": prev.returns_amount, "growth": growth(cur.returns_amount, prev.returns_amount)},
		},
		"monthly": series_by_month([{"month": r.month, "value": r.value} for r in monthly], months),
		"daily": {"labels": [str(r.day) for r in daily], "values": [round(flt(r.value), 2) for r in daily]},
		"yearly": {
			"labels": [month_label(f"2000-{(start_month - 1 + k) % 12 + 1:02d}")[:3] for k in range(12)],
			"series": [
				{"name": k, "values": [round(v, 2) for v in vals]} for k, vals in sorted(yearly.items()) if any(vals)
			],
		},
		"by_customer": _rows(by_customer, "customer_name", "customer", n=None),
		"top_customers": _rows(by_customer, "customer_name", "customer", n=n),
		"by_item": _rows(by_item, "item_name", "item_code", n=None),
		"top_items": _rows(by_item, "item_name", "item_code", n=n),
		"by_item_group": [{"label": r.label, "value": round(flt(r.value), 2)} for r in by_group],
		"by_territory": [{"label": r.label, "value": round(flt(r.value), 2)} for r in by_territory],
		"by_sales_person": [{"label": r.label, "value": round(flt(r.value), 2)} for r in sp],
		"target_vs_achievement": target,
		"so_status": [{"label": r.label, "count": r.count, "value": round(flt(r.value), 2)} for r in so_status],
		"pending_delivery": [
			{
				"name": r.name,
				"customer": r.customer_name or r.customer,
				"delivery_date": str(r.delivery_date) if r.delivery_date else None,
				"pending_qty": round(flt(r.pending_qty), 2),
				"pending_value": round(flt(r.pending_value), 2),
				"days_late": max(int(r.days_late or 0), 0),
			}
			for r in pending
		],
		"pending_delivery_total": round(sum(flt(r.pending_value) for r in pending), 2),
		"si_status": [{"label": r.label, "count": r.count, "value": round(flt(r.value), 2)} for r in si_status],
		"returns": {
			"monthly": series_by_month([{"month": r.month, "value": abs(flt(r.value))} for r in returns], months),
			"count": sum(r.count for r in returns),
			"amount": round(abs(sum(flt(r.value) for r in returns)), 2),
			"by_customer": [
				{"label": r.customer_name or r.customer, "value": round(abs(flt(r.value)), 2), "count": r.count} for r in ret_cust
			],
			"rate_percent": round(abs(cur.returns_amount) / cur.gross_sales * 100, 2) if cur.gross_sales else 0.0,
		},
		"routes": {
			"invoices": list_route("Sales Invoice", {**drill, "is_return": 0}),
			"orders": list_route("Sales Order", {"transaction_date": drill["posting_date"], "docstatus": 1, "company": f.company}),
			"returns": list_route("Sales Invoice", {**drill, "is_return": 1}),
			"pending_delivery": list_route(
				"Sales Order", {"status": ["in", ["To Deliver and Bill", "To Deliver"]], "company": f.company, "docstatus": 1}
			),
		},
	}


def _rows(rows, label_key, name_key, n=None):
	rows = rows[:n] if n else rows
	return [{"label": r.get(label_key) or r.get(name_key), "name": r.get(name_key), "value": round(flt(r.value), 2)} for r in rows]


def _target_vs_achievement(f, achieved_rows):
	"""Sales Person targets (Target Detail child rows) for the fiscal year vs achievement."""
	if not frappe.has_permission("Sales Person", "read"):
		return {"rows": [], "note": _("No permission to read Sales Person targets.")}
	targets = frappe.db.sql(
		"""select td.parent as sales_person, sum(td.target_amount) as target
		from `tabTarget Detail` td where td.parenttype = 'Sales Person' and td.fiscal_year = %(fy)s
		group by td.parent""",
		{"fy": f.fiscal_year},
		as_dict=True,
	)
	if not targets:
		return {"rows": [], "note": _("No Sales Person targets are defined for fiscal year {0}.").format(f.fiscal_year)}
	achieved = {r.label: flt(r.value) for r in achieved_rows}
	rows = []
	for t in targets:
		if f.sales_persons is not None and t.sales_person not in f.sales_persons:
			continue
		a = achieved.get(t.sales_person, 0.0)
		rows.append(
			{
				"label": t.sales_person,
				"target": round(flt(t.target), 2),
				"achieved": round(a, 2),
				"percent": round(a / flt(t.target) * 100, 2) if flt(t.target) else 0.0,
			}
		)
	return {"rows": sorted(rows, key=lambda r: -r["target"]), "note": None}
