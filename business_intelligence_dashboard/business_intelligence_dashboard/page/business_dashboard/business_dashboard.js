frappe.pages["business-dashboard"].on_page_load = function (wrapper) {
	frappe.require("bi_dashboard.bundle.js", () => {
		wrapper.bid = new business_intelligence_dashboard.Dashboard(wrapper);
	});
};

frappe.pages["business-dashboard"].on_page_show = function (wrapper) {
	// navigating between sections only changes the route: the page instance is reused
	if (wrapper.bid) wrapper.bid.onShow();
};
