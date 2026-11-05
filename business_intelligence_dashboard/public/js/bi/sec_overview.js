// Executive dashboard and Business Insights sections.
import {
	Panels, chart, deltaChip, drill, esc, fmtValue, hbars, icon, listSpec, money, moneyFull, monthRange, note, reportSpec, series, statusBadge,
} from "./core.js";

const GROUPS = [
	["financial", __("Financial Performance")],
	["sales", __("Sales")],
	["purchase", __("Purchases")],
	["cash", __("Cash & Bank")],
];

export function kpiCards(container, cards) {
	const wrap = document.createElement("div");
	wrap.className = "bid-cards";
	wrap.innerHTML = cards
		.map((c, i) => {
			const value = fmtValue(c.format, c.value);
			const prev = c.previous == null ? "" : `<span class="bid-card-prev" title="${__("Previous period")}">${__("vs")} ${esc(fmtValue(c.format, c.previous))}</span>`;
			const delta = deltaChip(c.growth, c.good);
			const full = c.format === "currency" && c.value != null ? moneyFull(c.value) : value;
			return `<button class="bid-card" data-i="${i}" style="--i:${i}" title="${esc(full)}${c.hint ? " — " + esc(c.hint) : ""}">
				<span class="bid-card-top"><span class="bid-card-icon">${icon(c.icon, 18)}</span><span class="bid-card-label">${esc(c.label)}</span></span>
				<span class="bid-card-value">${esc(value)}</span>
				<span class="bid-card-foot">${c.key === "sales_growth" ? `<span class="bid-card-prev">${esc(c.hint || "")}</span>` : `${delta}${prev}`}</span></button>`;
		})
		.join("");
	container.appendChild(wrap);
	wrap.querySelectorAll(".bid-card").forEach((b) => b.addEventListener("click", () => drill(cards[b.dataset.i].route)));
}

export function renderExecutive(el, d, ctx) {
	const f = ctx.f;
	GROUPS.forEach(([key, title]) => {
		const cards = d.cards.filter((c) => c.group === key);
		if (!cards.length) return;
		const h = document.createElement("h3");
		h.className = "bid-group-title";
		h.textContent = title;
		el.appendChild(h);
		kpiCards(el, cards);
	});
	if (d.restricted && d.restricted.length) {
		note(el, __("Some sections are hidden because your role does not have read access to the underlying records."), "warn");
	}

	const P = new Panels(el);
	const c = d.charts || {};
	if (c.income_vs_expense) {
		chart(P.panel({ title: __("Income vs Expenses"), sub: __("Monthly, from the Profit & Loss engine. Click a month to open the report."), span: 6 }), {
			labels: c.income_vs_expense.labels,
			datasets: [
				{ name: __("Income"), values: c.income_vs_expense.income },
				{ name: __("Expenses"), values: c.income_vs_expense.expense },
			],
			type: "bar",
			colors: [series(0), series(1)],
			onSelect: (i) => {
				const r = monthRange(c.income_vs_expense.labels[i]);
				if (r) drill(reportSpec("Profit and Loss Statement", { company: f.company, period_start_date: r[0], period_end_date: r[1], periodicity: "Monthly", filter_based_on: "Date Range" }));
			},
		});
		chart(P.panel({ title: __("Net Profit Trend"), sub: __("Income minus all expenses, per month"), span: 6 }), {
			labels: c.profit_trend.labels,
			datasets: [{ name: __("Net profit"), values: c.profit_trend.values }],
			type: "line",
			area: true,
			colors: [series(0)],
		});
	}
	if (c.sales_vs_purchase) {
		chart(P.panel({ title: __("Sales vs Purchases"), sub: __("Net invoiced value, before tax"), span: 6 }), {
			labels: c.sales_vs_purchase.labels,
			datasets: [
				{ name: __("Sales"), values: c.sales_vs_purchase.sales },
				{ name: __("Purchases"), values: c.sales_vs_purchase.purchases },
			],
			type: "bar",
			colors: [series(0), series(1)],
		});
	}
	if (c.cash_flow) {
		chart(P.panel({ title: __("Cash Inflow vs Outflow"), sub: __("From Cash and Bank account postings"), span: 6 }), {
			labels: c.cash_flow.labels,
			datasets: [
				{ name: __("Inflow"), values: c.cash_flow.inflow },
				{ name: __("Outflow"), values: c.cash_flow.outflow },
			],
			type: "bar",
			colors: [series(2), series(1)],
		});
	}
	if (c.top_customers) {
		hbars(
			P.panel({ title: __("Top Customers"), sub: __("Click a customer to open their invoices"), span: 6 }),
			c.top_customers.map((r) => ({
				...r,
				route: listSpec("Sales Invoice", { company: f.company, docstatus: 1, customer_name: r.label, posting_date: ["Between", [f.from_date, f.to_date]] }),
			}))
		);
	}
}

// ------------------------------------------------------------------------ insights
const SEV_ICON = { critical: "x-circle", warning: "alert-triangle", ok: "check-circle", info: "info" };

export function renderInsights(el, d, ctx) {
	const counts = d.counts || {};
	const head = document.createElement("div");
	head.className = "bid-insight-summary";
	head.innerHTML = `<span>${statusBadge("critical")} <b>${counts.critical || 0}</b></span><span>${statusBadge("warning")} <b>${counts.warning || 0}</b></span><span>${statusBadge("ok")} <b>${counts.ok || 0}</b></span>
		${ctx.canConfigure ? `<button class="btn btn-default btn-sm bid-open-settings">${icon("settings", 14)} ${__("Configure thresholds")}</button>` : ""}`;
	el.appendChild(head);
	const btn = head.querySelector(".bid-open-settings");
	if (btn) btn.addEventListener("click", () => frappe.set_route("Form", "BI Dashboard Settings"));

	const list = document.createElement("div");
	list.className = "bid-alerts";
	list.innerHTML = d.alerts
		.map(
			(a, i) => `<article class="bid-alert sev-${a.severity}">
			<header><span class="bid-alert-icon">${icon(SEV_ICON[a.severity] || "info", 20)}</span>
				<div><h4>${esc(a.title)}</h4><p>${a.restricted ? esc(a.message) : esc(a.message)}</p></div>
				<div class="bid-alert-meta">${statusBadge(a.severity)}${a.amount != null && a.count ? `<b title="${esc(moneyFull(a.amount))}">${esc(money(a.amount))}</b>` : ""}</div></header>
			${
				a.rows && a.rows.length
					? `<ul class="bid-alert-rows">${a.rows
							.map((r) => `<li><span>${esc(r.label)}${r.detail ? `<small>${esc(r.detail)}</small>` : ""}</span><span>${r.value != null ? esc(typeof r.value === "number" ? money(r.value) : r.value) : ""}${r.days ? `<small>${__("{0} days", [r.days])}</small>` : ""}</span></li>`)
							.join("")}</ul>`
					: ""
			}
			${a.route && !a.restricted ? `<button class="bid-alert-open" data-i="${i}">${__("Open")} ${icon("external-link", 13)}</button>` : ""}</article>`
		)
		.join("");
	el.appendChild(list);
	list.querySelectorAll(".bid-alert-open").forEach((b) => b.addEventListener("click", () => drill(d.alerts[b.dataset.i].route)));
	note(el, __("Thresholds come from BI Dashboard Settings. Alerts use live records for the selected company and period."));
}
