// Accounting analytics, Financial Statements, Cash Flow & Banking, Inventory and GST sections.
import {
	Panels, api, chart, drill, emptyHtml, errorHtml, esc, formSpec, hbars, icon, kpiStrip, listSpec, money, moneyFull, monthRange, note, num, pct, reportSpec, series, table, fmtValue,
} from "./core.js";

const glSpec = (f, account) => reportSpec("General Ledger", { company: f.company, from_date: f.from_date, to_date: f.to_date, account: [account] });

const mk = (label, m, kind = "currency", good = "up", extra = {}) => ({
	label,
	value: fmtValue(kind, m.value),
	delta: m.growth,
	good,
	sub: m.previous != null ? `${__("vs")} ${fmtValue(kind, m.previous)}` : "",
	title: kind === "currency" && m.value != null ? moneyFull(m.value) : "",
	...extra,
});

function donutRows(body, labels, values, fmt = money) {
	chart(body, { labels, datasets: [{ values: values.map((v) => Math.max(v, 0)) }], type: "donut", height: 250, fmt });
}

// ------------------------------------------------------------------------- Accounting
export function renderAccounting(el, d, ctx) {
	const f = ctx.f;
	const pl = d.profit_and_loss, bs = d.balance_sheet, gl = d.general_ledger, ex = d.expenses;
	const M = pl.metrics;
	const P = new Panels(el);

	P.heading(__("Profit & Loss"));
	kpiStrip(P.grid, [
		mk(__("Total Income"), M.total_income, "currency", "up", { route: pl.route }),
		mk(__("Direct Expenses"), M.direct_expense, "currency", "down", { route: pl.route }),
		mk(__("Gross Profit"), M.gross_profit, "currency", "up", { route: pl.route }),
		mk(__("Indirect Expenses"), M.indirect_expense, "currency", "down", { route: pl.route }),
		mk(__("Net Profit"), M.net_profit, "currency", "up", { route: pl.route }),
		mk(__("Gross Margin"), M.gp_margin, "percent", "up", { route: pl.route }),
		mk(__("Net Margin"), M.np_margin, "percent", "up", { route: pl.route }),
	], "span-12");
	chart(P.panel({ title: __("Monthly Income vs Expenses"), sub: __("Click a month to open the Profit and Loss report"), span: 7 }), {
		labels: pl.monthly.labels, datasets: [{ name: __("Income"), values: pl.monthly.income }, { name: __("Expenses"), values: pl.monthly.expense }], type: "bar", colors: [series(0), series(1)],
		onSelect: (i) => { const r = monthRange(pl.monthly.labels[i]); if (r) drill(reportSpec("Profit and Loss Statement", { company: f.company, period_start_date: r[0], period_end_date: r[1], periodicity: "Monthly", filter_based_on: "Date Range" })); },
	});
	chart(P.panel({ title: __("Monthly Profit Trend"), sub: __("Gross and net profit"), span: 5 }), {
		labels: pl.monthly.labels, datasets: [{ name: __("Gross profit"), values: pl.monthly.gross_profit }, { name: __("Net profit"), values: pl.monthly.net_profit }], type: "line", colors: [series(2), series(0)],
	});

	P.heading(__("Balance Sheet"));
	const B = bs.metrics;
	kpiStrip(P.grid, [
		mk(__("Current Assets"), B.current_assets, "currency", "up", { route: bs.route }),
		mk(__("Fixed / Non-Current Assets"), B.fixed_assets, "currency", "up", { route: bs.route }),
		mk(__("Current Liabilities"), B.current_liabilities, "currency", "down", { route: bs.route }),
		mk(__("Long-Term Liabilities"), B.long_term_liabilities, "currency", "down", { route: bs.route }),
		mk(__("Equity"), B.equity, "currency", "up", { route: bs.route, title: __("Assets minus liabilities: equity accounts plus retained / unclosed profit") }),
		mk(__("Working Capital"), B.working_capital, "currency", "up", { route: bs.route }),
		mk(__("Current Ratio"), B.current_ratio, "ratio", "up", { title: __("Current assets / current liabilities") }),
		mk(__("Quick Ratio"), B.quick_ratio, "ratio", "up", { title: __("(Current assets - stock) / current liabilities") }),
		mk(__("Debt-to-Equity"), B.debt_to_equity, "ratio", "down", { title: __("Total liabilities / equity") }),
	], "span-12");
	donutRows(P.panel({ title: __("Asset Composition"), sub: `${__("As on")} ${frappe.datetime.str_to_user(bs.asof)}`, span: 6 }), bs.composition.labels, bs.composition.values);
	donutRows(P.panel({ title: __("Liabilities & Equity"), span: 6 }), bs.funding.labels, bs.funding.values);

	P.heading(__("General Ledger"));
	kpiStrip(P.grid, [
		{ label: __("Total Debit"), value: money(gl.total_debit), title: moneyFull(gl.total_debit), route: gl.route },
		{ label: __("Total Credit"), value: money(gl.total_credit), title: moneyFull(gl.total_credit), route: gl.route },
		{ label: __("Difference"), value: money(gl.difference), tone: Math.abs(gl.difference) < 0.01 ? "good" : "bad", sub: Math.abs(gl.difference) < 0.01 ? __("Ledger balances") : __("Ledger does not balance") },
		{ label: __("GL Entries"), value: num(gl.entries), route: gl.route },
	], "span-12");
	chart(P.panel({ title: __("Ledger Transaction Trend"), sub: __("Monthly debit and credit postings"), span: 12 }), {
		labels: gl.trend.labels, datasets: [{ name: __("Debit"), values: gl.trend.debit }, { name: __("Credit"), values: gl.trend.credit }], type: "line", colors: [series(0), series(1)],
	});
	hbars(P.panel({ title: __("Major Income Accounts"), span: 6 }), gl.major_income_accounts.map((r) => ({ label: r.label, value: r.amount, route: glSpec(f, r.account) })), { color: 2 });
	hbars(P.panel({ title: __("Major Expense Accounts"), span: 6 }), gl.major_expense_accounts.map((r) => ({ label: r.label, value: r.amount, route: glSpec(f, r.account) })), { color: 1 });
	table(P.panel({ title: __("Account-wise Balances"), sub: __("Largest closing balances (debit positive)"), span: 12 }), [
		{ key: "account", label: __("Account"), link: (r) => glSpec(f, r.account) },
		{ key: "root_type", label: __("Type") },
		{ key: "balance", label: __("Balance"), align: "right", fmt: (v) => moneyFull(v) },
	], gl.account_balances, { max: 20 });

	P.heading(__("Expense Analysis"));
	kpiStrip(P.grid, [
		mk(__("Total Expenses"), ex.total, "currency", "down", { route: pl.route }),
		{ label: __("Direct Expenses"), value: money(ex.direct_vs_indirect.values[0]), route: pl.route },
		{ label: __("Indirect Expenses"), value: money(ex.direct_vs_indirect.values[1]), route: pl.route },
	], "span-12");
	hbars(P.panel({ title: __("Expense Account-wise Analysis"), sub: __("Click an account to open its ledger"), span: 6 }), ex.by_account.map((r) => ({ label: r.label, value: r.amount, route: r.account ? glSpec(f, r.account) : null })), { color: 1 });
	chart(P.panel({ title: __("Monthly Expenses"), span: 6 }), { labels: ex.monthly.labels, datasets: [{ name: __("Expenses"), values: ex.monthly.values }], type: "bar", colors: [series(1)] });
	hbars(P.panel({ title: __("Cost Center-wise Expenses"), span: 4 }), ex.by_cost_center.map((r) => ({ label: r.label, value: r.amount })), { color: 4 });
	const dep = P.panel({ title: __("Department-wise Expenses"), span: 4 });
	if (ex.by_department) hbars(dep, ex.by_department.map((r) => ({ label: r.label, value: r.amount })), { color: 6 });
	else dep.innerHTML = emptyHtml(esc(ex.department_note), "info");
	donutRows(P.panel({ title: __("Direct vs Indirect"), span: 4 }), ex.direct_vs_indirect.labels, ex.direct_vs_indirect.values);
	note(el, __("Profit & Loss and Balance Sheet figures are produced by ERPNext's own financial statement engine, so they follow the account tree, opening balances, fiscal year and cost-centre filters. Use Financial Statements > Verify to compare with the standard reports."));
}

