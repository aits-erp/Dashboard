// Shared helpers for the Business Intelligence Dashboard: formatting, API calls,
// drill-down routing, icons and the small component set (panels, charts, bar lists, tables).

const API = "business_intelligence_dashboard.business_intelligence_dashboard.api.";

// ---------------------------------------------------------------- icons (24px stroke set)
const ICON_PATHS = {
	home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
	"shopping-cart": '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>',
	truck: '<rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
	calculator: '<rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="8" y2="10.01"/><line x1="12" y1="10" x2="12" y2="10.01"/><line x1="16" y1="10" x2="16" y2="10.01"/><line x1="8" y1="14" x2="8" y2="14.01"/><line x1="12" y1="14" x2="12" y2="14.01"/><line x1="16" y1="14" x2="16" y2="14.01"/><line x1="8" y1="18" x2="16" y2="18"/>',
	"file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
	"file-minus": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/>',
	inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
	"credit-card": '<rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>',
	wallet: '<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>',
	package: '<line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
	percent: '<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
	"alert-triangle": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
	"trending-up": '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
	receipt: '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1z"/><line x1="8" y1="8" x2="16" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/>',
	layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
	award: '<circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/>',
	"pie-chart": '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
	briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
	scale: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
	clipboard: '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/>',
	"clipboard-list": '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="16" x2="15" y2="16"/>',
	"rotate-ccw": '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
	activity: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
	"corner-up-left": '<polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>',
	"dollar-sign": '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
	landmark: '<line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/><line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/><line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/>',
	"arrow-down-circle": '<circle cx="12" cy="12" r="10"/><polyline points="8 12 12 16 16 12"/><line x1="12" y1="8" x2="12" y2="16"/>',
	"arrow-up-circle": '<circle cx="12" cy="12" r="10"/><polyline points="16 12 12 8 8 12"/><line x1="12" y1="16" x2="12" y2="8"/>',
	repeat: '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
	menu: '<line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>',
	"chevrons-left": '<polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/>',
	"chevrons-right": '<polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/>',
	"refresh-cw": '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
	filter: '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
	settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
	bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
	"book-open": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
	"bar-chart": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
	x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
	check: '<polyline points="20 6 9 17 4 12"/>',
	"check-circle": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
	"x-circle": '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
	info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
	lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
	"arrow-up": '<line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>',
	"arrow-down": '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/>',
	minus: '<line x1="5" y1="12" x2="19" y2="12"/>',
	table: '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/>',
	"bar-chart-2": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
	"external-link": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
};

export function icon(name, size = 18) {
	const body = ICON_PATHS[name] || ICON_PATHS.activity;
	return `<svg class="bid-icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

export const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

// -------------------------------------------------------------------------- formatting
export const state = { currency: "INR", symbol: "₹" };

export function setCurrency(currency, symbol) {
	if (currency) state.currency = currency;
	if (symbol) state.symbol = symbol;
}

export function compact(value) {
	const v = Number(value) || 0;
	const a = Math.abs(v);
	const sign = v < 0 ? "-" : "";
	if (state.currency === "INR") {
		if (a >= 1e7) return `${sign}${(a / 1e7).toFixed(2)} Cr`;
		if (a >= 1e5) return `${sign}${(a / 1e5).toFixed(2)} L`;
		if (a >= 1e3) return `${sign}${(a / 1e3).toFixed(1)} K`;
		return `${sign}${a.toFixed(a % 1 ? 2 : 0)}`;
	}
	if (a >= 1e9) return `${sign}${(a / 1e9).toFixed(2)} B`;
	if (a >= 1e6) return `${sign}${(a / 1e6).toFixed(2)} M`;
	if (a >= 1e3) return `${sign}${(a / 1e3).toFixed(1)} K`;
	return `${sign}${a.toFixed(a % 1 ? 2 : 0)}`;
}

export const money = (v) => (v == null ? "—" : `${state.symbol} ${compact(v)}`);
export const moneyFull = (v) => (v == null ? "—" : format_currency(v, state.currency));
export const num = (v, digits = 0) => (v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: digits }));
export const pct = (v) => (v == null ? "—" : `${Number(v).toFixed(1)}%`);

export function fmtValue(kind, v) {
	if (v == null) return "—";
	if (kind === "currency") return money(v);
	if (kind === "percent") return pct(v);
	if (kind === "ratio") return Number(v).toFixed(2);
	return num(v, 2);
}

export const monthRange = (label) => {
	// "Apr 2026" -> ["2026-04-01", "2026-04-30"]
	const d = new Date(`1 ${label}`);
	if (isNaN(d)) return null;
	const pad = (n) => String(n).padStart(2, "0");
	const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
	const ym = `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
	return [`${ym}-01`, `${ym}-${pad(last)}`];
};

