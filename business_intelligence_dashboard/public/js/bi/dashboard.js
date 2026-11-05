// Dashboard shell: collapsible sidebar, global filter bar, section loading and routing.
import {
	api, drill, emptyHtml, errorHtml, esc, icon, lockedHtml, nextToken, setCurrency, skeleton,
} from "./core.js";
import { renderExecutive, renderInsights } from "./sec_overview.js";
import { renderSales, renderPurchase, renderOutstanding } from "./sec_commerce.js";
import { renderAccounting, renderStatements, renderCashFlow, renderInventory, renderGst } from "./sec_finance.js";

const SECTIONS = [
	{ key: "executive", label: __("Executive Dashboard"), short: __("Executive"), icon: "home", method: "dashboard.get_executive_dashboard", render: renderExecutive, perm: "executive" },
	{ key: "sales", label: __("Sales Analytics"), short: __("Sales"), icon: "shopping-cart", method: "sales.get_sales_analytics", render: renderSales, perm: "sales" },
	{ key: "purchase", label: __("Purchase Analytics"), short: __("Purchase"), icon: "truck", method: "purchase.get_purchase_analytics", render: renderPurchase, perm: "purchase" },
	{ key: "accounting", label: __("Accounting Analytics"), short: __("Accounting"), icon: "calculator", method: "accounting.get_accounting_analytics", render: renderAccounting, perm: "accounting" },
	{ key: "statements", label: __("Financial Statements"), short: __("Statements"), icon: "book-open", method: "accounting.get_financial_statements", render: renderStatements, perm: "statements" },
	{ key: "receivables", label: __("Receivables"), short: __("Receivables"), icon: "inbox", method: "receivables.get_receivables", render: (e, d, c) => renderOutstanding(e, d, c, "receivables"), perm: "receivables" },
	{ key: "payables", label: __("Payables"), short: __("Payables"), icon: "credit-card", method: "payables.get_payables", render: (e, d, c) => renderOutstanding(e, d, c, "payables"), perm: "payables" },
	{ key: "cashflow", label: __("Cash Flow & Banking"), short: __("Cash & Bank"), icon: "repeat", method: "cash_flow.get_cash_flow", render: renderCashFlow, perm: "cashflow" },
	{ key: "inventory", label: __("Inventory Analytics"), short: __("Inventory"), icon: "package", method: "inventory.get_inventory", render: renderInventory, perm: "inventory" },
	{ key: "gst", label: __("GST Analytics"), short: __("GST"), icon: "percent", method: "gst.get_gst", render: renderGst, perm: "gst" },
	{ key: "insights", label: __("Business Insights"), short: __("Insights"), icon: "bell", method: "insights.get_insights", render: renderInsights, perm: "insights" },
];

const LINK_FILTERS = [
	["customer", "Customer", __("Customer")],
	["supplier", "Supplier", __("Supplier")],
	["sales_person", "Sales Person", __("Salesperson")],
	["territory", "Territory", __("Territory")],
	["item_group", "Item Group", __("Item Group")],
	["warehouse", "Warehouse", __("Warehouse")],
	["department", "Department", __("Department")],
	["cost_center", "Cost Center", __("Cost Center")],
];

const STORE_KEY = "bid_state_v1";
const store = {
	get() {
		try { return JSON.parse(localStorage.getItem(`${STORE_KEY}:${frappe.session.user}`) || "{}"); } catch (e) { return {}; }
	},
	set(v) {
		try { localStorage.setItem(`${STORE_KEY}:${frappe.session.user}`, JSON.stringify(v)); } catch (e) { /* private mode */ }
	},
};

