# Engineering handoff: Decision Center redesign

Read `README.md` first and run the prototype. Field and function names below were checked against the code on Nov 9, 2026. **Three code states exist and differ**; each row says which one it refers to:

- **base**: `origin/main` at `cfab8a2`, the base of this PR.
- **local**: Ricardo's uncommitted working tree. Several files it relies on are untracked and **not in base**: `ppc_page.py`, `ppc_settings.py`, `templates/ppc_decisions.html`, `static/ppc_decisions.js`.
- **live**: the Railway deployment, reviewed read-only and older than both.

Before implementing, decide with the PM which state is the starting point. This PR does not change any of them.

Labels: **[exists]** usable as is · **[partial]** source exists, the payload needs shaping · **[new]** new backend logic · **[gap]** the data is not captured · **[PROPOSAL]** design proposal that needs PM approval before it becomes a requirement.

## 1. How today's Home "Three priorities" is assembled

Route `GET /` → `executive()` in `decision_dashboard_v2/app.py` → `templates/dashboard.html` (`page=='executive'`, `diagnosis.priorities`).

1. `action_queue(start, end, brand)` scores ASIN alerts (`severity`, `estimated_30d_impact`, `headline`, `reason`, `next_step`) and returns the top 6. For Litet it only decides whether any steps exist (`executive_actions` returns "No material intervention" when it is empty).
2. `executive_actions()` (Litet branch) builds **fixed-order** steps:
   1. "ACT NOW — Stop PPC budget increases…" (carries a `proposal`)
   2. "WATCH — Do not change price from four days of demand." (the text "four days" is hard-coded)
   3. "ACT NOW — Confirm replenishment for …", only when the lowest-cover inventory query returns a row. It is labeled ACT NOW whatever the cover (live showed 40 days).
3. In **base and local**, `executive()` drops steps that have a `proposal` or contain PPC words, then **inserts "Review current advertising evidence" at position 1**.
4. `executive_diagnosis()` sets `priorities = steps[:3]`.

**Fixed:** positions 1 and 2 are always present and always in the same order. Only the inventory step is conditional. Nothing is ranked by urgency, impact or freshness. Possible crash (hypothesis, not tested): when `prior_sales` is 0, `change` is `None` and `f"{change:+.0%}"` raises.

## 2. Mapping: prototype → routes, templates, fields

### Home (`GET /`, `templates/dashboard.html`)

| Prototype element | Existing source | Work needed | Label |
| --- | --- | --- | --- |
| Up to 3 priorities, ranked | `action_queue` rows; inventory-cover query in `executive_actions`; `ppc_decisions()`; `build_workspace` targets | A new `home_priorities(brand)` that returns candidates `{category, title, why, urgency, impact_30d, evidence_end, imported_at, comparison:{start,end,prior_start,prior_end}, destination:{page, params}, qualifies, exclusion_reason}`, ranks them, and returns ≤ 3 without padding, plus the non-qualifying candidates | **[new]** |
| Ranking: score = urgency × impact × freshness; ties go to the larger 30-day impact | none | Formula, factor scales and qualification thresholds | **[PROPOSAL]** |
| Freshness factor: 1.0 fresh, 0.75 attribution maturing, ≤ 0.6 stale | `ppc_coverage()`, `build_workspace().freshness`, `MAX(report_date)` / `imported_at` | Per-source freshness for orders, PPC, inventory (`inventory_snapshots.snapshot_date`) and Business Report traffic. Prototype threshold: stale when the newest import is more than 2 days old | **[PROPOSAL]** thresholds · **[partial]** data |
| Comparison period on every card ("Nov 1–8 vs Oct 1–8, same weekdays") | `previous_month_comparison()`, `previous_period()` | Return the exact windows used, per candidate | **[partial]** |
| "Last data update" per card | as above | Show the source import time | **[partial]** |
| Investigate deep links | Routes accept `brand` and `period` only | Add `pack`, `asin`, `campaign` and `target` query parameters to `/products` and `/ppc` | **[new]** small |
| Daily ordered sales with a prior-period overlay; daily orders | `orders` table + `amazon_us_date()`; `monthly_trend()` is monthly only (`ordered_sales`, `ad_spend`, `tacos`, `sessions`, `conversion`, `is_partial`) | Daily series: sales, distinct non-cancelled orders, prior window. Days not imported must be `null`, not 0 | **[partial]** |
| Settled contribution by month, shown separately | `pnl_statement()`, `overview().contribution_after_cogs` / `contribution_margin` | Monthly series plus a `settled_through` date. Unsettled months are `null` with a reason | **[partial]** |
| Fewer-than-3 panel | none | The candidate builder returns `exclusion_reason` | **[new]** |

