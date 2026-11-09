# Acceptance checks

Use these checks for the implementation (with disposable test data) and as a script for walking through the prototype. Engineering and QA share the same cases. IDs are stable so test names can reference them. Values in quotes come from the prototype's synthetic data; in implementation tests, replace them with fixture values that produce the same situation.

The prototype demonstrates every check except H4, H12 and D11, which apply to the implementation only. Checks that depend on the **[PROPOSAL]** items in `HANDOFF.md` (ranking formula, freshness thresholds, comparability rule) stay provisional until the PM approves those items.

## Home: priority ranking and drill-downs

| ID | Given | When | Then |
| --- | --- | --- | --- |
| H1 | Sales, inventory and advertising candidates all qualify; sales has the highest urgency × impact × freshness | Home loads | Exactly 3 cards, ordered Sales → Inventory → Advertising, numbered 1–3 |
| H2 | Same data, but inventory cover falls below the inbound date (inventory urgency 1.0, impact 0.7; sales impact 0.8) | Home loads | Inventory is #1 and Sales is #2: the two **swap rank** with no code change. Advertising stays #3 |
| H3 | Only 2 candidates meet the qualification thresholds | Home loads | 2 cards, no filler card. A "did not qualify" list names each excluded candidate with its reason (for example, "Insufficient evidence: 54 sessions, 9 units") |
| H4 | 0 candidates qualify | Home loads | An empty state saying nothing needs attention, with the latest data update. No fixed or default priorities appear |
| H5 | Any card | Rendered | It shows the category, why it surfaced, the comparison windows with dates, the last data update for its source, all three factor values, and an Investigate link |
| H6 | The newest orders import is older than the freshness threshold | Home loads | A stale banner names the import time. Affected cards are marked "Stale evidence" and their freshness factor and score drop. Days not imported show as missing in the charts, not as 0 |
| H7 | Two candidates have equal scores | Home loads | The one with the larger 30-day impact ranks first **[PROPOSAL]** |
| H8 | Sales card | Investigate | Products opens with that pack selected and its heatmap visible |
| H9 | Inventory card | Investigate | Products opens at that ASIN's detail with the pack and ASIN in the breadcrumb |
| H10 | Advertising card | Investigate | PPC opens filtered to that campaign with the target's evidence drawer open |
| H11 | Home trends | Rendered | Daily ordered sales and daily orders sit in an "Operating" group. Monthly contribution sits in a separate "Settled" group, labeled with its settled-through date. The unsettled current month shows as not available, never as 0 |
| H12 | Any data | Code review | No priority is hard-coded by position or by text (regression for "Review current advertising evidence" at #1 and "four days of demand") |

## Products: pack → color × size → ASIN

| ID | Given | When | Then |
| --- | --- | --- | --- |
| P1 | Default view | Products loads | Horizontal bars, one per pack, sorted by ordered sales (descending), with a prior-period marker and a % change |
| P2 | Bars | Switch to Units, then Contribution | The bars re-rank for each metric. The contribution title states the settled period |
| P3 | A pack where every ASIN's contribution is unknown | Contribution selected | That pack shows hatched "Not available" with a reason, is excluded from ranking and sits last |
| P4 | A pack where some ASINs' contribution is unknown | Contribution selected | The value shows the known total plus "+ N ASIN missing", with a hatched segment |
| P5 | Select a pack | — | A color × size heatmap for that pack; the breadcrumb reads "All packs › {pack}" |
| P6 | Heatmap cells | Rendered | Three distinct treatments: hatched "No data" (null), dotted "Not offered" (no ASIN), and a real 0 shown as a number |
| P7 | Select a cell | — | ASIN detail shows the ASIN and SKUs, a daily sales chart, a sellable-stock trend with a cover line, and an exact-values table. Missing values say why. Unsellable stock is excluded |
| P8 | An ASIN below the evidence minimum | Detail opens | An insufficient-evidence notice; no conclusion is shown |
| P9 | ASIN detail | Open pricing decision | The pricing case for that ASIN opens (`/decisions/pricing?asin=`) |
| P10 | Breadcrumb | Select "All packs" or the pack name | Returns to that level, keeping the selected metric |

## PPC: campaign filter with stable brand totals

| ID | Given | When | Then |
| --- | --- | --- | --- |
| C1 | PPC loads | — | Brand KPIs (total sales, ad spend, TACoS) and three aligned daily trends share one x-axis. The recent, attribution-maturing window is shaded and labeled |
| C2 | Record the brand KPI values | Select a campaign on the scatterplot | The target table shows only that campaign's targets. **Every brand KPI and trend value is unchanged** |
| C3 | Campaign selected | Select it again, or use the campaign chip ✕ | The filter clears and all targets return. KPIs are still unchanged |
| C4 | Any scope | Type in the search box | Rows filter by target text as you type, and the input keeps focus |
| C5 | A search with no matches | — | An empty state names the search and scope, says the brand totals are unchanged, and offers Clear |
| C6 | Any target | Open Evidence | The drawer shows match type, current bid with its check date and source, proposed action and amount, Amazon range with its capture date, campaign budget (labeled campaign-level), the mature window with dates, and the recent window labeled provisional |
| C7 | A target below the evidence minimum | Open Evidence | An insufficient-evidence notice; the action is "Needs data" and no bid amount is proposed |
| C8 | Campaign budgets | Rendered | Budgets appear in their own panel, never in target-bid columns. A missing budget shows "Not captured" |
| C9 | Data stale | PPC loads | Days not imported are gaps in the trends; the period label and import date reflect the last import |
| C10 | A target with an active decision | Open Evidence | "Open in Decisions" goes to that decision |

## Decisions: timelines and outcome states

| ID | Given | When | Then |
| --- | --- | --- | --- |
| D1 | Decisions loads | — | Tabs read Pending review / Monitoring / History, each with a count. The nav shows the pending count |
| D2 | Any decision card | Rendered | A 4-step timeline (Proposed, Approved, Recorded change, Outcome), each step with a date and actor or an explicit "Awaiting review", "Not recorded yet", "Pending" or "None" |
| D3 | Pending bid proposal | Approve | It moves to Monitoring. Approved shows the date and actor; Recorded change shows "Not recorded yet". No Amazon change happens |
| D4 | Approved, not recorded | Record actual Amazon change (with confirmation) | Recorded change shows the date and "confirmed". Outcome shows Pending with the checkpoint and attribution-maturity dates |
| D5 | Owner-reported campaign change | Rendered | Recorded change reads "owner-reported, not independently verified" |
| D6 | Outcome windows are equal, complete and mature, with no overlapping change **[PROPOSAL]** | Select the decision | A before/after chart per metric (orders/day, spend/day, ACoS) with both windows' dates; ACoS is marked "lower is better" |
| D7 | Windows not comparable (for example, the after window has 5 of 7 days, or attribution is not mature) | Select the decision | No chart. "Outcome pending: windows not comparable yet" with the specific reason |
| D8 | Dismiss a pending proposal | — | It moves to History as Dismissed, with the date and reason. Outcome is "None" |
| D9 | Pending is empty | Pending tab | An empty state explaining where proposals come from, with a link to Monitoring |
| D10 | Any state | "Product pricing decisions" | The pricing case opens. "View product evidence" goes to the ASIN in Products |
| D11 | A reverted decision | History | Outcome shows the revert date and reason. A newer evaluation for the same target is referenced, not merged |

## Shared shell

| ID | Then |
| --- | --- |
| S1 | All four pages share one navigation (Home, Products, PPC, Decisions), brand selector and freshness pill |
| S2 | At 390 px wide: no horizontal page scroll, the navigation becomes a horizontal row, grids stack, and wide tables scroll inside their own box |
| S3 | Interactive controls are real buttons, links or inputs, reachable by keyboard, with targets of at least 36–44 px |