// ------------------------------------------------------------------ Financial statements
export function renderStatements(el, d, ctx) {
	const f = ctx.f;
	const wrap = document.createElement("div");
	wrap.innerHTML = `<div class="bid-tabs" role="tablist">
		<button class="bid-tab active" data-t="pl" role="tab">${__("Profit & Loss")}</button>
		<button class="bid-tab" data-t="bs" role="tab">${__("Balance Sheet")}</button>
		<span class="bid-spacer"></span>
		<label class="bid-check"><input type="checkbox" class="bid-months"> ${__("Show months")}</label>
		<button class="btn btn-default btn-sm bid-verify">${icon("check-circle", 14)} ${__("Verify against standard reports")}</button></div>
		<div class="bid-fs-body"></div><div class="bid-verify-body"></div>`;
	el.appendChild(wrap);
	const body = wrap.querySelector(".bid-fs-body");
	let tab = "pl";

	const draw = () => {
		body.innerHTML = "";
		const months = wrap.querySelector(".bid-months").checked;
		const P = new Panels(body);
		if (tab === "pl") {
			const pl = d.profit_and_loss, s = pl.summary;
			kpiStrip(P.grid, [
				{ label: __("Total Income"), value: money(s.total_income) },
				{ label: __("Gross Profit"), value: money(s.gross_profit), sub: pct(s.gross_margin) },
				{ label: __("Net Profit"), value: money(s.net_profit), sub: pct(s.net_margin), tone: s.net_profit >= 0 ? "good" : "bad" },
			], "span-12");
			const cols = [{ key: "label", label: __("Account"), first: true, link: (r) => (r._account ? glSpec(f, r._account) : null) }, { key: "total", label: __("Total"), align: "right", fmt: (v) => moneyFull(v) }];
			if (months) pl.labels.forEach((l, i) => cols.push({ key: `m${i}`, label: l, align: "right", fmt: (v) => (v ? moneyFull(v) : "—") }));
			const rows = (list) => list.map((r) => ({ ...r, _account: r.is_group ? null : r.account, _indent: r.indent, _cls: r.is_group ? "group" : "", ...Object.fromEntries(r.values.map((v, i) => [`m${i}`, v])) }));
			table(P.panel({ title: __("Income"), span: 12, tools: `<a class="bid-link" href="#" data-open="pl">${__("Open standard report")} ${icon("external-link", 12)}</a>` }), cols, rows(pl.income), { max: 500, emptyText: __("No income in this period.") });
			table(P.panel({ title: __("Expenses"), span: 12 }), cols, rows(pl.expenses), { max: 500, emptyText: __("No expenses in this period.") });
			body.querySelector("[data-open=pl]").addEventListener("click", (e) => { e.preventDefault(); drill(pl.route); });
		} else {
			const bs = d.balance_sheet, s = bs.summary;
			kpiStrip(P.grid, [
				{ label: __("Total Assets"), value: money(s.total_assets) },
				{ label: __("Total Liabilities"), value: money(s.total_liabilities), sub: `${__("Current")} ${money(s.current_liabilities)}` },
				{ label: __("Equity"), value: money(s.equity), sub: `${__("Accounts")} ${money(s.equity_accounts)} + ${__("retained / unclosed")} ${money(s.retained_earnings_and_unclosed)}` },
			], "span-12");
			const cols = [
				{ key: "label", label: __("Account"), first: true, link: (r) => (r._account ? reportSpec("General Ledger", { company: f.company, to_date: bs.asof, account: [r._account] }) : null) },
				{ key: "total", label: `${__("As on")} ${frappe.datetime.str_to_user(bs.asof)}`, align: "right", fmt: (v) => moneyFull(v) },
				{ key: "previous", label: `${__("As on")} ${frappe.datetime.str_to_user(bs.prev_asof)}`, align: "right", fmt: (v) => moneyFull(v) },
			];
			const rows = (list) => list.map((r) => ({ ...r, _account: r.is_group ? null : r.account, _indent: r.indent, _cls: r.is_group ? "group" : "" }));
			table(P.panel({ title: __("Assets"), span: 12, tools: `<a class="bid-link" href="#" data-open="bs">${__("Open standard report")} ${icon("external-link", 12)}</a>` }), cols, rows(bs.assets), { max: 600 });
			table(P.panel({ title: __("Liabilities"), sub: __("Equity accounts in your chart sit under Liabilities and are listed here."), span: 12 }), cols, rows(bs.liabilities), { max: 600 });
			if (bs.equity_accounts.length) table(P.panel({ title: __("Equity"), span: 12 }), cols, rows(bs.equity_accounts), { max: 600 });
			body.querySelector("[data-open=bs]").addEventListener("click", (e) => { e.preventDefault(); drill(bs.route); });
		}
	};
	wrap.querySelectorAll(".bid-tab").forEach((b) =>
		b.addEventListener("click", () => {
			wrap.querySelectorAll(".bid-tab").forEach((x) => x.classList.toggle("active", x === b));
			tab = b.dataset.t;
			draw();
		})
	);
	wrap.querySelector(".bid-months").addEventListener("change", draw);
	wrap.querySelector(".bid-verify").addEventListener("click", async () => {
		const out = wrap.querySelector(".bid-verify-body");
		out.innerHTML = `<div class="bid-skel bid-skel-panel"></div>`;
		try {
			const r = await api("validation.get_reconciliation", { filters: ctx.filtersJson() });
			if (r.permission_denied) { out.innerHTML = emptyHtml(esc(r.message), "lock"); return; }
			const p = new Panels(out);
			table(p.panel({ title: r.all_ok ? __("All checks passed") : __("Some checks differ"), sub: __("Dashboard figures against ERPNext's standard reports and independent ledger queries."), span: 12 }), [
				{ key: "check", label: __("Check") },
				{ key: "dashboard", label: __("Dashboard"), align: "right", fmt: (v) => moneyFull(v) },
				{ key: "standard", label: __("Standard / ledger"), align: "right", fmt: (v) => moneyFull(v) },
				{ key: "difference", label: __("Difference"), align: "right", fmt: (v) => moneyFull(v) },
				{ key: "ok", label: __("Result"), html: true, fmt: (v, row) => (row.informational ? `<span class="bid-badge sev-info">${__("Info")}</span>` : v ? `<span class="bid-badge sev-ok">${icon("check-circle", 13)} ${__("Match")}</span>` : `<span class="bid-badge sev-critical">${icon("x-circle", 13)} ${__("Differs")}</span>`) },
				{ key: "source", label: __("Compared with") },
			], r.checks);
		} catch (e) {
			out.innerHTML = errorHtml(e.message, false);
		}
	});
	draw();
}