export class Dashboard {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Business Intelligence Dashboard"), single_column: true });
		this.cache = {};
		this.controls = {};
		this.section = "executive";
		this.applied = {};
		this.options = null;
		this.saved = store.get();
		this.build();
		this.init();
	}

	// ------------------------------------------------------------------------- shell
	build() {
		const main = this.page.main;
		main.addClass("bid-main");
		$(this.wrapper).addClass("bid-wrapper");
		this.page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.root = document.createElement("div");
		this.root.className = "bid" + (this.saved.collapsed ? " collapsed" : "");
		this.root.innerHTML = `
			<aside class="bid-side" aria-label="${__("Dashboard sections")}">
				<div class="bid-side-head"><span class="bid-logo">${icon("bar-chart", 18)}</span><span class="bid-side-title">${__("Business Intelligence")}</span>
					<button class="bid-icon-btn bid-collapse" title="${__("Collapse sidebar")}" aria-label="${__("Collapse sidebar")}">${icon("chevrons-left", 16)}</button></div>
				<nav class="bid-nav">${SECTIONS.map((s) => `<button class="bid-nav-item" data-s="${s.key}" title="${esc(s.label)}">${icon(s.icon, 18)}<span class="bid-nav-label">${esc(s.label)}</span><span class="bid-nav-badge" hidden></span></button>`).join("")}</nav>
			</aside>
			<div class="bid-scrim"></div>
			<div class="bid-content">
				<div class="bid-topbar">
					<button class="bid-icon-btn bid-burger" aria-label="${__("Open menu")}">${icon("menu", 20)}</button>
					<div class="bid-titles"><h2 class="bid-title"></h2><p class="bid-subtitle"></p></div>
					<div class="bid-updated" aria-live="polite"></div>
				</div>
				<div class="bid-filters">
					<div class="bid-filter-primary"></div>
					<div class="bid-filter-more" hidden></div>
					<div class="bid-filter-actions">
						<button class="btn btn-primary btn-sm bid-apply">${icon("check", 14)} ${__("Apply Filters")}</button>
						<button class="btn btn-default btn-sm bid-reset">${icon("x", 14)} ${__("Reset")}</button>
						<button class="btn btn-default btn-sm bid-refresh">${icon("refresh-cw", 14)} ${__("Refresh")}</button>
						<button class="btn btn-default btn-sm bid-more-toggle">${icon("filter", 14)} <span>${__("More filters")}</span><span class="bid-count" hidden></span></button>
					</div>
				</div>
				<div class="bid-chips"></div>
				<div class="bid-body" tabindex="-1"></div>
			</div>`;
		main.append(this.root);
		this.$ = (sel) => this.root.querySelector(sel);
		this.body = this.$(".bid-body");

		this.$(".bid-collapse").addEventListener("click", () => this.toggleCollapse());
		this.$(".bid-burger").addEventListener("click", () => this.root.classList.toggle("drawer-open"));
		this.$(".bid-scrim").addEventListener("click", () => this.root.classList.remove("drawer-open"));
		this.root.querySelectorAll(".bid-nav-item").forEach((b) => b.addEventListener("click", () => this.go(b.dataset.s)));
		this.$(".bid-apply").addEventListener("click", () => this.apply());
		this.$(".bid-reset").addEventListener("click", () => this.reset());
		this.$(".bid-refresh").addEventListener("click", () => this.refresh());
		this.$(".bid-more-toggle").addEventListener("click", () => {
			const more = this.$(".bid-filter-more");
			more.hidden = !more.hidden;
			this.$(".bid-more-toggle span").textContent = more.hidden ? __("More filters") : __("Fewer filters");
		});
		this.body.addEventListener("click", (e) => {
			if (e.target.closest(".bid-retry")) this.load(this.section, true);
		});
		this.root.addEventListener("keydown", (e) => {
			if (e.key === "Enter" && e.target.closest(".bid-filters") && !e.target.closest("button")) this.apply();
		});
	}

	toggleCollapse() {
		this.root.classList.toggle("collapsed");
		this.saved.collapsed = this.root.classList.contains("collapsed");
		store.set(this.saved);
		// charts are sized to their container: redraw after the width animation
		setTimeout(() => this.load(this.section, false), 260);
	}

	// ----------------------------------------------------------------- initialisation
	async init() {
		this.body.innerHTML = skeleton("dashboard");
		try {
			this.options = await api("dashboard.get_filter_options", { company: this.saved.filters && this.saved.filters.company });
		} catch (e) {
			this.body.innerHTML = errorHtml(esc(e.message));
			return;
		}
		setCurrency(this.options.currency);
		this.canConfigure = this.options.can_configure;
		this.buildFilters();
		this.defaults = this.defaultFilters();
		const restored = this.saved.filters && this.saved.filters.company === this.options.company ? this.saved.filters : null;
		this.setFilterValues(restored || this.defaults, false);
		// controls settle asynchronously, so seed from the values we just set rather than reading them back
		this.applied = Object.fromEntries(Object.entries(restored || this.defaults).filter(([, v]) => v));
		this.markNav();
		this.onShow();
	}

	defaultFilters() {
		const o = this.options;
		return { company: o.company, fiscal_year: o.fiscal_year, from_date: o.from_date, to_date: o.to_date };
	}

	buildFilters() {
		const primary = this.$(".bid-filter-primary");
		const more = this.$(".bid-filter-more");
		const add = (parent, df, cls = "") => {
			const holder = document.createElement("div");
			holder.className = `bid-field ${cls}`;
			holder.innerHTML = `<label>${esc(df.label)}</label><div class="bid-field-input"></div>`;
			parent.appendChild(holder);
			const c = frappe.ui.form.make_control({ df, parent: holder.querySelector(".bid-field-input"), render_input: true, only_input: true });
			c.refresh();
			this.controls[df.fieldname] = c;
			return c;
		};
		add(primary, { fieldtype: "Link", fieldname: "company", options: "Company", label: __("Company"), placeholder: __("Company"), change: () => this.onCompanyChange() });
		add(primary, { fieldtype: "Link", fieldname: "fiscal_year", options: "Fiscal Year", label: __("Financial Year"), placeholder: __("Financial Year"), change: () => this.onFiscalYearChange(),
			get_query: () => ({ filters: { name: ["in", this.options.fiscal_years.map((f) => f.name)] } }) });
		add(primary, { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		add(primary, { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });
		LINK_FILTERS.forEach(([name, doctype, label]) => {
			if (name === "department" && !this.options.has_department_dimension) {
				// still offered: it narrows GL based views only when Department is an accounting dimension
			}
			const df = { fieldtype: "Link", fieldname: name, options: doctype, label, placeholder: label };
			if (["warehouse", "cost_center", "department"].includes(name)) df.get_query = () => ({ filters: { company: this.controls.company.get_value() || this.options.company } });
			add(more, df);
		});
	}

	onCompanyChange() {
		if (this._silent) return;
		const company = this.controls.company.get_value();
		if (!company || company === this.options.company) return;
		// the fiscal year / currency belong to the company: refetch defaults
		api("dashboard.get_filter_options", { company }).then((o) => {
			this.options = o;
			setCurrency(o.currency);
			this.defaults = this.defaultFilters();
			this.setFilterValues({ company, fiscal_year: o.fiscal_year, from_date: o.from_date, to_date: o.to_date }, false);
		}).catch((e) => frappe.show_alert({ message: e.message, indicator: "red" }));
	}

	onFiscalYearChange() {
		const fy = this.controls.fiscal_year.get_value();
		// Link controls fire "change" late (after server validation), also for values we set
		// ourselves - only react when the user really picked a different fiscal year.
		if (!fy || fy === this._lastFy) return;
		this._lastFy = fy;
		const row = (this.options.fiscal_years || []).find((f) => f.name === fy);
		if (!row) return;
		const today = frappe.datetime.get_today();
		this.setValues({ from_date: row.from_date, to_date: today >= row.from_date && today <= row.to_date ? today : row.to_date });
	}

	setValues(values) {
		if (values.fiscal_year !== undefined) this._lastFy = values.fiscal_year || "";
		this._silent = true;
		Object.entries(values).forEach(([k, v]) => this.controls[k] && this.controls[k].set_value(v || ""));
		setTimeout(() => (this._silent = false), 150);
	}

	setFilterValues(values, apply) {
		const all = {};
		["company", "fiscal_year", "from_date", "to_date", ...LINK_FILTERS.map((l) => l[0])].forEach((k) => (all[k] = values[k] || ""));
		this.setValues(all);
		if (apply) this.apply();
	}

	readFilters() {
		const out = {};
		Object.entries(this.controls).forEach(([k, c]) => {
			// a Link control reports "" until its server validation returns; fall back to what is typed
			const v = c.get_value() || (c.df.fieldtype === "Link" && c.$input ? c.$input.val() : "");
			if (v) out[k] = v;
		});
		return out;
	}

	validateFilters(f) {
		if (f.from_date && f.to_date && f.from_date > f.to_date) {
			frappe.show_alert({ message: __("From Date cannot be after To Date"), indicator: "red" });
			return false;
		}
		return true;
	}

	// --------------------------------------------------------------------- actions
	apply() {
		const f = this.readFilters();
		if (!this.validateFilters(f)) return;
		this.applied = f;
		this.saved.filters = f;
		store.set(this.saved);
		this.cache = {};
		this.renderChips();
		this.load(this.section, true);
	}

	reset() {
		this.setFilterValues(this.defaults, false);
		setTimeout(() => this.apply(), 200);
	}

	refresh() {
		this.cache = {};
		this.load(this.section, true, true);
	}

	filtersJson() {
		const f = { ...this.applied };
		delete f.fiscal_year; // dates drive the period; fiscal year only seeds them
		return JSON.stringify(f);
	}

	renderChips() {
		const chips = this.$(".bid-chips");
		const extra = LINK_FILTERS.filter(([k]) => this.applied[k]);
		chips.innerHTML = extra.map(([k, , label]) => `<span class="bid-chip">${esc(label)}: <b>${esc(this.applied[k])}</b><button data-k="${k}" aria-label="${__("Remove filter")}">${icon("x", 12)}</button></span>`).join("");
		chips.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { this.controls[b.dataset.k].set_value(""); setTimeout(() => this.apply(), 150); }));
		const count = this.$(".bid-count");
		count.hidden = !extra.length;
		count.textContent = extra.length;
	}

	// -------------------------------------------------------------------- routing
	go(key) {
		this.root.classList.remove("drawer-open");
		frappe.set_route("business-dashboard", key);
	}

	onShow() {
		const route = frappe.get_route();
		// the bare route (login landing, /app) always means the Executive view
		const key = route[0] === "business-dashboard" && route[1] ? route[1] : "executive";
		const sec = SECTIONS.find((s) => s.key === key) || SECTIONS[0];
		this.section = sec.key;
		this.saved.section = sec.key;
		store.set(this.saved);
		if (!this.options) return;
		this.markNav();
		this.renderChips();
		this.load(sec.key, false);
	}

	markNav() {
		const allowed = (this.options && this.options.sections) || {};
		this.root.querySelectorAll(".bid-nav-item").forEach((b) => {
			const sec = SECTIONS.find((s) => s.key === b.dataset.s);
			b.classList.toggle("active", b.dataset.s === this.section);
			b.classList.toggle("restricted", allowed[sec.perm] === false);
			b.setAttribute("aria-current", b.dataset.s === this.section ? "page" : "false");
		});
		const sec = SECTIONS.find((s) => s.key === this.section);
		this.$(".bid-title").textContent = sec.label;
		const f = this.applied;
		this.$(".bid-subtitle").textContent = `${f.company || this.options.company} · ${frappe.datetime.str_to_user(f.from_date || this.options.from_date)} – ${frappe.datetime.str_to_user(f.to_date || this.options.to_date)}`;
	}

	// ------------------------------------------------------------------- data load
	async load(key, force, bypassServerCache) {
		const sec = SECTIONS.find((s) => s.key === key);
		if (!sec) return;
		this.markNav();
		const allowed = this.options.sections || {};
		if (allowed[sec.perm] === false) {
			this.body.innerHTML = lockedHtml(__("Your role does not have access to {0}.", [sec.label]));
			return;
		}
		const ck = `${key}|${this.filtersJson()}`;
		const token = (this.token = nextToken());
		let data = !force && this.cache[ck];
		if (!data) {
			this.body.innerHTML = skeleton(key === "executive" ? "dashboard" : "section");
			this.setUpdated(null);
			try {
				data = await api(sec.method, { filters: this.filtersJson(), refresh: bypassServerCache ? 1 : 0 });
			} catch (e) {
				if (token !== this.token) return;
				this.body.innerHTML = errorHtml(esc(e.message));
				return;
			}
			if (token !== this.token) return; // a newer request superseded this one
			this.cache[ck] = data;
		}
		this.draw(sec, data);
	}

	draw(sec, data) {
		if (data.currency) setCurrency(data.currency, data.currency_symbol);
		this.setUpdated(data.last_updated);
		this.body.innerHTML = "";
		if (data.permission_denied) {
			this.body.innerHTML = lockedHtml(data.message);
			return;
		}
		const pane = document.createElement("div");
		pane.className = "bid-pane";
		this.body.appendChild(pane);
		try {
			sec.render(pane, data, { f: this.currentFilters(data), filtersJson: () => this.filtersJson(), canConfigure: this.canConfigure });
		} catch (e) {
			console.error("[bid] render failed", sec.key, e);
			this.body.innerHTML = errorHtml(__("This section could not be displayed ({0}).", [esc(e.message)]));
			return;
		}
		if (sec.key === "executive" && !this.badgeLoaded) this.loadBadge();
	}

	currentFilters(data) {
		const p = (data && data.period) || {};
		return { ...this.applied, company: this.applied.company || this.options.company, from_date: p.from_date || this.applied.from_date || this.options.from_date, to_date: p.to_date || this.applied.to_date || this.options.to_date };
	}

	setUpdated(ts) {
		const el = this.$(".bid-updated");
		if (!ts) { el.innerHTML = `<span class="bid-spin"></span> ${__("Updating…")}`; return; }
		el.innerHTML = `${icon("check-circle", 14)} ${__("Last updated")} ${frappe.datetime.str_to_user(ts.split(".")[0])}`;
	}

	async loadBadge() {
		this.badgeLoaded = true;
		if (!(this.options.sections || {}).insights) return;
		try {
			const d = await api("insights.get_insights", { filters: this.filtersJson(), refresh: 0 });
			const n = (d.counts.critical || 0) + (d.counts.warning || 0);
			const badge = this.$('.bid-nav-item[data-s="insights"] .bid-nav-badge');
			badge.hidden = !n;
			badge.textContent = n;
			badge.className = "bid-nav-badge" + (d.counts.critical ? " critical" : "");
		} catch (e) { /* badge is optional */ }
	}
}