### Products (`GET /products`, `templates/dashboard.html`)

| Prototype element | Existing source | Work needed | Label |
| --- | --- | --- | --- |
| Ranked pack bars: Sales / Units | `product_portfolio().pack_groups` (`name`, `sales`, `units`, `asins`, `sku_count`, `status`) | Add prior-period values for the marker | **[exists]** / small |
| Contribution switch | `product_diagnostics()` `net_proceeds` (before COGS), COGS seed | Per-ASIN settled contribution after COGS for the settled month; return a missing count when fees are unsettled | **[new]** |
| Color × size heatmap | product rows (`color`, `size`, `pack_type`, `asin`, `sku_list`, `inventory`, `sessions`); `color_groups`, `size_groups` | Matrix payload per pack where a cell is `value`, `null` (no data, with a reason) or `not_offered` (no ASIN in `dim_product`) | **[partial]** |
| ASIN detail: daily sales | `orders` by `asin` | New daily query | **[partial]** |
| ASIN detail: sellable stock trend | `inventory_availability` (`sellable_quantity` by `snapshot_date`) | New daily query; exclude unsellable stock, consistent with the Nov 3 inventory fix | **[partial]** |
| ASIN detail: inbound / AWD units | not imported | Data source needed; until then shown as missing | **[gap]** |
| Distinct missing values | Templates render `None` as "—" and zero as "$0.00", so they look alike | API contract: `null` plus `reason`; the UI never turns `null` into 0 | **[new]** contract |
| Path to the pricing decision | `GET /decisions/pricing?asin=` → `pricing_case()` (live returns 200); `POST /decisions/pricing/approve` | Add links from ASIN detail and from Decisions; no template links there today | **[partial]** |

### PPC (`GET /ppc`)

The template depends on the state: **base** renders `ppc_workspace.html` via `_evidence_review("ppc")`; **local** renders `ppc_decisions.html` via `ppc_page.build_page()`; **live** renders the legacy "PPC + organic" section of `dashboard.html`.

| Prototype element | Existing source | Work needed | Label |
| --- | --- | --- | --- |
| Brand KPIs (sales, spend, TACoS) that never change with the campaign filter | local `build_page()` → `company`, `prior`; base `build_workspace()` → `company`, `totals` | Compute brand KPIs separately from the campaign scope | **[partial]** (local only) |
| Aligned daily sales / spend / TACoS | local `build_page()` → `daily` (`day`, `sales`, `spend`) | Daily TACoS; a shared x-axis; `null` for days not imported | **[partial]** (local only) |
| Recent (attribution-maturing) window shaded | base `build_workspace()` → `mature_start`, `mature_end`, `recent_start`, `attribution_cutoff`; per target `mature`, `recent` | Expose these in the page payload | **[exists]** in base |
| Prototype recent window = last 7 days | `attribution_cutoff` | Confirm against the 14-day attribution policy and the Nov 4–10 checkpoint | **[PROPOSAL]** |
| Campaign spend vs attributed-sales scatter | campaign aggregation of `ppc_fact_clean` (the same query as in `executive_actions`) | Per-campaign `{spend, ad_sales, orders}` for the period | **[partial]** small |
| Scatter filters the target table | local `ppc_decisions.html` campaign `<select>` reloads the page | Filter on the client so the KPIs and trends stay fixed | **[new]** small |
| Searchable target table | local `static/ppc_decisions.js` (search, action, match, status filters) | Reuse it | **[partial]** (local only) |
| Evidence drawer: match type, current bid and check date, proposed action, Amazon range and capture date, evidence dates | local `build_page()` rows: `current_bid`, `recommended`, `suggested_low/mid/high`, `settings.bid_checked_date`, `settings.range_checked_date`, `reason`, `assessment_state`; base `decision_card()` → `current_bid`, `candidate_bid`, `action`, `review_date` | Merge into one target payload; recent metrics are labeled provisional and are not used for the action | **[partial]** |
| Campaign budgets panel, separate from bids | local `build_page()` → `budget` (selected campaign only, from the captured-settings JSON) | A budget for every campaign. Out-of-budget hours are not captured, so utilization cannot show a constraint | **[gap]** |

### Decisions (`GET /decisions`)

**Base and local** render `ppc_workspace.html` (`page='decisions'`) with `review.interventions`. **Live** renders the legacy "Decision workspace" in `dashboard.html`.

