// Sales, Purchase, Receivables and Payables sections.
import {
	Panels, chart, drill, esc, formSpec, hbars, kpiStrip, listSpec, money, moneyFull, monthRange, note, num, pct, reportSpec, series, table, emptyHtml,
} from "./core.js";

const share = (rows, n = 7) => {
	const top = rows.slice(0, n);
	const rest = rows.slice(n).reduce((s, r) => s + Math.max(r.value, 0), 0);
	const out = top.map((r) => ({ label: r.label, value: Math.max(r.value, 0) }));
	if (rest > 0) out.push({ label: __("Others"), value: rest });
	return out;
};

function donut(body, rows, onSelect, fmt = money) {
	const data = share(rows);
	chart(body, { labels: data.map((r) => r.label), datasets: [{ values: data.map((r) => r.value) }], type: "donut", height: 260, fmt, onSelect: onSelect ? (i) => onSelect(data[i]) : null });
}

const kpi = (label, k, extra = {}) => ({ label, value: money(k.value), delta: k.growth, sub: k.previous != null ? `${__("vs")} ${money(k.previous)}` : "", title: moneyFull(k.value), ...extra });
const kpiN = (label, k, extra = {}) => ({ label, value: num(k.value), delta: k.growth, sub: k.previous != null ? `${__("vs")} ${num(k.previous)}` : "", ...extra });

const datedFilters = (f, extra = {}, field = "posting_date") => ({ company: f.company, docstatus: 1, [field]: ["Between", [f.from_date, f.to_date]], ...extra });

