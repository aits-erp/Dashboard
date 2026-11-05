"""Inventory analytics.

Stock quantity and value are derived from the Stock Ledger Entry (non-cancelled
entries, ``actual_qty`` and ``stock_value_difference``) exactly as ERPNext's *Stock
Balance* report does, so values follow the item's valuation method.  Stock ageing
reuses the standard *Stock Ageing* report (FIFO slots).
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt

from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	cached,
	get_settings,
	list_route,
	locked,
	month_label,
	months_between,
	report_route,
	top_n,
)


def _sle_conditions(f, alias="sle", with_item_join=False):
	conds = [f"{alias}.company = %(company)s", f"{alias}.is_cancelled = 0"]
	params = {"company": f.company}
	if f.warehouses is not None:
		conds.append(f"{alias}.warehouse in %(warehouses)s")
		params["warehouses"] = tuple(f.warehouses) or ("",)
	if f.item_groups is not None:
		conds.append("it.item_group in %(item_groups)s")
		params["item_groups"] = tuple(f.item_groups) or ("",)
	return " and ".join(conds), params


def stock_balances(f, date):
	"""[{item_code, warehouse, qty, value}] as of ``date`` from the Stock Ledger."""
	cond, params = _sle_conditions(f)
	params["date"] = date
	return frappe.db.sql(
		f"""select sle.item_code, sle.warehouse, sum(sle.actual_qty) as qty, sum(sle.stock_value_difference) as value
		from `tabStock Ledger Entry` sle join `tabItem` it on it.name = sle.item_code
		where {cond} and sle.posting_date <= %(date)s
		group by sle.item_code, sle.warehouse
		having abs(sum(sle.actual_qty)) > 0.0000001 or abs(sum(sle.stock_value_difference)) > 0.005""",
		params,
		as_dict=True,
	)


def stock_totals(f, date):
	rows = stock_balances(f, date)
	return sum(flt(r.value) for r in rows), sum(flt(r.qty) for r in rows)


def _item_info(codes):
	if not codes:
		return {}
	rows = frappe.get_all(
		"Item", filters={"name": ["in", list(codes)]}, fields=["name", "item_name", "item_group", "stock_uom", "safety_stock"]
	)
	return {r.name: r for r in rows}


@frappe.whitelist()
@cached
def get_inventory(f):
	if not (frappe.has_permission("Stock Ledger Entry", "read") and frappe.has_permission("Item", "read")):
		return locked(["Stock Ledger Entry", "Item"])
	settings = get_settings()
	n = top_n()
	balances = stock_balances(f, f.to_date)
	positive = [r for r in balances if flt(r.qty) > 0.0000001]
	total_value = sum(flt(r.value) for r in balances)
	total_qty = sum(flt(r.qty) for r in balances)
	p_value, p_qty = stock_totals(f, f.prev_to)

	# ---- warehouse wise
	wh = {}
	for r in balances:
		d = wh.setdefault(r.warehouse, {"qty": 0.0, "value": 0.0, "items": 0})
		d["qty"] += flt(r.qty)
		d["value"] += flt(r.value)
		d["items"] += 1
	warehouses = sorted(
		({"warehouse": k, "qty": round(v["qty"], 3), "value": round(v["value"], 2), "items": v["items"]} for k, v in wh.items()),
		key=lambda x: -x["value"],
	)

	# ---- item wise
	items = {}
	for r in balances:
		d = items.setdefault(r.item_code, {"qty": 0.0, "value": 0.0})
		d["qty"] += flt(r.qty)
		d["value"] += flt(r.value)
	info = _item_info(items.keys())
	top_value = sorted(items.items(), key=lambda kv: -kv[1]["value"])[:n]

	# ---- negative stock (item x warehouse)
	negative = sorted((r for r in balances if flt(r.qty) < -0.0000001), key=lambda r: flt(r.qty))
	neg_info = _item_info({r.item_code for r in negative})

	# ---- movement analysis over the look-back window
	window = int(settings.non_moving_days)
	start = add_days(f.to_date, -window)
	cond, params = _sle_conditions(f)
	moves = frappe.db.sql(
		f"""select sle.item_code, count(*) as txns, sum(-sle.actual_qty) as qty_out, sum(-sle.stock_value_difference) as value_out
		from `tabStock Ledger Entry` sle join `tabItem` it on it.name = sle.item_code
		where {cond} and sle.actual_qty < 0 and sle.voucher_type != 'Stock Reconciliation'
		and sle.posting_date between %(start)s and %(end)s
		group by sle.item_code""",
		{**params, "start": start, "end": f.to_date},
		as_dict=True,
	)
	moved = {r.item_code: r for r in moves}
	in_stock = {k: v for k, v in items.items() if v["qty"] > 0.0000001}
	non_moving = [k for k in in_stock if k not in moved]
	slow = [k for k in in_stock if k in moved and moved[k].txns <= int(settings.slow_moving_orders)]
	fast = sorted((k for k in in_stock if k in moved), key=lambda k: -flt(moved[k].qty_out))[:n]
	mover_info = _item_info(set(non_moving[:300]) | set(slow[:300]) | set(fast))

	def mover_row(code, with_moves=True):
		i, s, m = mover_info.get(code), in_stock[code], moved.get(code)
		return {
			"item_code": code,
			"item_name": i.item_name if i else code,
			"qty": round(s["qty"], 3),
			"value": round(s["value"], 2),
			"qty_out": round(flt(m.qty_out), 3) if m else 0,
			"transactions": m.txns if m else 0,
		}

	non_moving_rows = sorted((mover_row(k) for k in non_moving), key=lambda r: -r["value"])
	slow_rows = sorted((mover_row(k) for k in slow), key=lambda r: -r["value"])

	# ---- low stock vs safety stock (across the filtered warehouses)
	low = []
	safety = frappe.get_all(
		"Item", filters={"disabled": 0, "is_stock_item": 1, "safety_stock": [">", 0]}, fields=["name", "item_name", "safety_stock"]
	)
	for it in safety:
		qty = items.get(it.name, {}).get("qty", 0.0)
		if qty < flt(it.safety_stock):
			low.append({"item_code": it.name, "item_name": it.item_name, "qty": round(qty, 3), "safety_stock": flt(it.safety_stock), "shortfall": round(flt(it.safety_stock) - qty, 3)})
	low.sort(key=lambda r: -r["shortfall"])

	# ---- reorder alerts (Item Reorder levels vs projected qty)
	wh_cond, wh_params = "", {}
	if f.warehouses is not None:
		wh_cond, wh_params = "and ir.warehouse in %(warehouses)s", {"warehouses": tuple(f.warehouses) or ("",)}
	reorder = frappe.db.sql(
		f"""select ir.parent as item_code, it.item_name, ir.warehouse, ir.warehouse_reorder_level as level,
			ir.warehouse_reorder_qty as reorder_qty, ifnull(b.actual_qty,0) as actual_qty, ifnull(b.projected_qty,0) as projected_qty
		from `tabItem Reorder` ir join `tabItem` it on it.name = ir.parent
		left join `tabBin` b on b.item_code = ir.parent and b.warehouse = ir.warehouse
		where it.disabled = 0 and ifnull(b.projected_qty,0) < ir.warehouse_reorder_level {wh_cond}
		order by (ir.warehouse_reorder_level - ifnull(b.projected_qty,0)) desc limit 200""",
		wh_params,
		as_dict=True,
	)

	# ---- valuation trend: opening + month-wise movement
	months = months_between(f.from_date, f.to_date)
	cond, params = _sle_conditions(f)
	opening_value = frappe.db.sql(
		f"""select ifnull(sum(sle.stock_value_difference),0) from `tabStock Ledger Entry` sle join `tabItem` it on it.name = sle.item_code
		where {cond} and sle.posting_date < %(start)s""",
		{**params, "start": f.from_date},
	)[0][0]
	monthly = frappe.db.sql(
		f"""select date_format(sle.posting_date,'%%Y-%%m') as month, sum(sle.stock_value_difference) as value
		from `tabStock Ledger Entry` sle join `tabItem` it on it.name = sle.item_code
		where {cond} and sle.posting_date between %(start)s and %(end)s group by 1""",
		{**params, "start": f.from_date, "end": f.to_date},
		as_dict=True,
	)
	mv = {r.month: flt(r.value) for r in monthly}
	running, trend = flt(opening_value), []
	for m in months:
		running += mv.get(m, 0.0)
		trend.append(round(running, 2))

	# ---- in transit
	transit_wh = set(frappe.get_all("Warehouse", filters={"company": f.company, "warehouse_type": "Transit"}, pluck="name"))
	transit_value = sum(flt(r.value) for r in balances if r.warehouse in transit_wh)
	pending_transfers = frappe.db.sql(
		"""select count(*) as count, ifnull(sum(total_outgoing_value),0) as value from `tabStock Entry`
		where docstatus = 1 and company = %(company)s and add_to_transit = 1 and ifnull(per_transferred,0) < 100""",
		{"company": f.company},
		as_dict=True,
	)[0]

	return {
		"summary": {
			"stock_value": round(total_value, 2),
			"stock_qty": round(total_qty, 3),
			"previous_value": round(p_value, 2),
			"previous_qty": round(p_qty, 3),
			"item_count": len(items),
			"warehouse_count": len(wh),
		},
		"warehouses": warehouses,
		"top_value_items": [
			{
				"item_code": k,
				"item_name": info.get(k).item_name if info.get(k) else k,
				"qty": round(v["qty"], 3),
				"value": round(v["value"], 2),
			}
			for k, v in top_value
		],
		"fast_moving": [mover_row(k) for k in fast],
		"slow_moving": slow_rows[:50],
		"non_moving": non_moving_rows[:50],
		"movement_counts": {
			"window_days": window,
			"fast": len(fast),
			"slow": len(slow),
			"non_moving": len(non_moving),
			"non_moving_value": round(sum(r["value"] for r in non_moving_rows), 2),
			"slow_value": round(sum(r["value"] for r in slow_rows), 2),
		},
		"negative_stock": [
			{
				"item_code": r.item_code,
				"item_name": neg_info.get(r.item_code).item_name if neg_info.get(r.item_code) else r.item_code,
				"warehouse": r.warehouse,
				"qty": round(flt(r.qty), 3),
				"value": round(flt(r.value), 2),
			}
			for r in negative[:100]
		],
		"negative_count": len(negative),
		"low_stock": low[:100],
		"low_stock_count": len(low),
		"reorder_alerts": [
			{
				"item_code": r.item_code,
				"item_name": r.item_name,
				"warehouse": r.warehouse,
				"reorder_level": flt(r.level),
				"reorder_qty": flt(r.reorder_qty),
				"actual_qty": flt(r.actual_qty),
				"projected_qty": flt(r.projected_qty),
			}
			for r in reorder
		],
		"reorder_count": len(reorder),
		"valuation_trend": {"labels": [month_label(m) for m in months], "values": trend},
		"ageing": _stock_ageing(f),
		"in_transit": {
			"warehouse_value": round(transit_value, 2),
			"pending_transfers": pending_transfers.count,
			"pending_transfer_value": round(flt(pending_transfers.value), 2),
		},
		"routes": {
			"stock_balance": report_route("Stock Balance", {"company": f.company, "to_date": str(f.to_date), "from_date": str(f.from_date)}),
			"negative": report_route("Stock Balance", {"company": f.company, "to_date": str(f.to_date), "from_date": str(f.from_date), "show_negative": 1}),
			"bin": list_route("Bin", {"actual_qty": ["<", 0]}),
			"ageing": report_route("Stock Ageing", {"company": f.company, "to_date": str(f.to_date)}),
			"projected": report_route("Stock Projected Qty", {"company": f.company}),
		},
	}


def _stock_ageing(f):
	"""Bucket stock using the standard FIFO based Stock Ageing report."""
	try:
		from erpnext.stock.report.stock_ageing.stock_ageing import execute

		# the report concatenates strings onto to_date, so it must be an ISO string, not a date
		filters = frappe._dict(company=f.company, to_date=str(f.to_date), range="30, 60, 90")
		if f.warehouse:
			filters.warehouse = f.warehouse
		if f.item_group:
			filters.item_group = f.item_group
		columns, data = execute(filters)[:2]
		# rows come back as lists in column order: map the range columns by fieldname
		index = {c["fieldname"]: i for i, c in enumerate(columns)}
	except Exception:
		frappe.clear_last_message()
		frappe.log_error(title="BI Dashboard: stock ageing failed")
		return {"available": False, "note": _("Stock ageing could not be computed.")}
	qty = [0.0] * 4
	val = [0.0] * 4
	for r in data:
		get = (lambda k: r.get(k)) if isinstance(r, dict) else (lambda k: r[index[k]] if k in index else 0)
		for i in range(4):
			qty[i] += flt(get(f"range{i + 1}"))
			val[i] += flt(get(f"range{i + 1}value"))
	return {
		"available": True,
		"labels": ["0-30", "31-60", "61-90", "90+"],
		"qty": [round(x, 3) for x in qty],
		"value": [round(x, 2) for x in val],
		"total_value": round(sum(val), 2),
	}