// ------------------------------------------------------------------------------- API
let tokenSeq = 0;
export function api(method, args = {}) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: API + method,
			args,
			type: "POST",
			freeze: false,
			// we render errors in the page ourselves instead of popping a dialog
			error: (r) => reject(extractError(r)),
			callback: (r) => (r && r.message !== undefined ? resolve(r.message) : reject(new Error(__("Empty response")))),
		});
	});
}

function extractError(r) {
	let msg = __("Something went wrong while loading this section.");
	try {
		const server = r && r.responseJSON && r.responseJSON._server_messages;
		if (server) {
			msg = JSON.parse(server).map((m) => JSON.parse(m).message).join("<br>");
		} else if (r && r.responseJSON && r.responseJSON.exception) {
			msg = r.responseJSON.exception.split(":").slice(1).join(":").trim() || msg;
		} else if (r && r.status === 403) {
			msg = __("You do not have permission to view this section.");
		}
	} catch (e) {
		/* keep default */
	}
	const err = new Error(msg);
	err.status = r && r.status;
	return err;
}

export const nextToken = () => ++tokenSeq;

// -------------------------------------------------------------------------- drill-down
export function drill(spec) {
	if (!spec) return;
	const clean = {};
	Object.entries(spec.filters || {}).forEach(([k, v]) => {
		if (v !== null && v !== undefined && v !== "") clean[k] = v;
	});
	if (spec.type === "list") {
		frappe.route_options = clean;
		frappe.set_route("List", spec.doctype, "List");
	} else if (spec.type === "report") {
		frappe.route_options = clean;
		frappe.set_route("query-report", spec.report);
	} else if (spec.type === "form") {
		frappe.set_route("Form", spec.doctype, spec.name);
	} else if (spec.type === "route") {
		frappe.set_route(...spec.route);
	}
}

export const listSpec = (doctype, filters) => ({ type: "list", doctype, filters });
export const reportSpec = (report, filters) => ({ type: "report", report, filters });
export const formSpec = (doctype, name) => ({ type: "form", doctype, name });