// ------------------------------------------------------------------------------- Sales
export function renderSales(el, d, ctx) {
	const f = ctx.f;
	const R = d.routes;
	kpiStrip(el, [
		kpi(__("Net Sales"), d.kpis.net_sales, { route: R.invoices }),
		kpiN(__("Sales Invoices"), d.kpis.invoices, { route: R.invoices }),
		kpiN(__("Sales Orders"), d.kpis.orders, { route: R.orders }),
		kpi(__("Sales Returns"), { ...d.kpis.returns, value: Math.abs(d.kpis.returns.value), previous: Math.abs(d.kpis.returns.previous || 0) }, { route: R.returns, good: "down" }),
	]);
	const P = new Panels(el);

	chart(P.panel({ title: __("Monthly Sales Trend"), sub: __("Click a month to open its invoices"), span: 8 }), {
		labels: d.monthly.labels, datasets: [{ name: __("Sales"), values: d.monthly.values }], type: "bar", colors: [series(0)],
		onSelect: (i) => { const r = monthRange(d.monthly.labels[i]); if (r) drill(listSpec("Sales Invoice", datedFilters({ company: f.company, from_date: r[0], to_date: r[1] }))); },
	});
	chart(P.panel({ title: __("Year-wise Comparison"), sub: __("Fiscal years, month by month"), span: 4 }), {
		labels: d.yearly.labels, datasets: d.yearly.series.map((s) => ({ name: s.name, values: s.values })), type: "line", hideDots: false,
		emptyText: __("Only one fiscal year has sales so far."),
	});
	chart(P.panel({ title: __("Daily Sales Trend"), sub: __("Net sales per day"), span: 12 }), {
		labels: d.daily.labels, datasets: [{ name: __("Sales"), values: d.daily.values }], type: "line", area: true, hideDots: d.daily.labels.length > 45, colors: [series(0)], xAxisMode: "span",
		onSelect: (i) => drill(listSpec("Sales Invoice", { company: f.company, docstatus: 1, posting_date: d.daily.labels[i] })),
	});

	donut(P.panel({ title: __("Sales by Customer"), sub: __("Share of net sales"), span: 4 }), d.by_customer, (r) => r.label !== __("Others") && drill(listSpec("Sales Invoice", datedFilters(f, { customer_name: r.label }))));
	hbars(
		P.panel({ title: __("Top 10 Customers"), span: 4 }),
		d.top_customers.map((r) => ({ label: r.label, value: r.value, route: listSpec("Sales Invoice", datedFilters(f, { customer: r.name })) }))
	);
	donut(P.panel({ title: __("Territory-wise Sales"), span: 4 }), d.by_territory, (r) => r.label !== __("Others") && r.label !== "Not set" && drill(listSpec("Sales Invoice", datedFilters(f, { territory: r.label }))));

	donut(P.panel({ title: __("Sales by Item"), sub: __("Share of net sales"), span: 4 }), d.by_item, null);
	hbars(
		P.panel({ title: __("Top 10 Selling Items"), span: 4 }),
		d.top_items.map((r) => ({ label: r.label, value: r.value, route: reportSpec("Item-wise Sales Register", { company: f.company, from_date: f.from_date, to_date: f.to_date, item_code: r.name }) }))
	);
	donut(P.panel({ title: __("Sales by Item Group"), span: 4 }), d.by_item_group, (r) => r.label !== __("Others") && drill(reportSpec("Item-wise Sales Register", { company: f.company, from_date: f.from_date, to_date: f.to_date, item_group: r.label })));

	hbars(P.panel({ title: __("Salesperson Performance"), sub: __("Allocated invoice value from the Sales Team"), span: 6 }), d.by_sales_person, { emptyText: __("No invoices carry a Sales Team in this period.") });
	const tb = P.panel({ title: __("Salesperson Target vs Achievement"), span: 6 });
	if (d.target_vs_achievement.rows.length) {
		const t = d.target_vs_achievement.rows;
		chart(tb, { labels: t.map((r) => r.label), datasets: [{ name: __("Target"), values: t.map((r) => r.target) }, { name: __("Achieved"), values: t.map((r) => r.achieved) }], type: "bar", colors: [series(3), series(0)] });
	} else {
		tb.innerHTML = emptyHtml(esc(d.target_vs_achievement.note || __("No targets defined.")), "info");
	}

	donut(P.panel({ title: __("Sales Order Status"), span: 4 }), d.so_status.map((r) => ({ label: `${r.label} (${r.count})`, value: r.count })), (r) => drill(listSpec("Sales Order", { company: f.company, docstatus: 1, status: r.label.replace(/ \(\d+\)$/, "") })), num);
	donut(P.panel({ title: __("Sales Invoice Status"), span: 4 }), d.si_status.map((r) => ({ label: `${r.label} (${r.count})`, value: r.count })), (r) => drill(listSpec("Sales Invoice", datedFilters(f, { status: r.label.replace(/ \(\d+\)$/, "") }))), num);
	const ret = P.panel({ title: __("Sales Returns"), sub: `${__("Return rate")} ${pct(d.returns.rate_percent)} · ${d.returns.count} ${__("credit notes")}`, span: 4 });
	chart(ret, { labels: d.returns.monthly.labels, datasets: [{ name: __("Returns"), values: d.returns.monthly.values }], type: "bar", colors: [series(1)], height: 220, emptyText: __("No sales returns in this period.") });

	const pd = P.panel({ title: __("Pending Delivery Analysis"), sub: `${__("Undelivered value")}: <b>${esc(money(d.pending_delivery_total))}</b>`, span: 8 });
	table(pd, [
		{ key: "name", label: __("Sales Order"), link: (r) => formSpec("Sales Order", r.name) },
		{ key: "customer", label: __("Customer") },
		{ key: "delivery_date", label: __("Delivery Date") },
		{ key: "days_late", label: __("Days Late"), align: "right", fmt: (v) => (v ? v : "—") },
		{ key: "pending_qty", label: __("Pending Qty"), align: "right", fmt: (v) => num(v, 2) },
		{ key: "pending_value", label: __("Pending Value"), align: "right", fmt: (v) => money(v) },
	], d.pending_delivery, { emptyText: __("No undelivered sales orders."), max: 15 });
	const rc = P.panel({ title: __("Returns by Customer"), span: 4 });
	hbars(rc, d.returns.by_customer.map((r) => ({ label: r.label, value: r.value, sub: `${r.count} ${__("returns")}` })), { color: 1, emptyText: __("No sales returns in this period.") });
}

