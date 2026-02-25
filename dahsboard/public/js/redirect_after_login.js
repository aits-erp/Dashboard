// ==========================================
// Redirect to Dashboard Home after Login
// ==========================================

frappe.ready(function () {

    const redirectToDashboardHome = () => {

        // Prevent infinite loop
        const isOnHome =
            window.location.pathname === "/app" ||
            window.location.pathname === "/app/home";

        if (isOnHome) {
            console.log("[custom] Redirecting to /app/dashboard-view/Home");
            frappe.set_route("dashboard-view", "Home");
        }
    };

    // Wait until boot is fully loaded
    if (frappe.boot) {
        redirectToDashboardHome();
    } else {
        frappe.after_ajax(() => {
            redirectToDashboardHome();
        });
    }
});