// ------------------------------------------------------------------- Cash flow / banking
export function renderCashFlow(el, d, ctx) {
	const f = ctx.f;
	const s = d.summary, R = d.routes;
	kpiStrip(el, [
		{ label: __("Opening Cash & Bank"), value: money(s.opening), title: moneyFull(s.opening), route: R.accounts },
		{ label: __("Cash Inflow"), value: money(s.inflow), tone: "good", route: R.accounts },
		{ label: __("Cash Outflow"), value: money(s.outflow), tone: "bad", route: R.accounts },
		{ label: __("Net Cash Flow"), value: money(s.net), tone: s.net >= 0 ? "good" : "bad", route: R.accounts },
		{ label: __("Closing Cash & Bank"), value: money(s.closing), title: moneyFull(s.closing), delta: s.growth, sub: `${__("Cash")} ${money(s.cash)} · ${__("Bank")} ${money(s.bank)}`, route: R.accounts },
	]);
	const P = new Panels(el);
	chart(P.panel({ title: __("Monthly Cash Flow"), sub: __("Netted per voucher, so transfers between your own accounts are excluded"), span: 7 }), {
		labels: d.monthly.labels, datasets: [{ name: __("Inflow"), values: d.monthly.inflow }, { name: __("Outflow"), values: d.monthly.outflow }], type: "bar", colors: [series(2), series(1)],
	});
	chart(P.panel({ title: __("Closing Balance"), sub: __("Cash and bank at month end"), span: 5 }), {
		labels: d.monthly.labels, datasets: [{ name: __("Closing"), values: d.monthly.closing }], type: "line", area: true, colors: [series(0)],
	});
	table(P.panel({ title: __("Cash & Bank Account Balances"), sub: __("Click an account to open its ledger"), span: 12 }), [
		{ key: "label", label: __("Account"), link: (r) => glSpec(f, r.account) },
		{ key: "type", label: __("Type") },
		{ key: "opening", label: __("Opening"), align: "right", fmt: (v) => moneyFull(v) },
		{ key: "debits", label: __("Receipts"), align: "right", fmt: (v) => moneyFull(v) },
		{ key: "credits", label: __("Payments"), align: "right", fmt: (v) => moneyFull(v) },
		{ key: "closing", label: __("Closing"), align: "right", fmt: (v) => moneyFull(v) },
	], d.accounts, { emptyText: __("No cash or bank accounts for this company.") });

	const rec = d.reconciliation;
	const rb = P.panel({ title: __("Bank Reconciliation Status"), sub: rec.transactions ? `${rec.transactions.count} ${__("unreconciled bank transactions")} (${money(rec.transactions.amount)})` : "", span: 7, tools: `<a class="bid-link bid-rec" href="#">${__("Open reconciliation tool")} ${icon("external-link", 12)}</a>` });
	table(rb, [
		{ key: "label", label: __("Bank Account") },
		{ key: "book_balance", label: __("Book Balance"), align: "right", fmt: (v) => money(v) },
		{ key: "uncleared_vouchers", label: __("Uncleared"), align: "right" },
		{ key: "uncleared_deposits", label: __("Deposits"), align: "right", fmt: (v) => money(v) },
		{ key: "uncleared_withdrawals", label: __("Withdrawals"), align: "right", fmt: (v) => money(v) },
	], rec.accounts, { emptyText: __("No bank accounts.") });
	el.querySelector(".bid-rec").addEventListener("click", (e) => { e.preventDefault(); drill(R.reconcile); });
	const pp = d.pending_payments;
	table(P.panel({ title: __("Pending Payments"), sub: `${pp.draft_pay_count} ${__("draft supplier payments")} · ${money(pp.draft_pay_amount)}`, span: 5, tools: `<a class="bid-link bid-pend" href="#">${__("Open")} ${icon("external-link", 12)}</a>` }), [
		{ key: "name", label: __("Payment"), link: (r) => formSpec("Payment Entry", r.name) },
		{ key: "party", label: __("Party") },
		{ key: "amount", label: __("Amount"), align: "right", fmt: (v) => money(v) },
	], pp.rows, { emptyText: __("No draft payments."), max: 8 });
	el.querySelector(".bid-pend").addEventListener("click", (e) => { e.preventDefault(); drill(R.pending); });

	if (d.obligations.payable) chart(P.panel({ title: __("Upcoming Cash Obligations"), sub: __("Supplier bills falling due"), span: 6 }), { labels: d.obligations.payable.labels, datasets: [{ name: __("Payable"), values: d.obligations.payable.values }], type: "bar", colors: [series(1)], emptyText: __("No supplier bills fall due soon.") });
	if (d.obligations.receivable) chart(P.panel({ title: __("Expected Cash Receipts"), sub: __("Customer invoices falling due"), span: 6 }), { labels: d.obligations.receivable.labels, datasets: [{ name: __("Receivable"), values: d.obligations.receivable.values }], type: "bar", colors: [series(2)], emptyText: __("No customer invoices fall due soon.") });
	note(el, __("Reconciliation counts bank GL postings from Payment and Journal Entries that have no clearance date. If your team does not record clearance dates, these numbers will be large by design."));
}

