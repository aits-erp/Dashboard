"""Default landing page for the Business Intelligence Dashboard.

Frappe v15 opens ``frappe.boot.home_page`` when the user lands on ``/app``. Where login sends the
user depends on ``frappe.apps.get_default_path``: with a single desk app it is that app's route,
with several desk apps it is ``/app``. The dashboard therefore registers itself on the apps screen
(``add_to_apps_screen`` in hooks.py) for exactly the users who may use it, and ``boot_session``
sets the home page for those whose role is listed in *BI Dashboard Settings > Roles landing on the
dashboard*. Everybody else keeps their normal home page and is never redirected to a page they
cannot open.
"""

import frappe

PAGE = "business-dashboard"


def landing_roles():
	try:
		if not frappe.db.get_default("bid_settings_initialised"):
			from business_intelligence_dashboard.install import DEFAULT_LANDING_ROLES

			return set(DEFAULT_LANDING_ROLES)  # not seeded yet: use the shipped default
		doc = frappe.get_cached_doc("BI Dashboard Settings")
		return {r.role for r in doc.get("home_page_roles") or []}
	except Exception:
		return {"BI Dashboard User"}


def can_open_dashboard(user=None):
	user = user or frappe.session.user
	if user == "Guest":
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
	if user == "Guest":
		return False
	# Administrator holds every role, so it follows the same role list as everyone else
	roles = set(frappe.get_roles(user))
	return bool(roles & landing_roles()) and can_open_dashboard(user)


def boot_session(bootinfo):
	if should_land_on_dashboard():
		bootinfo["home_page"] = PAGE


def has_app_permission():
	"""Apps screen: show the dashboard only to users who may open it."""
	return can_open_dashboard()


def get_website_user_home_page(user):
	"""Website-level fallback (``/`` redirect) for the same users; ``None`` keeps Frappe's default."""
	return "app/" + PAGE if should_land_on_dashboard(user) else None
