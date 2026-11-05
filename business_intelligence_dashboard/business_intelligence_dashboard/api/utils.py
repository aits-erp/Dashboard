"""Shared helpers for the Business Intelligence Dashboard APIs.

Everything here is permission aware, parameterised and cache friendly:

* ``parse_filters`` validates and normalises the global filters (company, dates,
  parties, dimensions) and applies the user's *User Permissions*.
* ``cached`` is a small decorator that caches an endpoint's payload per user and
  filter set; ``bump_cache_version`` (hooked to document events) invalidates it.
* ``sales_scope`` / ``purchase_scope`` build the parameterised SQL fragments that
  all sales / purchase analytics share.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_days, add_months, add_years, cint, flt, getdate, now_datetime, nowdate

DASHBOARD_ROLES = (
	"System Manager",
	"Accounts Manager",
	"Accounts User",
	"Sales Manager",
	"Purchase Manager",
	"Stock Manager",
	"Auditor",
	"BI Dashboard User",
)

DEFAULT_SETTINGS = {
	"cache_minutes": 5,
	"overdue_days_alert": 30,
	"high_outstanding_amount": 500000,
	"low_margin_percent": 10,
	"expense_increase_percent": 25,
	"sales_decline_percent": 10,
	"pending_order_days": 15,
	"delayed_po_days": 7,
	"non_moving_days": 90,
	"slow_moving_orders": 3,
	"top_n": 10,
}

# filter key -> (DocType, list key used in SQL, is tree)
LINK_FILTERS = {
	"customer": ("Customer", "customers", False),
	"supplier": ("Supplier", "suppliers", False),
	"sales_person": ("Sales Person", "sales_persons", True),
	"territory": ("Territory", "territories", True),
	"item_group": ("Item Group", "item_groups", True),
	"warehouse": ("Warehouse", "warehouses", True),
	"department": ("Department", "departments", True),
	"cost_center": ("Cost Center", "cost_centers", True),
}


# --------------------------------------------------------------------- access


def has_dashboard_access(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)) & set(DASHBOARD_ROLES))


def require_dashboard_access():
	if not has_dashboard_access():
		frappe.throw(_("You are not permitted to use the Business Intelligence Dashboard."), frappe.PermissionError)


def require_permission(*doctypes):
	"""Raise PermissionError unless the user can read every given DocType."""
	for dt in doctypes:
		if not frappe.has_permission(dt, "read"):
			frappe.throw(
				_("You do not have permission to read {0}.").format(_(dt)),
				frappe.PermissionError,
			)


def can_read(*doctypes):
	return all(frappe.has_permission(dt, "read") for dt in doctypes)


def get_permitted_companies():
	"""Companies the user may analyse.

	Dashboard roles (e.g. Sales Manager) often lack read access to the Company DocType itself,
	so the list is taken without the DocType check and restricted by the user's *User
	Permissions* on Company - the same restriction Frappe applies to company-linked records.
	"""
	require_dashboard_access()
	names = frappe.get_all("Company", pluck="name", order_by="name")
	allowed = _user_permitted_names("Company")
	if allowed is not None:
		names = [n for n in names if n in allowed]
	return names


def get_settings():
	"""Dashboard thresholds. Falls back to defaults before the doctype is migrated."""
	settings = frappe._dict(DEFAULT_SETTINGS)
	try:
		doc = frappe.get_cached_doc("BI Dashboard Settings")
		for key in DEFAULT_SETTINGS:
			value = doc.get(key)
			if value not in (None, ""):
				settings[key] = value
	except Exception:
		pass
	return settings


# -------------------------------------------------------------------- filters


def _fiscal_year_for(date, company):
	"""(name, start, end) of the fiscal year containing ``date``; calendar year fallback."""
	try:
		from erpnext.accounts.utils import get_fiscal_year

		name, start, end = get_fiscal_year(date, company=company)
		return name, getdate(start), getdate(end)
	except Exception:
		frappe.clear_last_message()
		date = getdate(date)
		return None, getdate(f"{date.year}-01-01"), getdate(f"{date.year}-12-31")


def _user_permitted_names(doctype):
	"""Names the user is restricted to for a DocType via User Permissions, or None."""
	from frappe.permissions import get_user_permissions

	perms = get_user_permissions(frappe.session.user) or {}
	rows = perms.get(doctype)
	if not rows:
		return None
	return [r.get("doc") for r in rows if r.get("doc")]


def _expand(doctype, names, is_tree):
	out = []
	for name in names:
		out.append(name)
		if is_tree:
			from frappe.utils.nestedset import get_descendants_of

			try:
				out.extend(get_descendants_of(doctype, name, ignore_permissions=True) or [])
			except Exception:
				frappe.clear_last_message()
	return list(dict.fromkeys(out))


def parse_filters(raw=None):
	"""Validate the global filters and return a normalised ``frappe._dict``."""
	require_dashboard_access()

	if isinstance(raw, str):
		try:
			raw = json.loads(raw) if raw.strip() else {}
		except ValueError:
			frappe.throw(_("Invalid filters"), frappe.ValidationError)
	raw = raw or {}
	if not isinstance(raw, dict):
		frappe.throw(_("Invalid filters"), frappe.ValidationError)

	f = frappe._dict()

	permitted = get_permitted_companies()
	if not permitted:
		frappe.throw(_("No company is accessible for your user."), frappe.PermissionError)

	company = raw.get("company") or default_company(permitted)
	if not isinstance(company, str) or company not in permitted:
		frappe.throw(_("You are not permitted to access company {0}.").format(frappe.bold(str(company))), frappe.PermissionError)
	f.company = company
	f.currency = frappe.get_cached_value("Company", company, "default_currency")
	f.currency_symbol = frappe.db.get_value("Currency", f.currency, "symbol") or f.currency

	today = getdate(nowdate())
	fy_name, fy_start, fy_end = _fiscal_year_for(today, company)

	fiscal_year = raw.get("fiscal_year")
	if fiscal_year and not (raw.get("from_date") and raw.get("to_date")):
		row = frappe.db.get_value("Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"])
		if not row:
			frappe.throw(_("Unknown fiscal year {0}").format(frappe.bold(str(fiscal_year))), frappe.ValidationError)
		fy_name, fy_start, fy_end = fiscal_year, getdate(row[0]), getdate(row[1])
		from_date, to_date = fy_start, min(today, fy_end) if fy_start <= today <= fy_end else fy_end
	else:
		try:
			from_date = getdate(raw["from_date"]) if raw.get("from_date") else fy_start
			to_date = getdate(raw["to_date"]) if raw.get("to_date") else (min(today, fy_end) if from_date <= today else from_date)
		except Exception:
			frappe.throw(_("Invalid date filter"), frappe.ValidationError)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date"), frappe.ValidationError)
	if (to_date - from_date).days > 366 * 5:
		frappe.throw(_("Please choose a period of at most five years"), frappe.ValidationError)

	f.fiscal_year = fy_name
	f.from_date, f.to_date = from_date, to_date
	f.fy_start, f.fy_end = _fiscal_year_for(from_date, company)[1:]
	f.today = today

	# previous period: same dates last year when the range starts on a fiscal year
	# start (year-to-date style), otherwise the immediately preceding equal span
	if from_date == f.fy_start:
		f.prev_from, f.prev_to = add_years(from_date, -1), add_years(to_date, -1)
	else:
		span = (to_date - from_date).days + 1
		f.prev_to = add_days(from_date, -1)
		f.prev_from = add_days(f.prev_to, -(span - 1))

	for key, (doctype, list_key, is_tree) in LINK_FILTERS.items():
		value = raw.get(key)
		f[key] = None
		f[list_key] = None
		allowed = _user_permitted_names(doctype)
		allowed = _expand(doctype, allowed, is_tree) if allowed else None
		chosen = None
		if value:
			if not isinstance(value, str) or len(value) > 140 or not frappe.db.exists(doctype, value):
				frappe.throw(_("Unknown {0}: {1}").format(_(doctype), frappe.bold(str(value))), frappe.ValidationError)
			f[key] = value
			chosen = _expand(doctype, [value], is_tree)
			if allowed is not None and not set(chosen) & set(allowed):
				frappe.throw(_("You are not permitted to access {0} {1}.").format(_(doctype), frappe.bold(value)), frappe.PermissionError)
		if chosen is not None and allowed is not None:
			chosen = [c for c in chosen if c in allowed]
		f[list_key] = chosen if chosen is not None else allowed
	return f


def default_company(permitted=None):
	permitted = permitted or get_permitted_companies()
	for candidate in (
		frappe.defaults.get_user_default("Company"),
		frappe.defaults.get_global_default("company"),
	):
		if candidate in permitted:
			return candidate
	return permitted[0] if permitted else None


def filter_summary(f):
	"""A hashable/serialisable subset of the filters, used as cache key material."""
	keys = ["company", "from_date", "to_date"] + [k for k in LINK_FILTERS]
	return {k: str(f.get(k)) for k in keys if f.get(k)}


# ---------------------------------------------------------------------- cache


def _cache_version():
	return frappe.cache.get_value("bid_cache_version") or "0"


def bump_cache_version(doc=None, method=None):
	"""Hooked to the transactional DocTypes; invalidates every cached dashboard payload."""
	try:
		frappe.cache.set_value("bid_cache_version", str(now_datetime().timestamp()))
	except Exception:
		pass


def cached(fn):
	"""Cache an API function ``fn(f)`` per user + filters; ``refresh=1`` bypasses the cache.

	The wrapper keeps a plain ``(filters, refresh)`` signature so Frappe's argument
	filtering works.  A payload that raised PermissionError is never cached.
	"""

	def wrapper(filters=None, refresh=0):
		f = parse_filters(filters)
		material = json.dumps(
			[frappe.session.user, fn.__module__, fn.__name__, filter_summary(f), _cache_version()],
			sort_keys=True,
		)
		key = "bid:" + hashlib.sha1(material.encode()).hexdigest()
		if not cint(refresh):
			hit = frappe.cache.get_value(key)
			if hit is not None:
				return hit
		data = fn(f)
		data["currency"] = f.currency
		data["currency_symbol"] = f.currency_symbol
		data["period"] = {
			"from_date": str(f.from_date),
			"to_date": str(f.to_date),
			"prev_from": str(f.prev_from),
			"prev_to": str(f.prev_to),
		}
		data["last_updated"] = str(now_datetime())
		ttl = max(cint(get_settings().cache_minutes), 1) * 60
		frappe.cache.set_value(key, data, expires_in_sec=ttl)
		return data

	wrapper.__name__ = fn.__name__
	wrapper.__doc__ = fn.__doc__
	wrapper.__module__ = fn.__module__
	return wrapper


def locked(doctypes, message=None):
	"""Payload returned when the user lacks permission for a whole section."""
	return {
		"permission_denied": True,
		"message": message
		or _("You need read access to {0} to see this section.").format(", ".join(_(d) for d in doctypes)),
	}


# ---------------------------------------------------------------- calculations


def growth(current, previous):
	"""Percentage change; ``None`` when there is no meaningful base."""
	current, previous = flt(current), flt(previous)
	if not previous:
		return None
	return round((current - previous) / abs(previous) * 100, 2)


def ratio_pct(part, whole):
	whole = flt(whole)
	return round(flt(part) / whole * 100, 2) if whole else 0.0


def months_between(from_date, to_date):
	"""['2026-04', '2026-05', ...] covering the period."""
	cur = getdate(from_date).replace(day=1)
	end = getdate(to_date)
	out = []
	while cur <= end:
		out.append(cur.strftime("%Y-%m"))
		cur = add_months(cur, 1)
	return out


def month_label(ym):
	return getdate(ym + "-01").strftime("%b %Y")


def series_by_month(rows, months, key="month", value="value"):
	"""Fill ``rows`` ([{month: 'YYYY-MM', value: x}]) into ordered labels/values."""
	lookup = {r[key]: flt(r[value]) for r in rows}
	return {
		"months": months,
		"labels": [month_label(m) for m in months],
		"values": [round(lookup.get(m, 0.0), 2) for m in months],
	}


def request_memo():
	"""Per-request scratch dict so nested payload builders share expensive report runs."""
	try:
		return frappe.local.bid_memo
	except AttributeError:
		frappe.local.bid_memo = {}
		return frappe.local.bid_memo


def top_n():
	return max(cint(get_settings().top_n) or 10, 1)


# ------------------------------------------------------------------ drill-down


def list_route(doctype, filters=None):
	return {"type": "list", "doctype": doctype, "filters": filters or {}}


def report_route(report, filters=None):
	return {"type": "report", "report": report, "filters": filters or {}}


def form_route(doctype, name):
	return {"type": "form", "doctype": doctype, "name": name}


def date_range(f, field="posting_date"):
	return {field: ["Between", [str(f.from_date), str(f.to_date)]]}


# ----------------------------------------------------------- SQL scope builders


class Scope:
	"""A parameterised ``FROM ... JOIN ... WHERE`` fragment shared by analytics queries."""

	def __init__(self, sql_from, where, params):
		self.sql_from = sql_from
		self.where = where
		self.params = params

	def query(self, select, tail="", extra_where="", extra_params=None):
		params = dict(self.params)
		params.update(extra_params or {})
		sql = f"select {select} {self.sql_from} where {self.where} {extra_where} {tail}"
		return frappe.db.sql(sql, params, as_dict=True)


def _scope(f, header, item, party_field, party_list, has_territory, team_doctype, from_key, to_key, period_field="posting_date", extra=""):
	h, i = "h", "i"
	conds = [f"{h}.docstatus = 1", f"{h}.company = %(company)s", f"{h}.{period_field} between %({from_key})s and %({to_key})s"]
	params = {"company": f.company, from_key: f[from_key], to_key: f[to_key]}

	if f.get(party_list) is not None:
		conds.append(f"{h}.{party_field} in %(parties)s")
		params["parties"] = tuple(f[party_list]) or ("",)
	if has_territory and f.territories is not None:
		conds.append(f"{h}.territory in %(territories)s")
		params["territories"] = tuple(f.territories) or ("",)
	if team_doctype and f.sales_persons is not None:
		conds.append(
			f"exists (select 1 from `tabSales Team` st where st.parent = {h}.name "
			f"and st.parenttype = '{team_doctype}' and st.sales_person in %(sales_persons)s)"
		)
		params["sales_persons"] = tuple(f.sales_persons) or ("",)
	if f.item_groups is not None:
		conds.append(f"{i}.item_group in %(item_groups)s")
		params["item_groups"] = tuple(f.item_groups) or ("",)
	if f.warehouses is not None:
		conds.append(f"{i}.warehouse in %(warehouses)s")
		params["warehouses"] = tuple(f.warehouses) or ("",)
	if f.cost_centers is not None:
		conds.append(f"{i}.cost_center in %(cost_centers)s")
		params["cost_centers"] = tuple(f.cost_centers) or ("",)
	sql_from = f"from `tab{item}` {i} join `tab{header}` {h} on {h}.name = {i}.parent"
	return Scope(sql_from, " and ".join(conds) + extra, params)


def sales_invoice_scope(f, previous=False):
	"""Submitted Sales Invoice Items (alias i) joined to header (alias h)."""
	fk, tk = ("prev_from", "prev_to") if previous else ("from_date", "to_date")
	return _scope(f, "Sales Invoice", "Sales Invoice Item", "customer", "customers", True, "Sales Invoice", fk, tk)


def purchase_invoice_scope(f, previous=False):
	fk, tk = ("prev_from", "prev_to") if previous else ("from_date", "to_date")
	return _scope(f, "Purchase Invoice", "Purchase Invoice Item", "supplier", "suppliers", False, None, fk, tk)


def sales_order_scope(f, previous=False):
	fk, tk = ("prev_from", "prev_to") if previous else ("from_date", "to_date")
	return _scope(
		f, "Sales Order", "Sales Order Item", "customer", "customers", True, "Sales Order", fk, tk, "transaction_date"
	)


def purchase_order_scope(f, previous=False):
	fk, tk = ("prev_from", "prev_to") if previous else ("from_date", "to_date")
	return _scope(
		f, "Purchase Order", "Purchase Order Item", "supplier", "suppliers", False, None, fk, tk, "transaction_date"
	)


def purchase_receipt_scope(f, previous=False):
	fk, tk = ("prev_from", "prev_to") if previous else ("from_date", "to_date")
	return _scope(f, "Purchase Receipt", "Purchase Receipt Item", "supplier", "suppliers", False, None, fk, tk)


def gl_conditions(f, alias="gle", from_key="from_date", to_key="to_date", with_dates=True):
	"""Parameterised GL Entry conditions (company, cancellation, cost centre, party)."""
	conds = [f"{alias}.company = %(company)s", f"{alias}.is_cancelled = 0"]
	params = {"company": f.company}
	if with_dates:
		conds.append(f"{alias}.posting_date between %({from_key})s and %({to_key})s")
		params[from_key], params[to_key] = f[from_key], f[to_key]
	if f.cost_centers is not None:
		conds.append(f"{alias}.cost_center in %(cost_centers)s")
		params["cost_centers"] = tuple(f.cost_centers) or ("",)
	if f.department and frappe.db.has_column("GL Entry", "department"):
		conds.append(f"{alias}.department in %(departments)s")
		params["departments"] = tuple(f.departments) or ("",)
	return " and ".join(conds), params


def day_diff_bucket(days):
	if days <= 30:
		return "0-30"
	if days <= 60:
		return "31-60"
	if days <= 90:
		return "61-90"
	return "90+"
