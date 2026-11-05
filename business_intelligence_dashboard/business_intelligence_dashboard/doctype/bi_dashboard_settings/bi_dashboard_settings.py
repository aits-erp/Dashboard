import frappe
from frappe import _
from frappe.model.document import Document


class BIDashboardSettings(Document):
	def validate(self):
		for field, minimum in (("cache_minutes", 1), ("top_n", 3), ("non_moving_days", 7)):
			if (self.get(field) or 0) < minimum:
				frappe.throw(_("{0} must be at least {1}").format(_(self.meta.get_label(field)), minimum))
		for field in ("low_margin_percent", "expense_increase_percent", "sales_decline_percent"):
			if (self.get(field) or 0) < 0:
				frappe.throw(_("{0} cannot be negative").format(_(self.meta.get_label(field))))

	def on_update(self):
		# thresholds and the landing roles feed cached payloads / boot info
		from business_intelligence_dashboard.business_intelligence_dashboard.api.utils import bump_cache_version

		bump_cache_version()
		frappe.cache.delete_key("home_page")
