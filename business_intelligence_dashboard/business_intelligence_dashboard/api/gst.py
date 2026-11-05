"""GST analytics from actual accounting entries on the GST accounts.

The tax accounts are discovered from *GST Settings > GST Accounts* (India Compliance) for
the selected company.  If none are configured the dashboard falls back to Tax accounts
whose names mention CGST / SGST / IGST / Cess (liability = output, asset = input) and says so.
Because GL Entries are used, credit notes and purchase returns reduce the figures
automatically.  Journal / Payment Entries (GST settlement, set-off) are shown separately
from document driven tax so that "collected" and "paid" are not distorted.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt

from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	cached,
	gl_conditions,
	locked,
	month_label,
	months_between,
	report_route,
)

COMPONENTS = (("cgst_account", "CGST"), ("sgst_account", "SGST"), ("igst_account", "IGST"), ("cess_account", "Cess"), ("cess_non_advol_account", "Cess"))
DIRECTION = {"Output": "output", "Input": "input", "Sales Reverse Charge": "rcm_output", "Purchase Reverse Charge": "rcm_input"}
SETTLEMENT_VOUCHERS = ("Journal Entry", "Payment Entry")


def gst_accounts(company):
	"""({account: (direction, component)}, source note)"""
	mapping = {}
	if frappe.db.exists("DocType", "GST Account"):
		rows = frappe.get_all(
			"GST Account",
			filters={"parent": "GST Settings", "parenttype": "GST Settings", "company": company},
			fields=["account_type", *[c for c, _l in COMPONENTS]],
		)
		for r in rows:
			direction = DIRECTION.get(r.account_type)
			if not direction:
				continue
			for field, label in COMPONENTS:
				if r.get(field):
					mapping[r[field]] = (direction, label)
	if mapping:
		return mapping, None
	rows = frappe.get_all(
		"Account",
		filters={"company": company, "account_type": "Tax", "is_group": 0},
		fields=["name", "root_type"],
	)
	for r in rows:
		m = re.search(r"\b(cgst|sgst|igst|cess)\b", r.name, re.I)
		if m:
			label = {"cgst": "CGST", "sgst": "SGST", "igst": "IGST", "cess": "Cess"}[m.group(1).lower()]
			mapping[r.name] = ("output" if r.root_type == "Liability" else "input", label)
	note = _("GST accounts are not configured in GST Settings for this company; Tax accounts were matched by name.") if mapping else _(
		"No GST accounts were found for this company."
	)
	return mapping, note


def _movements(f, accounts, start=None, end=None):
	"""Per account and voucher class: debit/credit within [start, end]."""
	cond, params = gl_conditions(f, with_dates=False)
	params.update({"start": start or f.from_date, "end": end or f.to_date, "accounts": tuple(accounts) or ("",)})
	return frappe.db.sql(
		f"""select gle.account, date_format(gle.posting_date,'%%Y-%%m') as month,
			(gle.voucher_type in %(settle)s) as settlement, sum(gle.debit) as debit, sum(gle.credit) as credit
		from `tabGL Entry` gle
		where {cond} and gle.account in %(accounts)s and gle.posting_date between %(start)s and %(end)s
		group by gle.account, month, settlement""",
		{**params, "settle": SETTLEMENT_VOUCHERS},
		as_dict=True,
	)


@frappe.whitelist()
@cached
def get_gst(f):
	if not frappe.has_permission("GL Entry", "read"):
		return locked(["GL Entry"])
	mapping, note = gst_accounts(f.company)
	if not mapping:
		return {"available": False, "note": note}
	months = months_between(f.from_date, f.to_date)
	rows = _movements(f, mapping.keys())

	zero = lambda: {"debit": 0.0, "credit": 0.0}  # noqa: E731
	direction_totals = {d: zero() for d in ("output", "input", "rcm_output", "rcm_input")}
	component = {}
	per_account = {}
	settle = {"output": 0.0, "input": 0.0}
	monthly = {m: {"output": 0.0, "input": 0.0} for m in months}
	for r in rows:
		direction, comp = mapping[r.account]
		deb, cre = flt(r.debit), flt(r.credit)
		acc = per_account.setdefault(r.account, {"direction": direction, "component": comp, "debit": 0.0, "credit": 0.0})
		acc["debit"] += deb
		acc["credit"] += cre
		if r.settlement:
			if direction in ("output", "rcm_output"):
				settle["output"] += cre - deb
			else:
				settle["input"] += deb - cre
			continue
		direction_totals[direction]["debit"] += deb
		direction_totals[direction]["credit"] += cre
		c = component.setdefault(comp, {"output": 0.0, "input": 0.0})
		if direction == "output":
			c["output"] += cre - deb
			monthly.get(r.month, {"output": 0})["output"] += cre - deb
		elif direction == "input":
			c["input"] += deb - cre
			monthly.get(r.month, {"input": 0})["input"] += deb - cre

	output = direction_totals["output"]
	inp = direction_totals["input"]
	output_net = output["credit"] - output["debit"]
	input_net = inp["debit"] - inp["credit"]
	rcm_liability = direction_totals["rcm_output"]["credit"] - direction_totals["rcm_output"]["debit"]
	rcm_itc = direction_totals["rcm_input"]["debit"] - direction_totals["rcm_input"]["credit"]
	net_liability = output_net - input_net + rcm_liability - rcm_itc

	# ledger balance as of the end date (what is actually still payable)
	cond, params = gl_conditions(f, with_dates=False)
	bal = frappe.db.sql(
		f"""select gle.account, sum(gle.credit - gle.debit) as net from `tabGL Entry` gle
		where {cond} and gle.account in %(accounts)s and gle.posting_date <= %(end)s group by gle.account""",
		{**params, "accounts": tuple(mapping), "end": f.to_date},
		as_dict=True,
	)
	closing = {r.account: flt(r.net) for r in bal}
	payable = sum(v if mapping[a][0] in ("output", "rcm_output") else -v for a, v in closing.items())

	def comp_row(name):
		c = component.get(name, {"output": 0.0, "input": 0.0})
		return {"label": name, "output": round(c["output"], 2), "input": round(c["input"], 2), "net": round(c["output"] - c["input"], 2)}

	return {
		"available": True,
		"note": note,
		"summary": {
			"output_gst": round(output_net, 2),
			"input_gst": round(input_net, 2),
			"net_liability": round(net_liability, 2),
			"gst_collected": round(output["credit"], 2),
			"credit_note_reversal": round(output["debit"], 2),
			"gst_paid": round(inp["debit"], 2),
			"purchase_return_reversal": round(inp["credit"], 2),
			"rcm_liability": round(rcm_liability, 2),
			"rcm_itc": round(rcm_itc, 2),
			"settled_via_journal_output": round(settle["output"], 2),
			"settled_via_journal_input": round(settle["input"], 2),
			"gst_payable_ledger": round(payable, 2),
			"is_refundable": net_liability < 0,
		},
		"components": [comp_row(c) for c in ("CGST", "SGST", "IGST", "Cess") if c in component],
		"monthly": {
			"labels": [month_label(m) for m in months],
			"output": [round(monthly[m]["output"], 2) for m in months],
			"input": [round(monthly[m]["input"], 2) for m in months],
			"net": [round(monthly[m]["output"] - monthly[m]["input"], 2) for m in months],
		},
		"accounts": sorted(
			(
				{
					"account": a,
					"direction": v["direction"],
					"component": v["component"],
					"debit": round(v["debit"], 2),
					"credit": round(v["credit"], 2),
					"closing_balance": round(closing.get(a, 0.0), 2),
				}
				for a, v in per_account.items()
			),
			key=lambda r: (r["direction"], r["component"]),
		),
		"routes": {
			"ledger": report_route("General Ledger", {"company": f.company, "from_date": str(f.from_date), "to_date": str(f.to_date), "account": list(mapping)}),
			"gstr": report_route("GST Sales Register", {"company": f.company, "from_date": str(f.from_date), "to_date": str(f.to_date)})
			if frappe.db.exists("Report", "GST Sales Register")
			else None,
		},
	}