// ------------------------------------------------------------------------- Inventory
export function renderInventory(el, d, ctx) {
	const f = ctx.f;
	const s = d.summary, R = d.routes, mc = d.movement_counts;
	kpiStrip(el, [
		{ label: __("Total Stock Value"), value: money(s.stock_value), title: moneyFull(s.stock_value), route: R.stock_balance, sub: s.previous_value ? `${__("vs")} ${money(s.previous_value)}` : "" },
		{ label: __("Total Stock Quantity"), value: num(s.stock_qty, 2), sub: `${num(s.item_count)} ${__("items")} · ${s.warehouse_count} ${__("warehouses")}` },
		{ label: __("Negative Stock"), value: num(d.negative_count), tone: d.negative_count ? "bad" : "good", route: R.negative },
		{ label: __("Low Stock / Reorder"), value: `${d.low_stock_count} / ${d.reorder_count}`, tone: d.low_stock_count + d.reorder_count ? "warn" : "good", route: R.projected },
		{ label: __("Non-Moving Value"), value: money(mc.non_moving_value), sub: `${mc.non_moving} ${__("items, no issue in {0} days", [mc.window_days])}`, tone: "warn" },
		{ label: __("In Transit"), value: money(d.in_transit.warehouse_value + d.in_transit.pending_transfer_value), sub: `${d.in_transit.pending_transfers} ${__("open transfers")}` },
	]);
	const P = new Panels(el);
	chart(P.panel({ title: __("Stock Valuation Trend"), sub: __("Month-end stock value from the Stock Ledger"), span: 7 }), { labels: d.valuation_trend.labels, datasets: [{ name: __("Stock value"), values: d.valuation_trend.values }], type: "line", area: true, colors: [series(0)] });
	chart(P.panel({ title: __("Stock Ageing"), sub: d.ageing.available ? __("Value by age (FIFO), standard Stock Ageing report") : "", span: 5 }), d.ageing.available ? { labels: d.ageing.labels, datasets: [{ name: __("Value"), values: d.ageing.value }], type: "bar", colors: [series(3)], onSelect: () => drill(R.ageing) } : { labels: [], datasets: [], emptyText: d.ageing.note });
	hbars(P.panel({ title: __("Warehouse-wise Stock Value"), span: 6 }), d.warehouses.map((w) => ({ label: w.warehouse, value: w.value, sub: `${num(w.qty, 2)} ${__("units")}`, route: reportSpec("Stock Balance", { company: f.company, from_date: f.from_date, to_date: f.to_date, warehouse: w.warehouse }) })));
	hbars(P.panel({ title: __("Top 10 High-Value Items"), span: 6 }), d.top_value_items.map((r) => ({ label: r.item_name, value: r.value, sub: `${num(r.qty, 2)} ${__("units")}`, route: reportSpec("Stock Balance", { company: f.company, from_date: f.from_date, to_date: f.to_date, item_code: r.item_code }) })), { color: 2 });

	const cols = [
		{ key: "item_code", label: __("Item"), link: (r) => formSpec("Item", r.item_code) },
		{ key: "item_name", label: __("Name") },
		{ key: "qty", label: __("In Stock"), align: "right", fmt: (v) => num(v, 2) },
		{ key: "qty_out", label: __("Issued ({0}d)", [mc.window_days]), align: "right", fmt: (v) => num(v, 2) },
		{ key: "value", label: __("Value"), align: "right", fmt: (v) => money(v) },
	];
	table(P.panel({ title: __("Fast-Moving Items"), sub: __("Highest issues in the last {0} days", [mc.window_days]), span: 4 }), cols, d.fast_moving, { emptyText: __("No stock issues in the window."), max: 10 });
	table(P.panel({ title: __("Slow-Moving Items"), sub: `${mc.slow} ${__("items")} · ${money(mc.slow_value)}`, span: 4 }), cols, d.slow_moving, { emptyText: __("No slow-moving items."), max: 10 });
	table(P.panel({ title: __("Non-Moving Items"), sub: `${mc.non_moving} ${__("items")} · ${money(mc.non_moving_value)}`, span: 4 }), cols, d.non_moving, { emptyText: __("No non-moving items."), max: 10 });

	table(P.panel({ title: __("Negative Stock Alerts"), sub: __("Click an item to see its ledger"), span: 6 }), [
		{ key: "item_code", label: __("Item"), link: (r) => reportSpec("Stock Ledger", { company: f.company, from_date: f.from_date, to_date: f.to_date, item_code: r.item_code, warehouse: r.warehouse }) },
		{ key: "warehouse", label: __("Warehouse") },
		{ key: "qty", label: __("Qty"), align: "right", fmt: (v) => num(v, 3) },
		{ key: "value", label: __("Value"), align: "right", fmt: (v) => money(v) },
	], d.negative_stock, { emptyText: __("No negative stock."), max: 12 });
	table(P.panel({ title: __("Low Stock Alerts"), sub: __("Below the item's safety stock"), span: 6 }), [
		{ key: "item_code", label: __("Item"), link: (r) => formSpec("Item", r.item_code) },
		{ key: "qty", label: __("In Stock"), align: "right", fmt: (v) => num(v, 2) },
		{ key: "safety_stock", label: __("Safety Stock"), align: "right", fmt: (v) => num(v, 2) },
		{ key: "shortfall", label: __("Short By"), align: "right", fmt: (v) => num(v, 2) },
	], d.low_stock, { emptyText: __("No items below safety stock."), max: 12 });
	table(P.panel({ title: __("Reorder Alerts"), sub: __("Projected quantity below the Item Reorder level"), span: 12 }), [
		{ key: "item_code", label: __("Item"), link: (r) => formSpec("Item", r.item_code) },
		{ key: "warehouse", label: __("Warehouse") },
		{ key: "actual_qty", label: __("Actual"), align: "right", fmt: (v) => num(v, 2) },
		{ key: "projected_qty", label: __("Projected"), align: "right", fmt: (v) => num(v, 2) },
		{ key: "reorder_level", label: __("Reorder Level"), align: "right", fmt: (v) => num(v, 2) },
		{ key: "reorder_qty", label: __("Reorder Qty"), align: "right", fmt: (v) => num(v, 2) },
	], d.reorder_alerts, { emptyText: __("No Item Reorder levels are breached (or none are defined)."), max: 12 });
	note(el, __("Stock quantity and value come from the Stock Ledger Entry (same basis as the Stock Balance report), so they follow each item's valuation method."));
}