// --------------------------------------------------------------------------- Purchases
export function renderPurchase(el, d, ctx) {
	const f = ctx.f;
	const R = d.routes;
	kpiStrip(el, [
		kpi(__("Net Purchases"), d.kpis.net_purchases, { route: R.invoices, good: "neutral" }),
		kpiN(__("Purchase Invoices"), d.kpis.invoices, { route: R.invoices, good: "neutral" }),
		kpiN(__("Purchase Orders"), d.kpis.orders, { route: R.orders, good: "neutral" }),
		kpi(__("Purchase Returns"), { ...d.kpis.returns, value: Math.abs(d.kpis.returns.value), previous: Math.abs(d.kpis.returns.previous || 0) }, { route: R.returns, good: "neutral" }),
	]);
	const P = new Panels(el);
	chart(P.panel({ title: __("Monthly Purchase Trend"), sub: __("Click a month to open its invoices"), span: 8 }), {
		labels: d.monthly.labels, datasets: [{ name: __("Purchases"), values: d.monthly.values }], type: "bar", colors: [series(1)],
		onSelect: (i) => { const r = monthRange(d.monthly.labels[i]); if (r) drill(listSpec("Purchase Invoice", datedFilters({ company: f.company, from_date: r[0], to_date: r[1] }))); },
	});
	chart(P.panel({ title: __("Sales vs Purchases"), span: 4 }), {
		labels: d.sales_vs_purchase.labels, datasets: [{ name: __("Sales"), values: d.sales_vs_purchase.sales }, { name: __("Purchases"), values: d.sales_vs_purchase.purchases }], type: "line", colors: [series(0), series(1)],
	});
	donut(P.panel({ title: __("Purchase by Supplier"), span: 4 }), d.by_supplier, null);
	hbars(
		P.panel({ title: __("Top 10 Suppliers"), span: 4 }),
		d.top_suppliers.map((r) => ({ label: r.label, value: r.value, route: listSpec("Purchase Invoice", datedFilters(f, { supplier: r.name })) })),
		{ color: 1 }
	);
	donut(P.panel({ title: __("Purchase by Item Group"), span: 4 }), d.by_item_group, null);

	donut(P.panel({ title: __("Purchase Order Status"), span: 4 }), d.po_status.map((r) => ({ label: `${r.label} (${r.count})`, value: r.count })), (r) => drill(listSpec("Purchase Order", { company: f.company, docstatus: 1, status: r.label.replace(/ \(\d+\)$/, "") })), num);
	donut(P.panel({ title: __("Purchase Invoice Status"), span: 4 }), d.pi_status.map((r) => ({ label: `${r.label} (${r.count})`, value: r.count })), (r) => drill(listSpec("Purchase Invoice", datedFilters(f, { status: r.label.replace(/ \(\d+\)$/, "") }))), num);
	donut(P.panel({ title: __("Purchase Receipt Analysis"), sub: `${d.receipts.count} ${__("receipts")} · ${money(d.receipts.value)}`, span: 4 }), d.receipts.status.map((r) => ({ label: `${r.label} (${r.count})`, value: r.count })), (r) => drill(listSpec("Purchase Receipt", datedFilters(f, { status: r.label.replace(/ \(\d+\)$/, "") }))), num);

	table(P.panel({ title: __("Pending Purchase Orders"), sub: `${__("Pending value")}: <b>${esc(money(d.pending_po_total))}</b>`, span: 6 }), [
		{ key: "name", label: __("Purchase Order"), link: (r) => formSpec("Purchase Order", r.name) },
		{ key: "supplier", label: __("Supplier") },
		{ key: "schedule_date", label: __("Due") },
		{ key: "days_late", label: __("Days Late"), align: "right", fmt: (v) => (v ? v : "—") },
		{ key: "pending_value", label: __("Pending"), align: "right", fmt: (v) => money(v) },
	], d.pending_po, { emptyText: __("No pending purchase orders."), max: 12 });
	table(P.panel({ title: __("Goods Received but Not Invoiced"), sub: `${__("Unbilled value")}: <b>${esc(money(d.grni.total))}</b>`, span: 6 }), [
		{ key: "name", label: __("Receipt"), link: (r) => formSpec("Purchase Receipt", r.name) },
		{ key: "supplier", label: __("Supplier") },
		{ key: "posting_date", label: __("Date") },
		{ key: "unbilled", label: __("Unbilled"), align: "right", fmt: (v) => money(v) },
	], d.grni.rows, { emptyText: __("All received goods are invoiced."), max: 12 });

	chart(P.panel({ title: __("Purchase Receipts"), sub: __("Received value per month"), span: 6 }), { labels: d.receipts.monthly.labels, datasets: [{ name: __("Received"), values: d.receipts.monthly.values }], type: "bar", colors: [series(2)] });
	const ret = P.panel({ title: __("Purchase Returns"), sub: `${d.returns.count} ${__("debit notes")} · ${money(d.returns.amount)}`, span: 6 });
	chart(ret, { labels: d.returns.monthly.labels, datasets: [{ name: __("Returns"), values: d.returns.monthly.values }], type: "bar", colors: [series(1)], height: 220, emptyText: __("No purchase returns in this period.") });
}

