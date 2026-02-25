// ==========================================
// Redirect to Dashboard Home after Login
// ==========================================

frappe.after_ajax(() => {

    const isOnHome =
        window.location.pathname === "/app" ||
        window.location.pathname === "/app/home";

    if (isOnHome) {
        console.log("[custom] Redirecting to /app/dashboard-view/Home");

        // Small delay ensures router is initialized
        setTimeout(() => {
            frappe.set_route("dashboard-view", "Home");
        }, 300);
    }
});