| Prototype element | Existing source | Work needed | Label |
| --- | --- | --- | --- |
| Pending review / Monitoring / History | `interventions.status` (`proposed`, `approved`, `executed`, `monitoring`, `completed`, `reverted`, `dismissed`); `_intervention_rollup()` | Pending = proposed. Monitoring = approved, executed and monitoring. History = completed, reverted and dismissed | **[exists]** |
| Timeline: proposed → approved → recorded change → outcome | columns `created_at`, `approved_at`, `executed_at`, `review_date`, `review_14_date`, `outcome`, `external_status` | Show who acted, distinguish an owner-reported change from a confirmed one, and keep a status-history table so dismissals and reverts keep their dates | **[partial]** |
| Approve / Dismiss / Record change | `POST /ppc/evidence/status/<id>` with its transition map; `amazon_confirmed=yes` is required for `executed` | Reuse it. Keep the rule that the app never changes Amazon | **[exists]** |
| Before/after chart only when comparable | `ppc_change_impact()` (daily-rate before/after for the latest executed wave) | Comparability rule: equal complete windows, both attribution-mature, change day excluded, no overlapping change on the same target or campaign; otherwise return `not_comparable_reason` | **[PROPOSAL]** rule · **[new]** |
| Outcome-pending state with dates | `review_date`, `review_14_date` | Add the attribution maturity date | **[partial]** |
| Campaign-level changes (for example, dynamic bids down-only) | Owner record in `DECISIONS.md`; not an intervention row | Decide whether campaign-setting changes become intervention rows | **[gap]** |
| Product pricing decisions | `GET /decisions/pricing`, `pricing_case()`, `record_pricing_case()` | Persistent entry point on Decisions; pricing rows appear in the tabs | **[partial]** |

### Shared shell

The four templates use four navigation sets (see §3). The prototype assumes one base template with Home · Products · PPC · Decisions, a secondary "Also in the app" group, a brand selector and a freshness pill. The stale, empty and insufficient-evidence states need the per-source freshness API and the `null`-plus-reason contract above. **[new]** refactor.

## 3. Live vs local vs base differences (Nov 9, 2026)

"Verified" means seen directly. "Hypothesis" means it needs an engineering check before anyone calls it a defect.

| Area | Live (Railway) | Base (`origin/main`) | Local working tree | Read |
| --- | --- | --- | --- | --- |
| `/ppc` | Legacy "PPC + organic": "Reduce bid 10% / 30%", "Create proposal from real bid", objective "TaCoS toward 45%" | `ppc_workspace.html` "Advertising evidence" | `ppc_decisions.html` "PPC decisions" (untracked) | Verified: three different pages |
| `/decisions` | Legacy "Decision workspace": coordinated product cases, "Reduce bid 30%", executed-change cards | `ppc_workspace.html` "Decision and test workspace" | Same as base | Verified |
| Home #1 | "ACT NOW — Stop PPC budget increases…" | "Review current advertising evidence" inserted | Same as base | Verified: live is older |
| Navigation | Executive, Products, PPC, Decisions, **Strategy Map** | Executive, Products, PPC, Decisions, Sales tree, Price change | Plus "Overview … Review history" on the PPC page | Verified; no `/strategy` route in base or local |
| Pricing page | `/decisions/pricing?asin=` returns 200, with no link from Decisions | Route exists, no inbound link | Same | Verified |
| TACoS | Home 37% (MTD through Nov 9); PPC 54.9% (Nov 1–8) | n/a | n/a | Hypothesis: different denominators or periods |
| "Settled" P&L | "Latest settled period · Nov 1–8"; costs header 43.9% vs KPI 45.6% | `executive()` uses the selected MTD when it has `net_sales` | Same | Hypothesis: MTD labeled as settled |
| Products pace Δ | −86% to −100% on every ASIN | `previous_period()` picks the latest earlier Business Report period | Same | Hypothesis: mismatched prior window, or missing November traffic |
| Decision outcomes | September changes say "Early read — wait for 7 complete days" with 13–14 loaded days | `ppc_change_impact()` | Same | Hypothesis: after-window cut by the next change, or a label defect |
| Market table | "SILCA −109%", "— units / —%" shown as values | Helium 10 passthrough | Same | Verified display; source not checked |

## 4. Proposals that are not requirements

- The Home ranking formula, factor scales, qualification thresholds and tie-break.
- The freshness thresholds (stale after 2 days; "maturing" for recent PPC attribution).
- Before/after comparability rules and the 7-day recent window.
- The prototype's placement of campaign-level strategy changes in Monitoring.
- All synthetic numbers.

These need PM approval, then a joint UX, engineering and QA review against `Team Workflow/PPC-DECISION-RULES.md`, before the work is called implementation-ready. Target bids and campaign budgets stay separate everywhere. Black Friday and price-change analyses stay out of scope.
