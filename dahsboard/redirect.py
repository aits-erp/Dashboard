import frappe

def after_login_redirect(login_manager):
    # Only for Administrator
    if frappe.session.user == "Administrator":
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = "/app/dashboard-view/home"
