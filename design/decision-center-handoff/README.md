# Decision Center redesign: design handoff

A clickable prototype that redesigns **Home, Products, PPC and Decisions** in the LITET Decision Center, plus an engineering handoff and acceptance checks.

- Status: design proposal for implementation planning. It is not an approved requirement, and nothing here changes scoring policy, thresholds or advertising settings.
- Data: **synthetic only**. ASINs (`B0SYN…`), campaign names, dollar amounts and dates are invented for the prototype. The folder contains no credentials, environment files or database exports.
- Scope: this folder is separate from the Flask app. Nothing here is imported by `decision_dashboard_v2`, and nothing here should be deployed.

## Contents

| Path | What it is |
| --- | --- |
| `prototype/source/` | Canonical prototype source in the Design-canvas `.dc.html` format, exported from the published canvas: `Main.dc.html` (desktop app), `Narrow.dc.html` (390 px board), `Handoff.dc.html` (handoff board), `canvas.json` (board layout). |
| `prototype/standalone/` | Offline build that opens in any browser: `index.html` (the app), `narrow.html` (390 px frame), `handoff.html`, and `dc-lite.js` (a small runner for the template subset the prototype uses). |
| `prototype/build.py` | Regenerates `standalone/index.html` and `handoff.html` from `source/`. Uses the standard library only. |
| `HANDOFF.md` | Authoritative where it differs from the handoff board, because it also covers the `origin/main` code state. Maps charts and interactions to Flask routes, templates and fields. Lists the backend work, the live-vs-local differences, and the items that are proposals. |
| `ACCEPTANCE.md` | Acceptance checks for implementation and QA. |

## Open the prototype

From the repository root:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory design/decision-center-handoff/prototype/standalone
```

Then open <http://127.0.0.1:8765/index.html>. For the narrow layout, open <http://127.0.0.1:8765/narrow.html>. Opening `index.html` directly from disk also works in most browsers; the server avoids file-URL restrictions.

URL options for `index.html`: `?scenario=sales|inventory|few`, `?dataState=current|stale`, `?startPage=home|products|ppc|decisions`, `?narrow=1`. A window narrower than 820 px switches to the narrow layout automatically.

After editing `prototype/source/Main.dc.html`, rebuild the standalone pages:

```bash
python3 design/decision-center-handoff/prototype/build.py
```

The published canvas (desktop board, 390 px board, handoff board) is the Claude artifact "Decision Center redesign". It is private to its owner, so this folder is the copy engineers should use.

## Exercise the main flows

The dark **Prototype** bar at the top is a test control, not product UI. Use it to switch the Home scenario and the data state.

**Home**
1. With **Sales leads**, the order is Sales → Inventory → Advertising. Each card shows its score, the three ranking factors, why it surfaced, the comparison period and the last data update.
2. With **Inventory leads**, Inventory and Sales swap places because the inventory urgency and impact rise.
3. With **Fewer than 3**, only two priorities show. A panel lists the candidates that did not qualify and why.
4. With **Stale**, a banner appears, freshness and scores drop, affected cards are marked "Stale evidence", and the chart shows Nov 6–8 as not imported rather than as zero.
5. Use **Investigate** to jump with context: Sales opens Products › 3-pack, Inventory opens the Blue L/XL single ASIN, and Advertising opens PPC filtered to Discovery with the target's evidence drawer open.
6. Daily sales and orders charts sit under "Operating view". The monthly contribution chart sits separately under "Settled view".

**Products**
1. Switch **Sales / Units / Contribution**. The packs re-rank. Under Contribution, the 6-pack shows hatched "Not available" and drops to the bottom, and the single pair shows "+ 1 ASIN missing".
2. Select a pack to open its color × size heatmap. Hatched "No data", dotted "Not offered" and a real `$0` are three different treatments.
3. Select a cell to open ASIN detail: a daily sales chart, the sellable-stock trend against a 21-day cover line, and an exact-values table that marks missing values with the reason. Blue S/M single shows the insufficient-evidence state.
4. Use the breadcrumb to go back. **Open pricing decision** goes to the pricing case in Decisions.

**PPC**
1. The brand KPIs and the three aligned trends (sales, spend, TACoS) shade the recent, attribution-maturing window.
2. Select a campaign point on the scatterplot. The target table filters, and the brand KPIs and trends do not change. Select the point again, or use the campaign chip, to clear the filter.
3. Search targets. A search with no matches shows an empty state that confirms the brand totals are unchanged.
4. Use **Evidence** to open the drawer: match type, current bid and the date it was checked, proposed action, Amazon range and its capture date, campaign budget, and mature vs provisional recent windows. Targets with too little data show the insufficient-evidence state.
5. Campaign budgets appear in their own panel, separate from target bids.

**Decisions**
1. Tabs: Pending review (2), Monitoring (2), History (3). Each card shows a four-step timeline: proposed → approved → recorded change → outcome.
2. **Approve test** moves a proposal to Monitoring with "Not recorded yet". **Record actual Amazon change** fills that step, and the outcome shows Pending with its dates. Dismissing both pending items shows the empty state.
3. History shows a before/after chart only when the windows are comparable (thin cycling socks, cycling socks EXACT). Monitoring items explain why the windows are not comparable yet.
4. **Product pricing decisions** opens the pricing case. **View product evidence** goes to the ASIN in Products.

## What was reviewed

Built on Nov 9, 2026, from the local `decision_dashboard_v2` source and a read-only review of all four live Railway pages (page text and DOM only, no screenshots). See `HANDOFF.md` for the differences between them.
