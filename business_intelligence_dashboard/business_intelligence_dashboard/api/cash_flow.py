"""Cash flow and banking.

The General Ledger is the single source of truth: Payment Entries, Journal Entries,
POS / invoice payments and so on all post GL Entries on Cash / Bank accounts, so reading
only those entries cannot double count a payment that exists in both documents.
Flows are netted *per voucher*, therefore a transfer between two cash/bank accounts
(Internal Transfer, contra entry) nets to zero and is not reported as inflow + outflow.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt

from business_intelligence_dashboard.business_intelligence_dashboard.api.receivables import (
	run_ageing_report,
	summarise,
)
from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	cached,
	growth,
	list_route,
	locked,
	month_label,
	months_between,
	report_route,
)


def cash_bank_accounts(company):
	return frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "account_type": ["in", ["Cash", "Bank"]]},
		fields=["name", "account_name", "account_type", "account_currency"],
		order_by="account_type, name",
	)


def balances_as_of(company, accounts, date):
	"""{account: debit - credit} up to and including ``date`` (non-cancelled GL Entries)."""
	if not accounts:
		return {}
	rows = frappe.db.sql(
		"""select account, sum(debit - credit) as balance from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and account in %(accounts)s and posting_date <= %(date)s
		group by account""",
		{"company": company, "accounts": tuple(a.name for a in accounts), "date": date},
		as_dict=True,
	)
	return {r.account: flt(r.balance) for r in rows}


def cash_position(f, date):
	"""(cash, bank) totals as of ``date``."""
	accounts = cash_bank_accounts(f.company)
	bal = balances_as_of(f.company, accounts, date)
	cash = sum(bal.get(a.name, 0.0) for a in accounts if a.account_type == "Cash")
	bank = sum(bal.get(a.name, 0.0) for a in accounts if a.account_type == "Bank")
	return cash, bank


def cash_flows(f, start, end):
	"""(inflow, outflow, {month: (in, out)}) for [start, end], netted per voucher."""
	accounts = cash_bank_accounts(f.company)
	if not accounts:
		return 0.0, 0.0, {}
	rows = frappe.db.sql(
		"""select date_format(posting_date, '%%Y-%%m') as month, voucher_type, voucher_no, sum(debit - credit) as net
		from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and account in %(accounts)s
		and posting_date between %(start)s and %(end)s
		group by month, voucher_type, voucher_no""",
		{"company": f.company, "accounts": tuple(a.name for a in accounts), "start": start, "end": end},
		as_dict=True,
	)
	inflow = outflow = 0.0
	monthly = {}
	for r in rows:
		net = flt(r.net)
		if abs(net) < 0.005:
			continue
		m_in, m_out = monthly.get(r.month, (0.0, 0.0))
		if net > 0:
			inflow += net
			m_in += net
		else:
			outflow += -net
			m_out += -net
		monthly[r.month] = (m_in, m_out)
	return inflow, outflow, monthly


def cash_summary(f):
	"""Current and previous period cash numbers for the executive dashboard."""
	cash, bank = cash_position(f, f.to_date)
	p_cash, p_bank = cash_position(f, f.prev_to)
	inflow, outflow, _m = cash_flows(f, f.from_date, f.to_date)
	p_in, p_out, _pm = cash_flows(f, f.prev_from, f.prev_to)
	return frappe._dict(
		cash=cash, bank=bank, total=cash + bank, inflow=inflow, outflow=outflow, net=inflow - outflow,
		p_cash=p_cash, p_bank=p_bank, p_total=p_cash + p_bank, p_inflow=p_in, p_outflow=p_out, p_net=p_in - p_out,
	)


def _account_table(f):
	accounts = cash_bank_accounts(f.company)
	if not accounts:
		return []
	rows = frappe.db.sql(
		"""select account,
			sum(case when posting_date < %(start)s then debit - credit else 0 end) as opening,
			sum(case when posting_date between %(start)s and %(end)s then debit else 0 end) as inflow,
			sum(case when posting_date between %(start)s and %(end)s then credit else 0 end) as outflow,
			sum(debit - credit) as closing
		from `tabGL Entry`
		where company = %(company)s and is_cancelled = 0 and account in %(accounts)s and posting_date <= %(end)s
		group by account""",
		{"company": f.company, "accounts": tuple(a.name for a in accounts), "start": f.from_date, "end": f.to_date},
		as_dict=True,
	)
	by = {r.account: r for r in rows}
	out = []
	for a in accounts:
		r = by.get(a.name)
		if not r:
			continue
		out.append(
			{
				"account": a.name,
				"label": a.account_name,
				"type": a.account_type,
				"opening": round(flt(r.opening), 2),
				"debits": round(flt(r.inflow), 2),
				"credits": round(flt(r.outflow), 2),
				"closing": round(flt(r.closing), 2),
			}
		)
	return out


def _reconciliation(f):
	"""Per bank account: book balance vs. entries that have no clearance date yet."""
	banks = [a for a in cash_bank_accounts(f.company) if a.account_type == "Bank"]
	if not banks:
		return {"accounts": [], "transactions": None}
	rows = frappe.db.sql(
		"""select gle.account, count(*) as vouchers, sum(gle.debit) as deposits, sum(gle.credit) as withdrawals
		from `tabGL Entry` gle
		left join `tabPayment Entry` pe on gle.voucher_type = 'Payment Entry' and pe.name = gle.voucher_no
		left join `tabJournal Entry` je on gle.voucher_type = 'Journal Entry' and je.name = gle.voucher_no
		where gle.company = %(company)s and gle.is_cancelled = 0 and gle.account in %(accounts)s
		and gle.posting_date <= %(end)s
		and ((gle.voucher_type = 'Payment Entry' and pe.clearance_date is null)
			or (gle.voucher_type = 'Journal Entry' and je.clearance_date is null))
		group by gle.account""",
		{"company": f.company, "accounts": tuple(a.name for a in banks), "end": f.to_date},
		as_dict=True,
	)
	un = {r.account: r for r in rows}
	book = balances_as_of(f.company, banks, f.to_date)
	accounts = []
	for a in banks:
		r = un.get(a.name)
		deposits = flt(r.deposits) if r else 0.0
		withdrawals = flt(r.withdrawals) if r else 0.0
		accounts.append(
			{
				"account": a.name,
				"label": a.account_name,
				"book_balance": round(book.get(a.name, 0.0), 2),
				"uncleared_deposits": round(deposits, 2),
				"uncleared_withdrawals": round(withdrawals, 2),
				"uncleared_vouchers": r.vouchers if r else 0,
				# what the bank statement should show once uncleared items are accounted for
				"expected_bank_balance": round(book.get(a.name, 0.0) - deposits + withdrawals, 2),
			}
		)
	transactions = None
	if frappe.has_permission("Bank Transaction", "read"):
		bt = frappe.db.sql(
			"""select count(*) as count, ifnull(sum(unallocated_amount),0) as amount from `tabBank Transaction`
			where docstatus = 1 and company = %(company)s and status in ('Pending', 'Unreconciled')
			and date <= %(end)s""",
			{"company": f.company, "end": f.to_date},
			as_dict=True,
		)[0]
		transactions = {"count": bt.count, "amount": round(flt(bt.amount), 2)}
	return {"accounts": accounts, "transactions": transactions}


@frappe.whitelist()
@cached
def get_cash_flow(f):
	if not frappe.has_permission("GL Entry", "read"):
		return locked(["GL Entry"])
	s = cash_summary(f)
	inflow, outflow, monthly = cash_flows(f, f.from_date, f.to_date)
	months = months_between(f.from_date, f.to_date)
	opening_cash, opening_bank = cash_position(f, add_days(f.from_date, -1))
	opening = opening_cash + opening_bank

	m_in = [round(monthly.get(m, (0, 0))[0], 2) for m in months]
	m_out = [round(monthly.get(m, (0, 0))[1], 2) for m in months]
	running, cum = opening, []
	for a, b in zip(m_in, m_out):
		running += a - b
		cum.append(round(running, 2))

	accounts = _account_table(f)
	rec = _reconciliation(f)

	pending = frappe.db.sql(
		"""select name, payment_type, party_type, party, base_paid_amount as amount, posting_date
		from `tabPayment Entry` where docstatus = 0 and company = %(company)s order by posting_date desc limit 50""",
		{"company": f.company},
		as_dict=True,
	)
	pending_total = frappe.db.sql(
		"""select count(*) as count, ifnull(sum(base_paid_amount),0) as amount from `tabPayment Entry`
		where docstatus = 0 and company = %(company)s and payment_type = 'Pay'""",
		{"company": f.company},
		as_dict=True,
	)[0]

	obligations = {"payable": None, "receivable": None}
	if frappe.has_permission("Purchase Invoice", "read") and frappe.has_permission("Payment Ledger Entry", "read"):
		obligations["payable"] = summarise(f, run_ageing_report(f, "Supplier"), "suppliers")["schedule"]
	if frappe.has_permission("Sales Invoice", "read") and frappe.has_permission("Payment Ledger Entry", "read"):
		obligations["receivable"] = summarise(f, run_ageing_report(f, "Customer"), "customers")["schedule"]

	return {
		"summary": {
			"opening": round(opening, 2),
			"closing": round(s.total, 2),
			"inflow": round(inflow, 2),
			"outflow": round(outflow, 2),
			"net": round(inflow - outflow, 2),
			"check_difference": round(opening + inflow - outflow - s.total, 2),
			"cash": round(s.cash, 2),
			"bank": round(s.bank, 2),
			"growth": growth(s.total, s.p_total),
		},
		"monthly": {
			"labels": [month_label(m) for m in months],
			"inflow": m_in,
			"outflow": m_out,
			"net": [round(a - b, 2) for a, b in zip(m_in, m_out)],
			"closing": cum,
		},
		"accounts": accounts,
		"reconciliation": rec,
		"pending_payments": {
			"draft_pay_count": pending_total.count,
			"draft_pay_amount": round(flt(pending_total.amount), 2),
			"rows": [
				{"name": r.name, "payment_type": r.payment_type, "party": r.party, "amount": round(flt(r.amount), 2), "posting_date": str(r.posting_date)}
				for r in pending
			],
		},
		"obligations": obligations,
		"routes": {
			"accounts": report_route("General Ledger", {"company": f.company, "from_date": str(f.from_date), "to_date": str(f.to_date), "account": [a["account"] for a in accounts]}),
			"pending": list_route("Payment Entry", {"docstatus": 0, "company": f.company}),
			"bank": list_route("Bank Account", {"company": f.company}),
			"reconcile": {"type": "route", "route": ["bank-reconciliation-tool"]},
		},
	}
