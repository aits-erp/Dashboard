"""Purchase analytics from submitted Purchase Order / Receipt / Invoice records."""

import frappe
from frappe import _
from frappe.utils import flt

from business_intelligence_dashboard.business_intelligence_dashboard.api.sales import sales_totals
from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	cached,
	growth,
	list_route,
	locked,
	months_between,
	purchase_invoice_scope,
	purchase_order_scope,
	purchase_receipt_scope,
	sales_invoice_scope,
	series_by_month,
	top_n,
)


def purchase_totals(f, previous=False):
	row = purchase_invoice_scope(f, previous).query(
		"ifnull(sum(i.base_net_amount),0) as net_purchases, "
		"ifnull(sum(case when h.is_return = 0 then i.base_net_amount else 0 end),0) as gross_purchases, "
		"ifnull(sum(case when h.is_return = 1 then i.base_net_amount else 0 end),0) as returns_amount, "
		"count(distinct case when h.is_return = 0 then h.name end) as invoices, "
		"count(distinct case when h.is_return = 1 then h.name end) as returns"
	)[0]
	orders = purchase_order_scope(f, previous).query(
		"count(distinct h.name) as orders, ifnull(sum(i.base_net_amount),0) as order_value",
		extra_where="and h.status != 'Cancelled'",
	)[0]
	return frappe._dict(
		net_purchases=flt(row.net_purchases),
		gross_purchases=flt(row.gross_purchases),
		returns_amount=flt(row.returns_amount),
		invoices=row.invoices,
		returns=row.returns,
		orders=orders.orders,
		order_value=flt(orders.order_value),
	)


def _label_rows(rows, label="label"):
	return [{"label": r.get(label), "value": round(flt(r.value), 2), "count": r.get("count")} for r in rows]


