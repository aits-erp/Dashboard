"""Payables - built on ERPNext's *Accounts Payable* report engine (see receivables.py)."""

import frappe
from frappe import _

from business_intelligence_dashboard.business_intelligence_dashboard.api.receivables import (
	run_ageing_report,
	summarise,
)
from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	cached,
	list_route,
	locked,
	report_route,
)


@frappe.whitelist()
@cached
def get_payables(f):
	if not (frappe.has_permission("Purchase Invoice", "read") and frappe.has_permission("Payment Ledger Entry", "read")):
		return locked(["Purchase Invoice", "Payment Ledger Entry"])
	out = summarise(f, run_ageing_report(f, "Supplier"), "suppliers")
	out["routes"] = {
		"outstanding": report_route("Accounts Payable", {"company": f.company, "report_date": str(f.to_date), "ageing_based_on": "Due Date"}),
		"overdue": list_route("Purchase Invoice", {"company": f.company, "docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", str(f.to_date)]}),
	}
	return out