// -------------------------------------------------------------------------------- GST
export function renderGst(el, d, ctx) {
	if (!d.available) {
		el.innerHTML = emptyHtml(esc(d.note || __("GST is not configured for this company.")), "info");
		return;
	}
	const f = ctx.f, s = d.summary, R = d.routes;
	if (d.note) note(el, esc(d.note), "warn");
	kpiStrip(el, [
		{ label: __("Output GST"), value: money(s.output_gst), title: moneyFull(s.output_gst), sub: __("net of credit notes"), route: R.ledger },
		{ label: __("Input GST"), value: money(s.input_gst), title: moneyFull(s.input_gst), sub: __("net of returns"), route: R.ledger },
		{ label: s.is_refundable ? __("Net GST (Refundable)") : __("Net GST Liability"), value: money(s.net_liability), tone: s.is_refundable ? "good" : "warn", title: __("Output - input (+ reverse charge) for the period") },
		{ label: __("GST Payable (Ledger)"), value: money(s.gst_payable_ledger), sub: __("balance on the GST accounts"), route: R.ledger },
		{ label: __("GST Collected"), value: money(s.gst_collected), sub: `${__("credit notes")} ${money(s.credit_note_reversal)}` },
		{ label: __("GST Paid on Purchases"), value: money(s.gst_paid), sub: `${__("returns")} ${money(s.purchase_return_reversal)}` },
	]);
	const P = new Panels(el);
	chart(P.panel({ title: __("Monthly GST Trend"), sub: __("Output vs input tax (document driven)"), span: 7 }), { labels: d.monthly.labels, datasets: [{ name: __("Output"), values: d.monthly.output }, { name: __("Input"), values: d.monthly.input }, { name: __("Net"), values: d.monthly.net }], type: "line", colors: [series(1), series(0), series(2)] });
	chart(P.panel({ title: __("CGST / SGST / IGST"), sub: __("Output and input by component"), span: 5 }), { labels: d.components.map((c) => c.label), datasets: [{ name: __("Output"), values: d.components.map((c) => c.output) }, { name: __("Input"), values: d.components.map((c) => c.input) }], type: "bar", colors: [series(1), series(0)] });
	table(P.panel({ title: __("Tax Account-wise Summary"), sub: __("Click an account to open its ledger"), span: 12 }), [
		{ key: "account", label: __("Tax Account"), link: (r) => glSpec(f, r.account) },
		{ key: "direction", label: __("Type"), fmt: (v) => ({ output: __("Output"), input: __("Input"), rcm_output: __("RCM Output"), rcm_input: __("RCM Input") }[v] || v) },
		{ key: "component", label: __("Tax") },
		{ key: "debit", label: __("Debit"), align: "right", fmt: (v) => moneyFull(v) },
		{ key: "credit", label: __("Credit"), align: "right", fmt: (v) => moneyFull(v) },
		{ key: "closing_balance", label: __("Closing (Cr +)"), align: "right", fmt: (v) => moneyFull(v) },
	], d.accounts);
	if (s.settled_via_journal_input || s.settled_via_journal_output) {
		note(el, __("Journal / Payment Entries on GST accounts (set-off and payments to the government): output side {0}, input side {1}. They are excluded from collected / paid figures.", [money(s.settled_via_journal_output), money(s.settled_via_journal_input)]));
	}
}
