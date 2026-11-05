"""Default landing page for the Business Intelligence Dashboard.

Frappe v15 desk opens ``frappe.boot.home_page`` when the user lands on ``/app`` (which is
where login redirects system users).  ``boot_session`` runs after Frappe has set it, so we
override it only for users who

* hold one of the roles listed in *BI Dashboard Settings > Roles landing on the dashboard*, and
* are actually permitted to open the page (page role check),

everyone else keeps their normal home page and is never redirected to a page they cannot open.
"""

import frappe

PAGE = "business-dashboard"


def landing_roles():
	try:
		if not frappe.db.get_default("bid_settings_initialised"):
			return {"BI Dashboard User"}  # not seeded yet: use the shipped default
		doc = frappe.get_cached_doc("BI Dashboard Settings")
		return {r.role for r in doc.get("home_page_roles") or []}
	except Exception:
		return {"BI Dashboard User"}


def can_open_dashboard(user=None):
	user = user or frappe.session.user
	if user in ("Guest",):
		return False
	if user == "Administrator":
		return True
	try:
		page_roles = frappe.get_cached_doc("Page", PAGE).get("roles") or []
	except frappe.DoesNotExistError:
		return False
	return bool({r.role for r in page_roles} & set(frappe.get_roles(user)))


def should_land_on_dashboard(user=None):
	user = user or frappe.session.user
	if user in ("Guest", "Administrator"):
		return False
	roles = set(frappe.get_roles(user))
	return bool(roles & landing_roles()) and can_open_dashboard(user)


def boot_session(bootinfo):
	if should_land_on_dashboard():
		bootinfo["home_page"] = PAGE


def get_website_user_home_page(user):
	"""Website-level fallback (``/`` redirect) for the same users; ``None`` keeps Frappe's default."""
	return "app/" + PAGE if should_land_on_dashboard(user) else None
