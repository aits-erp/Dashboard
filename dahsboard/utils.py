import frappe

def redirect_after_login():
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = "/app/dashboard-view/home"