@frappe.whitelist()
@cached
def get_purchase_analytics(f):
	if not frappe.has_permission("Purchase Invoice", "read"):
		return locked(["Purchase Invoice"])
	n = top_n()
	months = months_between(f.from_date, f.to_date)
	pi = purchase_invoice_scope(f)
	po = purchase_order_scope(f)
	pr = purchase_receipt_scope(f)

	monthly = pi.query("date_format(h.posting_date,'%%Y-%%m') as month, sum(i.base_net_amount) as value", "group by 1")
	by_supplier = pi.query(
		"h.supplier, h.supplier_name, sum(i.base_net_amount) as value",
		"group by h.supplier, h.supplier_name having sum(i.base_net_amount) != 0 order by value desc limit %(limit)s",
		extra_params={"limit": 200},
	)
	by_group = pi.query(
		"ifnull(i.item_group,'Not set') as label, sum(i.base_net_amount) as value",
		"group by 1 order by 2 desc limit %(limit)s",
		extra_params={"limit": n + 5},
	)
	po_status = po.query(
		"h.status as label, count(distinct h.name) as count, sum(i.base_net_amount) as value",
		"group by h.status order by count desc",
		extra_where="and h.status != 'Cancelled'",
	)
	pending_po = po.query(
		"h.name, h.supplier, h.supplier_name, h.schedule_date, "
		"sum((i.qty - i.received_qty) * i.base_net_rate) as pending_value, sum(i.qty - i.received_qty) as pending_qty, "
		"datediff(%(today)s, h.schedule_date) as days_late",
		"group by h.name, h.supplier, h.supplier_name, h.schedule_date having pending_qty > 0 "
		"order by h.schedule_date limit %(limit)s",
		extra_where="and h.status not in ('Closed','Completed','Cancelled','Draft','On Hold')",
		extra_params={"today": f.today, "limit": 100},
	)
	pr_monthly = pr.query(
		"date_format(h.posting_date,'%%Y-%%m') as month, sum(i.base_net_amount) as value, count(distinct h.name) as count",
		"group by 1",
		extra_where="and h.is_return = 0",
	)
	pr_status = pr.query(
		"h.status as label, count(distinct h.name) as count, sum(i.base_net_amount) as value", "group by h.status order by count desc"
	)
	# goods received but not billed: received value not yet invoiced (per receipt item billed amount)
	grni = pr.query(
		"h.name, h.supplier, h.supplier_name, h.posting_date, "
		"sum(i.base_net_amount - least(i.billed_amt, i.amount) * ifnull(h.conversion_rate,1)) as unbilled",
		"group by h.name, h.supplier, h.supplier_name, h.posting_date having unbilled > 0.005 order by unbilled desc limit %(limit)s",
		extra_where="and h.is_return = 0 and h.status != 'Cancelled' and h.per_billed < 100",
		extra_params={"limit": 100},
	)
	pi_status = pi.query(
		"h.status as label, count(distinct h.name) as count, sum(i.base_net_amount) as value", "group by h.status order by count desc"
	)
	returns = pi.query(
		"date_format(h.posting_date,'%%Y-%%m') as month, sum(i.base_net_amount) as value, count(distinct h.name) as count",
		"group by 1",
		extra_where="and h.is_return = 1",
	)
	ret_sup = pi.query(
		"h.supplier, h.supplier_name, sum(i.base_net_amount) as value, count(distinct h.name) as count",
		"group by h.supplier, h.supplier_name order by value limit %(limit)s",
		extra_where="and h.is_return = 1",
		extra_params={"limit": n},
	)

	cur, prev = purchase_totals(f), purchase_totals(f, previous=True)
	s_cur = sales_totals(f)
	sales_monthly = {
		r.month: flt(r.value)
		for r in sales_invoice_scope(f).query(
			"date_format(h.posting_date,'%%Y-%%m') as month, sum(i.base_net_amount) as value", "group by 1"
		)
	}
	purchase_monthly = {r.month: flt(r.value) for r in monthly}
	drill = {"posting_date": ["Between", [str(f.from_date), str(f.to_date)]], "docstatus": 1, "company": f.company}
	return {
		"kpis": {
			"net_purchases": {"value": cur.net_purchases, "previous": prev.net_purchases, "growth": growth(cur.net_purchases, prev.net_purchases)},
			"invoices": {"value": cur.invoices, "previous": prev.invoices, "growth": growth(cur.invoices, prev.invoices)},
			"orders": {"value": cur.orders, "previous": prev.orders, "growth": growth(cur.orders, prev.orders)},
			"returns": {"value": cur.returns_amount, "previous": prev.returns_amount, "growth": growth(cur.returns_amount, prev.returns_amount)},
		},
		"monthly": series_by_month([{"month": r.month, "value": r.value} for r in monthly], months),
		"by_supplier": [{"label": r.supplier_name or r.supplier, "name": r.supplier, "value": round(flt(r.value), 2)} for r in by_supplier],
		"top_suppliers": [{"label": r.supplier_name or r.supplier, "name": r.supplier, "value": round(flt(r.value), 2)} for r in by_supplier[:n]],
		"by_item_group": _label_rows(by_group),
		"po_status": _label_rows(po_status),
		"pending_po": [
			{
				"name": r.name,
				"supplier": r.supplier_name or r.supplier,
				"schedule_date": str(r.schedule_date) if r.schedule_date else None,
				"pending_qty": round(flt(r.pending_qty), 2),
				"pending_value": round(flt(r.pending_value), 2),
				"days_late": max(int(r.days_late or 0), 0),
			}
			for r in pending_po
		],
		"pending_po_total": round(sum(flt(r.pending_value) for r in pending_po), 2),
		"receipts": {
			"monthly": series_by_month([{"month": r.month, "value": r.value} for r in pr_monthly], months),
			"status": _label_rows(pr_status),
			"count": sum(r.count for r in pr_monthly),
			"value": round(sum(flt(r.value) for r in pr_monthly), 2),
		},
		"grni": {
			"total": round(sum(flt(r.unbilled) for r in grni), 2),
			"rows": [
				{"name": r.name, "supplier": r.supplier_name or r.supplier, "posting_date": str(r.posting_date), "unbilled": round(flt(r.unbilled), 2)}
				for r in grni
			],
		},
		"pi_status": _label_rows(pi_status),
		"returns": {
			"monthly": series_by_month([{"month": r.month, "value": abs(flt(r.value))} for r in returns], months),
			"count": sum(r.count for r in returns),
			"amount": round(abs(sum(flt(r.value) for r in returns)), 2),
			"by_supplier": [{"label": r.supplier_name or r.supplier, "value": round(abs(flt(r.value)), 2), "count": r.count} for r in ret_sup],
		},
		"sales_vs_purchase": {
			"labels": series_by_month([], months)["labels"],
			"sales": [round(sales_monthly.get(m, 0.0), 2) for m in months],
			"purchases": [round(purchase_monthly.get(m, 0.0), 2) for m in months],
			"total_sales": round(s_cur.net_sales, 2),
			"total_purchases": round(cur.net_purchases, 2),
		},
		"routes": {
			"invoices": list_route("Purchase Invoice", {**drill, "is_return": 0}),
			"orders": list_route("Purchase Order", {"transaction_date": drill["posting_date"], "docstatus": 1, "company": f.company}),
			"returns": list_route("Purchase Invoice", {**drill, "is_return": 1}),
			"receipts": list_route("Purchase Receipt", {**drill}),
			"grni": list_route("Purchase Receipt", {"status": "To Bill", "company": f.company, "docstatus": 1}),
			"pending_po": list_route("Purchase Order", {"status": ["in", ["To Receive and Bill", "To Receive"]], "company": f.company, "docstatus": 1}),
		},
	}
