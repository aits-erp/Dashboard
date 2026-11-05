"""Receivables - built on ERPNext's own *Accounts Receivable* report engine.

The engine reads the Payment Ledger, so payment allocations, credit notes, returns and
unallocated advances are all reflected in each invoice's outstanding amount.  Ageing
uses the report defaults (Due Date basis, ranges 30/60/90/120) evaluated at the
selected "To Date"; as in the standard report the 0-30 bucket also contains
invoices that are not yet due, which are additionally reported on their own.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

from business_intelligence_dashboard.business_intelligence_dashboard.api.sales import sales_totals
from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	cached,
	list_route,
	locked,
	month_label,
	months_between,
	report_route,
	request_memo,
	top_n,
)

BUCKETS = ["0-30", "31-60", "61-90", "90+"]


def run_ageing_report(f, party_type):
	"""Run the standard receivable / payable ageing report and return its rows (memoised per request)."""
	store = request_memo()
	key = ("ageing", party_type, f.company, str(f.to_date), str(f.customers), str(f.suppliers), str(f.cost_centers), f.sales_person, f.territory)
	if key not in store:
		store[key] = _run_ageing_report(f, party_type)
	return store[key]


def _run_ageing_report(f, party_type):
	if party_type == "Customer":
		from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute
	else:
		from erpnext.accounts.report.accounts_payable.accounts_payable import execute

	filters = frappe._dict(
		company=f.company,
		report_date=f.to_date,
		ageing_based_on="Due Date",
		calculate_ageing_with="Report Date",
		range="30, 60, 90, 120",
		party_type=party_type,
	)
	parties = f.customers if party_type == "Customer" else f.suppliers
	if parties is not None:
		filters["party"] = list(parties)
	if f.cost_centers is not None:
		filters["cost_center"] = list(f.cost_centers)
	if party_type == "Customer":
		if f.sales_person:
			filters["sales_person"] = f.sales_person
		if f.territory:
			filters["territory"] = f.territory
	data = execute(filters)[1]
	return [r for r in data if r.get("party")]


def outstanding_total(f, party_type, date):
	"""Total outstanding as on ``date``.

	Uses the Payment Ledger directly (the same table the ageing report reads - the
	reconciliation check proves they agree) so KPI cards stay fast; the territory /
	sales-person filters need invoice data, so those fall back to the full report.
	"""
	if f.territory or f.sales_person:
		scoped = frappe._dict(f)
		scoped.to_date = date
		return sum(flt(r.get("outstanding")) for r in run_ageing_report(scoped, party_type))
	parties = f.customers if party_type == "Customer" else f.suppliers
	cond, params = "", {}
	if parties is not None:
		cond += " and ple.party in %(parties)s"
		params["parties"] = tuple(parties) or ("",)
	if f.cost_centers is not None:
		cond += " and ple.cost_center in %(cost_centers)s"
		params["cost_centers"] = tuple(f.cost_centers) or ("",)
	row = frappe.db.sql(
		f"""select ifnull(sum(ple.amount), 0) from `tabPayment Ledger Entry` ple
		where ple.delinked = 0 and ple.company = %(company)s and ple.party_type = %(party_type)s
		and ple.account_type = %(account_type)s and ple.posting_date <= %(date)s {cond}""",
		{
			"company": f.company,
			"party_type": party_type,
			"account_type": "Receivable" if party_type == "Customer" else "Payable",
			"date": date,
			**params,
		},
	)
	return flt(row[0][0])


def _due(row, report_date):
	d = row.get("due_date") or row.get("posting_date")
	return getdate(d) if d else getdate(report_date)


def summarise(f, rows, label):
	"""Totals, ageing, party split and due-date schedule from ageing report rows."""
	report_date = getdate(f.to_date)
	total = not_due = 0.0
	age = dict.fromkeys(BUCKETS, 0.0)
	parties, schedule = {}, {"due_0_7": 0.0, "due_8_15": 0.0, "due_16_30": 0.0, "due_31_60": 0.0}
	overdue_rows, upcoming = [], []
	for r in rows:
		out = flt(r.get("outstanding"))
		total += out
		age["0-30"] += flt(r.get("range1"))
		age["31-60"] += flt(r.get("range2"))
		age["61-90"] += flt(r.get("range3"))
		age["90+"] += flt(r.get("range4")) + flt(r.get("range5"))
		party = r.get("party")
		parties[party] = parties.get(party, 0.0) + out
		due = _due(r, report_date)
		days_to_due = date_diff(due, report_date)
		if days_to_due > 0:
			not_due += out
			bucket = (
				"due_0_7" if days_to_due <= 7 else "due_8_15" if days_to_due <= 15 else "due_16_30" if days_to_due <= 30 else "due_31_60" if days_to_due <= 60 else None
			)
			if bucket:
				schedule[bucket] += out
			if out > 0:
				upcoming.append(_voucher(r, due, days_to_due))
		elif out > 0 and r.get("voucher_no"):
			overdue_rows.append(_voucher(r, due, days_to_due))
	overdue = total - not_due
	n = top_n()
	party_rows = sorted(
		({"party": p, "outstanding": round(v, 2)} for p, v in parties.items() if abs(v) > 0.005),
		key=lambda x: -x["outstanding"],
	)
	return {
		"total_outstanding": round(total, 2),
		"not_due": round(not_due, 2),
		"overdue": round(overdue, 2),
		"overdue_percent": round(overdue / total * 100, 2) if total else 0.0,
		"ageing": {"labels": BUCKETS, "values": [round(age[b], 2) for b in BUCKETS]},
		"by_party": party_rows,
		"top_parties": party_rows[:n],
		"party_count": len(party_rows),
		"overdue_invoices": sorted(overdue_rows, key=lambda x: x["days"], reverse=True)[:100],
		"upcoming_invoices": sorted(upcoming, key=lambda x: x["due_date"])[:100],
		"schedule": {
			"labels": [_("Due in 0-7 days"), _("8-15 days"), _("16-30 days"), _("31-60 days")],
			"values": [round(schedule[k], 2) for k in ("due_0_7", "due_8_15", "due_16_30", "due_31_60")],
		},
		"label": label,
	}


def _voucher(r, due, days):
	return {
		"party": r.get("party_name") or r.get("party"),
		"voucher_type": r.get("voucher_type"),
		"voucher_no": r.get("voucher_no"),
		"due_date": str(due),
		"outstanding": round(flt(r.get("outstanding")), 2),
		"days": -days if days <= 0 else days,
	}


@frappe.whitelist()
@cached
def get_receivables(f):
	if not (frappe.has_permission("Sales Invoice", "read") and frappe.has_permission("Payment Ledger Entry", "read")):
		return locked(["Sales Invoice", "Payment Ledger Entry"])
	rows = run_ageing_report(f, "Customer")
	out = summarise(f, rows, "customers")

	# monthly collections: Payment Entries received from customers (bank-side, company currency)
	months = months_between(f.from_date, f.to_date)
	coll = frappe.db.sql(
		"""select date_format(pe.posting_date,'%%Y-%%m') as month, sum(pe.base_received_amount) as value
		from `tabPayment Entry` pe
		where pe.docstatus = 1 and pe.company = %(company)s and pe.payment_type = 'Receive' and pe.party_type = 'Customer'
		and pe.posting_date between %(from_date)s and %(to_date)s
		{party}
		group by 1""".format(party="and pe.party in %(parties)s" if f.customers is not None else ""),
		{"company": f.company, "from_date": f.from_date, "to_date": f.to_date, "parties": tuple(f.customers or ()) or ("",)},
		as_dict=True,
	)
	lookup = {r.month: flt(r.value) for r in coll}
	days = date_diff(f.to_date, f.from_date) + 1
	credit_sales = sales_totals(f).gross_sales
	out["collection_trend"] = {
		"labels": [month_label(m) for m in months],
		"values": [round(lookup.get(m, 0.0), 2) for m in months],
		"total": round(sum(lookup.values()), 2),
	}
	out["average_collection_period"] = {
		"days": round(max(out["total_outstanding"], 0) / credit_sales * days, 1) if credit_sales else None,
		"basis": _("Outstanding receivables / invoiced sales x days in period"),
	}
	out["routes"] = {
		"outstanding": report_route("Accounts Receivable", {"company": f.company, "report_date": str(f.to_date), "ageing_based_on": "Due Date"}),
		"overdue": list_route("Sales Invoice", {"company": f.company, "docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", str(f.to_date)]}),
	}
	return out
