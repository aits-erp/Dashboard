"""Tests for the Business Intelligence Dashboard.

They only *read* the site's data (run as Administrator) and assert invariants that must hold for
any company: validated inputs, parameterised filters, and the accounting identities the
dashboard relies on (balance sheet balances, ledger debit = credit, cash flow roll-forward,
dashboard figures = ERPNext's standard reports).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, getdate

from business_intelligence_dashboard.business_intelligence_dashboard.api import accounting, cash_flow
from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import (
	growth,
	month_label,
	months_between,
	parse_filters,
	series_by_month,
)

API = "business_intelligence_dashboard.business_intelligence_dashboard.api."


def has_ledger():
	return bool(frappe.db.count("GL Entry"))


class TestFilters(FrappeTestCase):
	def test_invalid_inputs_are_rejected(self):
		for bad in (
			{"from_date": "not-a-date"},
			{"from_date": "2026-05-01", "to_date": "2026-04-01"},
			{"customer": "x'; drop table tabUser;--"},
			{"company": "No Such Company"},
			"{not json",
			[1, 2],
		):
			with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
				parse_filters(bad)

	def test_defaults_and_previous_period(self):
		f = parse_filters({})
		self.assertTrue(f.company)
		self.assertLessEqual(f.from_date, f.to_date)
		self.assertLess(f.prev_to, f.from_date)
		self.assertLessEqual(f.prev_from, f.prev_to)

	def test_previous_period_is_equal_span_when_not_fiscal_year_start(self):
		f = parse_filters({"from_date": "2026-08-01", "to_date": "2026-08-31"})
		self.assertEqual(str(f.prev_from), "2026-07-01")
		self.assertEqual(str(f.prev_to), "2026-07-31")

	def test_helpers(self):
		self.assertIsNone(growth(10, 0))
		self.assertEqual(growth(150, 100), 50.0)
		self.assertEqual(growth(50, -100), 150.0)
		self.assertEqual(months_between("2026-04-15", "2026-06-02"), ["2026-04", "2026-05", "2026-06"])
		self.assertEqual(month_label("2026-04"), "Apr 2026")
		s = series_by_month([{"month": "2026-05", "value": 5}], ["2026-04", "2026-05"])
		self.assertEqual(s["values"], [0.0, 5.0])


class TestAccountingIdentities(FrappeTestCase):
	def setUp(self):
		if not has_ledger():
			self.skipTest("site has no ledger entries")
		frappe.set_user("Administrator")
		self.f = parse_filters({})

	def test_balance_sheet_balances(self):
		bs = accounting.balance_sheet(self.f, self.f.to_date)
		self.assertAlmostEqual(bs.total_assets, bs.total_liabilities + bs.equity, places=2)
		self.assertAlmostEqual(bs.current_assets + bs.fixed_assets, bs.total_assets, places=2)

	def test_profit_and_loss_adds_up(self):
		pl = accounting.profit_and_loss(self.f, self.f.from_date, self.f.to_date)
		self.assertAlmostEqual(pl.net_profit, pl.total_income - pl.total_expense, places=2)
		self.assertAlmostEqual(pl.gross_profit - pl.indirect_expense, pl.net_profit, places=2)
		self.assertAlmostEqual(sum(pl.net_m), pl.net_profit, places=2)

	def test_matches_standard_profit_and_loss_report(self):
		from erpnext.accounts.report.profit_and_loss_statement import profit_and_loss_statement as report

		pl = accounting.profit_and_loss(self.f, self.f.from_date, self.f.to_date)
		data = report.execute(accounting.fs_filters(self.f, self.f.from_date, self.f.to_date))[1]
		net = next((r for r in data if r and str(r.get("account", "")).strip("'") == "Profit for the year"), None)
		self.assertIsNotNone(net)
		self.assertAlmostEqual(pl.net_profit, flt(net["total"]), places=2)

	def test_ledger_balances(self):
		row = frappe.db.sql(
			"select ifnull(sum(debit),0), ifnull(sum(credit),0) from `tabGL Entry` where is_cancelled = 0 and company = %s",
			self.f.company,
		)[0]
		self.assertAlmostEqual(flt(row[0]), flt(row[1]), places=2)

	def test_cash_flow_rolls_forward(self):
		opening = sum(cash_flow.cash_position(self.f, add_days(self.f.from_date, -1)))
		inflow, outflow, monthly = cash_flow.cash_flows(self.f, self.f.from_date, self.f.to_date)
		closing = sum(cash_flow.cash_position(self.f, self.f.to_date))
		self.assertAlmostEqual(opening + inflow - outflow, closing, places=2)
		self.assertAlmostEqual(sum(a for a, _b in monthly.values()), inflow, places=2)


class TestEndpoints(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_every_endpoint_returns_a_payload(self):
		for method in (
			"dashboard.get_executive_dashboard",
			"sales.get_sales_analytics",
			"purchase.get_purchase_analytics",
			"accounting.get_accounting_analytics",
			"accounting.get_financial_statements",
			"receivables.get_receivables",
			"payables.get_payables",
			"cash_flow.get_cash_flow",
			"inventory.get_inventory",
			"gst.get_gst",
			"insights.get_insights",
		):
			out = frappe.get_attr(API + method)(filters={}, refresh=1)
			self.assertIsInstance(out, dict, method)
			self.assertIn("last_updated", out, method)
			self.assertNotIn("error", out, method)

	def test_guest_and_unauthorised_users_are_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_attr(API + "dashboard.get_executive_dashboard")(filters={}, refresh=1)
		frappe.set_user("Administrator")

	def test_landing_page_only_for_configured_roles(self):
		from business_intelligence_dashboard import boot

		self.assertFalse(boot.should_land_on_dashboard("Guest"))
		self.assertFalse(boot.should_land_on_dashboard("Administrator"))
		self.assertEqual(getdate("2026-01-01").year, 2026)
