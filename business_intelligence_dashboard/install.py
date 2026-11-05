import frappe

ROLE = "BI Dashboard User"
PAGE = "business-dashboard"
INIT_MARKER = "bid_settings_initialised"

# Roles that open the dashboard right after login on a fresh install (editable in BI Dashboard Settings).
# Management / finance roles plus the dedicated role; everyone else keeps their normal home page.
DEFAULT_LANDING_ROLES = (
	ROLE,
	"System Manager",
	"Accounts Manager",
	"Sales Manager",
	"Purchase Manager",
	"Stock Manager",
	"Auditor",
)


def before_install():
	# the Page and Workspace reference this role, so it must exist before they are synced
	ensure_role()


def after_install():
	ensure_role()
	ensure_settings()


def after_migrate():
	ensure_role()
	ensure_settings()


def ensure_role():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc(
			{"doctype": "Role", "role_name": ROLE, "desk_access": 1, "is_custom": 1}
		).insert(ignore_permissions=True)


def ensure_settings():
	"""Seed the settings once with the default landing roles.

	A marker (not the table contents) records that seeding happened, so an administrator
	who deliberately empties the role list to switch the redirect off is not overridden
	by the next migrate.
	"""
	if not frappe.db.exists("DocType", "BI Dashboard Settings") or frappe.db.get_default(INIT_MARKER):
		return
	settings = frappe.get_doc("BI Dashboard Settings")
	if not settings.get("home_page_roles"):
		settings.set("home_page_roles", [{"role": r} for r in DEFAULT_LANDING_ROLES])
	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.set_default(INIT_MARKER, "1")
