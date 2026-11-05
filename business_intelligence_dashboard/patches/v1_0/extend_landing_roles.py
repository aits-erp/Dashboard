import frappe

from business_intelligence_dashboard.install import DEFAULT_LANDING_ROLES, ROLE


def execute():
	"""Sites seeded by the first release only had the dedicated role as a landing role, which made the
	dashboard open for nobody after login. Widen it to the default management roles - but only when
	the list is still exactly the shipped one, so an administrator's own choice is never overridden."""
	if not frappe.db.exists("DocType", "BI Dashboard Settings"):
		return
	settings = frappe.get_doc("BI Dashboard Settings")
	if [r.role for r in settings.get("home_page_roles")] != [ROLE]:
		return
	settings.set("home_page_roles", [{"role": r} for r in DEFAULT_LANDING_ROLES])
	settings.flags.ignore_permissions = True
	settings.save()