// ---------------------------------------------------------------- Receivables / Payables
export function renderOutstanding(el, d, ctx, kind) {
	const f = ctx.f;
	const isAR = kind === "receivables";
	const partyType = isAR ? "Customer" : "Supplier";
	const reportName = isAR ? "Accounts Receivable" : "Accounts Payable";
	const baseFilters = { company: f.company, report_date: f.to_date, ageing_based_on: "Due Date", party_type: partyType };
	const open = reportSpec(reportName, baseFilters);
	const overdueSpec = d.routes.overdue;

	const strip = [
		{ label: __("Total Outstanding"), value: money(d.total_outstanding), title: moneyFull(d.total_outstanding), route: open, sub: `${d.party_count} ${isAR ? __("customers") : __("suppliers")}` },
		{ label: __("Not Due"), value: money(d.not_due), tone: "good", route: open, title: moneyFull(d.not_due) },
		{ label: __("Overdue"), value: money(d.overdue), tone: d.overdue > 0 ? "bad" : "good", route: overdueSpec, sub: `${pct(d.overdue_percent)} ${__("of outstanding")}`, title: moneyFull(d.overdue) },
	];
	if (isAR) strip.push({ label: __("Avg. Collection Period"), value: d.average_collection_period.days != null ? `${d.average_collection_period.days} ${__("days")}` : "—", sub: __("DSO"), title: d.average_collection_period.basis });
	else strip.push({ label: __("Due in next 30 days"), value: money(d.schedule.values.slice(0, 3).reduce((a, b) => a + b, 0)), tone: "warn", title: __("Outstanding that falls due within 30 days of the To Date") });
	kpiStrip(el, strip);

	const P = new Panels(el);
	chart(P.panel({ title: __("Ageing"), sub: __("As on {0}. The 0-30 bucket includes amounts not yet due, as in the standard report.", [frappe.datetime.str_to_user(f.to_date)]), span: 6 }), {
		labels: d.ageing.labels, datasets: [{ name: __("Outstanding"), values: d.ageing.values }], type: "bar", colors: [series(isAR ? 0 : 1)], onSelect: () => drill(open),
	});
	hbars(
		P.panel({ title: isAR ? __("Top 10 Outstanding Customers") : __("Top 10 Outstanding Suppliers"), sub: __("Click to open the ageing report"), span: 6 }),
		d.top_parties.map((r) => ({ label: r.party, value: r.outstanding, route: reportSpec(reportName, { ...baseFilters, party: [r.party] }) })),
		{ color: isAR ? 0 : 1 }
	);
	if (isAR) {
		chart(P.panel({ title: __("Monthly Collection Trend"), sub: __("Payments received from customers"), span: 6 }), {
			labels: d.collection_trend.labels, datasets: [{ name: __("Collected"), values: d.collection_trend.values }], type: "line", area: true, colors: [series(2)],
		});
	}
	chart(P.panel({ title: isAR ? __("Expected Collections") : __("Upcoming Payment Obligations"), sub: __("Open invoices by due date, from the To Date"), span: 6 }), {
		labels: d.schedule.labels, datasets: [{ name: __("Due"), values: d.schedule.values }], type: "bar", colors: [series(isAR ? 2 : 3)], emptyText: __("Nothing falls due in the next 60 days."),
	});

	const cols = [
		{ key: "voucher_no", label: __("Invoice"), link: (r) => formSpec(r.voucher_type, r.voucher_no) },
		{ key: "party", label: isAR ? __("Customer") : __("Supplier") },
		{ key: "due_date", label: __("Due Date") },
		{ key: "days", label: __("Days"), align: "right" },
		{ key: "outstanding", label: __("Outstanding"), align: "right", fmt: (v) => money(v) },
	];
	table(P.panel({ title: __("Overdue Invoices"), sub: __("Oldest first (up to 100)"), span: 6 }), cols, d.overdue_invoices, { emptyText: __("No overdue invoices."), max: 12 });
	table(P.panel({ title: __("Upcoming Due"), sub: __("Not yet due, earliest first"), span: 6 }), cols, d.upcoming_invoices, { emptyText: __("Nothing upcoming."), max: 12 });
	note(el, __("Outstanding amounts come from ERPNext's {0} report engine (Payment Ledger), so allocations, credit notes, returns and advances are already netted.", [reportName]));
}