// --------------------------------------------------------------------------- palette
const PALETTES = {
	light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
	dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
};
export const isDark = () => document.documentElement.getAttribute("data-theme") === "dark";
export const palette = (n) => PALETTES[isDark() ? "dark" : "light"].slice(0, n || 8);
export const series = (i) => PALETTES[isDark() ? "dark" : "light"][i % 8];
export const STATUS = { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" };

// ------------------------------------------------------------------- state components
export function skeleton(kind = "dashboard") {
	const card = '<div class="bid-skel bid-skel-card"></div>';
	const panel = '<div class="bid-skel bid-skel-panel"></div>';
	return `<div class="bid-skeleton" aria-busy="true" aria-label="${__("Loading")}">
		<div class="bid-skel-row">${card.repeat(kind === "dashboard" ? 8 : 4)}</div>
		<div class="bid-skel-row two">${panel.repeat(2)}</div>
		<div class="bid-skel-row two">${panel.repeat(2)}</div></div>`;
}

export function emptyHtml(message, iconName = "info") {
	return `<div class="bid-empty">${icon(iconName, 28)}<p>${message}</p></div>`;
}

export function errorHtml(message, withRetry = true) {
	return `<div class="bid-error" role="alert">${icon("alert-triangle", 28)}
		<p>${message}</p>${withRetry ? `<button class="btn btn-default btn-sm bid-retry">${icon("refresh-cw", 14)} ${__("Retry")}</button>` : ""}</div>`;
}

export function lockedHtml(message) {
	return `<div class="bid-empty bid-locked">${icon("lock", 28)}<p>${esc(message)}</p></div>`;
}

// ------------------------------------------------------------------------------ panels
export class Panels {
	/** A responsive 12-column grid that hands out panel bodies. */
	constructor(container, cls = "") {
		this.grid = document.createElement("div");
		this.grid.className = `bid-grid ${cls}`;
		container.appendChild(this.grid);
	}

	heading(text) {
		const h = document.createElement("h3");
		h.className = "bid-group-title";
		h.textContent = text;
		this.grid.appendChild(h);
	}

	panel({ title, sub = "", span = 6, tools = "", cls = "" }) {
		const el = document.createElement("section");
		el.className = `bid-panel span-${span} ${cls}`;
		el.innerHTML = `<header class="bid-panel-head"><div><h4>${esc(title)}</h4>${sub ? `<p>${sub}</p>` : ""}</div><div class="bid-panel-tools">${tools}</div></header><div class="bid-panel-body"></div>`;
		this.grid.appendChild(el);
		return el.querySelector(".bid-panel-body");
	}
}

export function kpiStrip(container, items, cls = "") {
	const wrap = document.createElement("div");
	wrap.className = `bid-kpis ${cls}`;
	wrap.innerHTML = items.map((k, i) => miniKpi(k, i)).join("");
	container.appendChild(wrap);
	wrap.querySelectorAll("[data-i]").forEach((el) => {
		const item = items[el.dataset.i];
		if (item.route) el.addEventListener("click", () => drill(item.route));
	});
	return wrap;
}

function miniKpi(k, i) {
	const tone = k.tone ? ` tone-${k.tone}` : "";
	const tag = k.route ? "button" : "div";
	const d = k.delta != null ? deltaChip(k.delta, k.good || "up") : "";
	return `<${tag} class="bid-kpi${tone}${k.route ? " clickable" : ""}" data-i="${i}" ${k.title ? `title="${esc(k.title)}"` : ""}>
		<span class="bid-kpi-label">${esc(k.label)}</span>
		<span class="bid-kpi-value">${k.value}</span>
		<span class="bid-kpi-sub">${d}${k.sub ? `<span>${k.sub}</span>` : ""}</span></${tag}>`;
}

export function deltaChip(growth, good = "up") {
	if (growth == null) return `<span class="bid-delta flat" title="${__("No previous-period data to compare")}">${icon("minus", 12)} ${__("n/a")}</span>`;
	const up = growth > 0;
	const flat = Math.abs(growth) < 0.005;
	let tone = "flat";
	if (!flat && good !== "neutral") tone = (up && good === "up") || (!up && good === "down") ? "pos" : "neg";
	const arrow = flat ? "minus" : up ? "arrow-up" : "arrow-down";
	return `<span class="bid-delta ${tone}">${icon(arrow, 12)} ${Math.abs(growth).toFixed(1)}%</span>`;
}

// ----------------------------------------------------------------------------- charts
function chartOptions(el, cfg) {
	const dark = isDark();
	const fmt = cfg.fmt || ((v) => money(v));
	const n = cfg.datasets ? cfg.datasets.length : 1;
	return {
		// NB: no DOM node in the options - frappe-charts deep-clones them and recurses forever
		data: {
			labels: cfg.labels,
			datasets: cfg.datasets.map((d) => ({ name: d.name, values: d.values, chartType: d.chartType })),
		},
		type: cfg.type || "bar",
		height: cfg.height || 260,
		colors: cfg.colors || palette(Math.max(n, cfg.type === "donut" || cfg.type === "pie" ? cfg.labels.length : 1)),
		axisOptions: { xIsSeries: cfg.xIsSeries !== false, shortenYAxisNumbers: false, xAxisMode: cfg.xAxisMode || "tick" },
		barOptions: { spaceRatio: 0.45, stacked: cfg.stacked ? 1 : 0 },
		lineOptions: { regionFill: cfg.area ? 1 : 0, hideDots: cfg.hideDots ? 1 : 0, dotSize: 4, heatline: 0 },
		tooltipOptions: { formatTooltipY: (d) => fmt(d), formatTooltipX: (d) => d },
		isNavigable: false,
		// the library's draw animation runs on timers that throw if the section is swapped meanwhile
		animate: 0,
		maxSlices: 8,
		truncateLegends: true,
		valuesOverPoints: 0,
		_dark: dark,
	};
}

function pickUnit(maxAbs) {
	if (state.currency === "INR") {
		if (maxAbs >= 1e7) return [1e7, "Cr"];
		if (maxAbs >= 1e5) return [1e5, "L"];
		if (maxAbs >= 1e3) return [1e3, "K"];
		return [1, ""];
	}
	if (maxAbs >= 1e9) return [1e9, "B"];
	if (maxAbs >= 1e6) return [1e6, "M"];
	if (maxAbs >= 1e3) return [1e3, "K"];
	return [1, ""];
}

/** Render a frappe-charts chart inside ``el`` with an accessible data-table toggle. */
export function chart(el, cfg) {
	const total = (cfg.datasets || []).reduce((s, d) => s + d.values.reduce((a, b) => a + Math.abs(b || 0), 0), 0);
	if (!cfg.labels || !cfg.labels.length || !total) {
		el.innerHTML = emptyHtml(cfg.emptyText || __("No data for the selected filters."), "bar-chart-2");
		return null;
	}
	el.innerHTML = "";
	// Money axes are drawn in Cr / L / K (or M / K) so the tick labels stay short; tooltips and the
	// table view keep the full value.
	let drawCfg = cfg;
	const isMoney = !cfg.fmt && cfg.type !== "donut" && cfg.type !== "pie";
	if (isMoney) {
		const [div, unit] = pickUnit(Math.max(...cfg.datasets.flatMap((d) => d.values.map((v) => Math.abs(v || 0)))));
		if (div > 1) {
			const caption = document.createElement("div");
			caption.className = "bid-unit";
			caption.textContent = `${state.symbol} ${__("in")} ${unit}`;
			el.appendChild(caption);
			drawCfg = { ...cfg, datasets: cfg.datasets.map((d) => ({ ...d, values: d.values.map((v) => (v || 0) / div) })), fmt: (v) => money(v * div) };
		}
	}
	const holder = document.createElement("div");
	holder.className = "bid-chart";
	el.appendChild(holder);
	let instance;
	try {
		const opts = chartOptions(holder, drawCfg);
		delete opts._dark;
		instance = new frappe.Chart(holder, opts);
		instance.holder = holder;
	} catch (e) {
		console.error("[bid] chart failed", e);
		el.innerHTML = errorHtml(__("This chart could not be drawn."), false);
		return null;
	}
	if (cfg.onSelect) {
		// frappe-charts' own "navigable" mode throws on some datasets, so drill via the marks' index attribute
		holder.classList.add("navigable");
		holder.addEventListener("click", (e) => {
			const mark = e.target.closest("[data-point-index]");
			if (mark) cfg.onSelect(parseInt(mark.getAttribute("data-point-index"), 10), e);
		});
	}
	attachTableToggle(el, cfg);
	return instance;
}

function attachTableToggle(body, cfg) {
	const panel = body.closest(".bid-panel");
	const tools = panel && panel.querySelector(".bid-panel-tools");
	if (!tools || tools.querySelector(".bid-toggle-table")) return;
	const btn = document.createElement("button");
	btn.className = "bid-icon-btn bid-toggle-table";
	btn.title = __("Show as table");
	btn.setAttribute("aria-label", __("Show as table"));
	btn.innerHTML = icon("table", 15);
	let showing = false;
	let chartHtml = null;
	btn.addEventListener("click", () => {
		showing = !showing;
		btn.classList.toggle("active", showing);
		if (showing) {
			chartHtml = body.innerHTML;
			const fmt = cfg.fmt || ((v) => money(v));
			body.innerHTML = `<div class="bid-table-wrap"><table class="bid-table"><thead><tr><th></th>${cfg.datasets
				.map((d) => `<th class="num">${esc(d.name || "")}</th>`)
				.join("")}</tr></thead><tbody>${cfg.labels
				.map((l, i) => `<tr><td>${esc(l)}</td>${cfg.datasets.map((d) => `<td class="num">${esc(fmt(d.values[i]))}</td>`).join("")}</tr>`)
				.join("")}</tbody></table></div>`;
		} else {
			chart(body, cfg);
		}
	});
	tools.prepend(btn);
}

/** Clickable horizontal bar list (top-N style). rows: [{label, value, sub, route}] */
export function hbars(el, rows, { fmt = money, color = 0, emptyText } = {}) {
	if (!rows || !rows.length) {
		el.innerHTML = emptyHtml(emptyText || __("No data for the selected filters."), "bar-chart-2");
		return;
	}
	const max = Math.max(...rows.map((r) => Math.abs(r.value))) || 1;
	el.innerHTML = `<ul class="bid-hbars">${rows
		.map(
			(r, i) => `<li><button class="bid-hbar${r.route ? " clickable" : ""}" data-i="${i}" title="${esc(r.label)}: ${esc(moneyFullSafe(r.value, fmt))}">
			<span class="bid-hbar-label">${esc(r.label)}${r.sub ? `<small>${esc(r.sub)}</small>` : ""}</span>
			<span class="bid-hbar-track"><span class="bid-hbar-fill" style="width:${Math.max((Math.abs(r.value) / max) * 100, 1.5)}%;background:${series(color)}"></span></span>
			<span class="bid-hbar-value">${esc(fmt(r.value))}</span></button></li>`
		)
		.join("")}</ul>`;
	el.querySelectorAll(".bid-hbar").forEach((b) => {
		const row = rows[b.dataset.i];
		if (row.route) b.addEventListener("click", () => drill(row.route));
	});
}

const moneyFullSafe = (v, fmt) => (fmt === money ? moneyFull(v) : fmt(v));

/** Data table. cols: [{key,label,align,fmt,link(row)->spec}] */
export function table(el, cols, rows, { emptyText, max = 200, footer } = {}) {
	if (!rows || !rows.length) {
		el.innerHTML = emptyHtml(emptyText || __("Nothing to show."), "check-circle");
		return;
	}
	const head = cols.map((c) => `<th class="${c.align === "right" ? "num" : ""}">${esc(c.label)}</th>`).join("");
	const body = rows
		.slice(0, max)
		.map(
			(r, ri) => `<tr class="${r._cls || ""}">${cols
				.map((c) => {
					const raw = c.fmt ? c.fmt(r[c.key], r) : r[c.key];
					const text = c.html ? raw : esc(raw == null ? "" : raw);
					const cell = c.link && r[c.key] != null ? `<a href="#" class="bid-link" data-r="${ri}" data-c="${c.key}">${text}</a>` : text;
					return `<td class="${c.align === "right" ? "num" : ""}" style="${r._indent && c.first ? `padding-left:${8 + r._indent * 16}px` : ""}">${cell}</td>`;
				})
				.join("")}</tr>`
		)
		.join("");
	el.innerHTML = `<div class="bid-table-wrap"><table class="bid-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody>${footer ? `<tfoot>${footer}</tfoot>` : ""}</table></div>${
		rows.length > max ? `<p class="bid-note">${__("Showing first {0} of {1} rows.", [max, rows.length])}</p>` : ""
	}`;
	el.querySelectorAll("a.bid-link").forEach((a) => {
		a.addEventListener("click", (e) => {
			e.preventDefault();
			const col = cols.find((c) => c.key === a.dataset.c);
			drill(col.link(rows[a.dataset.r]));
		});
	});
}

export function note(el, text, tone = "info") {
	const p = document.createElement("p");
	p.className = `bid-note tone-${tone}`;
	p.innerHTML = `${icon("info", 14)} ${text}`;
	el.appendChild(p);
}

export function statusBadge(sev) {
	const map = { critical: ["x-circle", __("Critical")], warning: ["alert-triangle", __("Warning")], ok: ["check-circle", __("OK")], info: ["info", __("Info")] };
	const [i, label] = map[sev] || map.info;
	return `<span class="bid-badge sev-${sev}">${icon(i, 13)} ${label}</span>`;
}
