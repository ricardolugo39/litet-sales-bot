# Amazon/Ecommerce Sales Dashboard Audit & Redesign Blueprint

## Executive summary

The current dashboard is a useful revenue and PPC snapshot, but it is not yet a profit or cash-reconciliation system. Its main analytical dataset, called `sales_df` in code, is not a database table: it is derived in memory from `orders` joined to `asins`. The database has no physical `sales` table.

The most important discovery is that the stated assumption about `transactions` is incorrect. The table has an `Order ID`, and 1,497 of 1,550 rows match an order ID in `orders`. Therefore:

- Order-related transaction rows can be joined to sales and used for exact **total Amazon fee** and net-payout analysis at order level.
- The current transaction export does **not** expose individual referral and FBA fee components. It has one aggregated `Amazon fees` column. An exact referral/FBA split cannot be recovered from this table alone.
- Periodic fees can be classified from `Transaction type` and `Product Details`, then reconciled and allocated by an explicit rule.
- `Deferred` and `Released` rows must be treated as lifecycle states, not blindly summed. The extract contains 94 rows in 45 duplicate economic groups when status and ingestion metadata are ignored.

The recommended sequence is to keep Streamlit for the data-model work, add a tested transaction/fee mart and profit model, validate that users adopt the new workflow, and only then decide whether to migrate the presentation layer. The code’s rigidity is primarily caused by embedding a complete, 3,600-pixel HTML application inside a Streamlit iframe—not by an immediate, proven need for Flask.

---

## Phase 1 — Audit of the current implementation

### 1.1 Repository and runtime architecture

| Layer | Current implementation | Findings |
|---|---|---|
| Dashboard shell | `dashboard.py`, Streamlit | Holds global period/campaign controls, cache controls, and one iframe. |
| Dashboard UI | `html_dashboard/*.py` | Server-generates a full HTML document with Plotly charts, tables, CSS, and client-side tab switching. Embedded as a base64 `data:` URL. |
| Context/orchestration | `dashboard_context.py` | Loads all data, invokes calculations, assembles one large dictionary, and calls the AI summary synchronously. |
| Analytics | `calculations.py`, `ppc.py`, `sales_analysis.py`, `inventory.py` | Pandas functions for revenue, product mix, comparisons, PPC metrics, bid rules, and inventory risk. |
| Preparation | `data_prep.py` | Normalizes raw `orders` and `ppc`, joins the 12-row ASIN product list, derives product attributes and ratios. |
| Data access | `data.py` | Reads entire SQLite tables using `SELECT *`; path is supplied by `LITET_DB_PATH`. |
| Physical store | External SQLite `litet.db` | Tables include `orders`, `transactions`, `ppc`, `asins`, and `inventory_snapshots`. The ingestion jobs/migrations that populate them are not in this repo. |
| Other apps | `app.py`, `prime_day_app.py` | A separate Gradio AI analyst and a Streamlit Prime Day scenario app. They are not part of the main dashboard request path. |

Current request path:

```text
SQLite
  -> data.py (full-table reads)
  -> data_prep.py (Pandas normalization/enrichment)
  -> dashboard_context.py (metrics + AI call)
  -> html_dashboard/*.py (HTML string)
  -> dashboard.py (base64 iframe inside Streamlit)
```

There is no backend API layer, ORM, migration directory, or repository-owned ETL/ELT pipeline. SQLite is both the source and serving store. The raw source lineage is only hinted at by columns such as `source_system`, `source_file`, and `imported_at`; legacy commented code in `data.py` references Access databases.

### 1.2 Current pages, controls, metrics, sources, and intended questions

#### Global Streamlit controls

| Control/widget | Behavior | Source | Intended question |
|---|---|---|---|
| Refresh data | Clears `st.cache_data` and reruns | All loaded tables | “Has new source data arrived?” |
| Clear All Cache | Clears data and resource caches | All data/resources | Debug/operations control, duplicative with Refresh |
| Period | Last 7 days, last 30 days, MTD, YTD | `orders`, `ppc` | “How is the selected period performing?” |
| PPC Campaign | Filters PPC only | `ppc.Campaign Name` | “How did this campaign perform?” |
| Debug checkbox | Shows row counts and first 500 HTML characters | In-memory data | Developer troubleshooting |
| Sidebar diagnostics | Max sales date and row count | Derived `sales_df` | Freshness/volume check |

The campaign selector sits in the main area rather than the sidebar. Its filter affects PPC metrics, keyword tables, bid recommendations, trend PPC spend, and the AI input, but not sales. This is logically reasonable; the UI should make the asymmetric scope explicit.

#### Embedded dashboard tabs

| Tab / section | Current metrics and displays | Feeding data / calculation | Intended business question |
|---|---|---|---|
| Executive — KPI hero | Revenue, unique orders, pairs sold, AOV, TACOS; revenue/order/pairs/AOV prior-period deltas | `orders` + `asins`; `ppc`; `get_sales_summary_period`, `build_ppc_kpis`, `compare_periods` | “How is the business performing now versus before?” |
| Executive — AI Analyst | Summary, sales, PPC, inventory, recommended actions | Aggregated context sent to OpenAI | “What deserves attention?” |
| Executive — Sales Trend | Weekly revenue and TACOS for 12 weeks | Derived sales + PPC | “Are sales and ad efficiency improving?” |
| Executive — Attention | Revenue/orders, TACOS/ACOS, count of Critical/High inventory items | Sales, PPC, latest inventory snapshot | “Where should management look?” |
| Executive — Period Comparison | Revenue, orders, pairs sold, AOV current/prior/change | Sales | “What changed versus the prior period?” |
| Sales — KPI row | Revenue, orders, pairs, AOV, average daily sales | Sales | “What was demand in the selected period?” |
| Sales — Product Performance | Top product revenue share | Sales grouped by product/ASIN | “Which products drive revenue?” |
| Sales — Mix | Revenue by pack type, color, size | Sales + derived ASIN attributes | “What product configurations sell?” |
| Sales — Geography | Top states by revenue | `orders.ship-state` | “Where are customers?” |
| Sales — Rhythm | Revenue by weekday; best/worst weekday | Sales | “Which weekdays sell best?” |
| Sales — Velocity | Pairs/day by product | Sales | “Which SKUs move fastest?” |
| Sales — Last 3 Weeks SKU Performance | Fixed-window SKU table | Sales | “How has each SKU performed recently?” |
| Sales — Detail | Product/ASIN aggregates, not order-level detail | Sales | “What are product-level totals?” |
| PPC | Spend, ad sales, ACOS, ROAS | PPC | “Is paid advertising efficient?” |
| Products | Currently repeats the same PPC/product/inventory three-card block | PPC + inventory; `product_chart` is passed as an empty string | Intended product view, but not implemented |
| Inventory | Currently repeats the same three-card block; six risk rows | Latest inventory + trailing-30-day demand | “Which ASINs may stock out?” |
| Keywords | Keyword/match-type spend, sales, clicks, orders, ACOS, ROAS, CVR, CTR, CPC plus rule label | PPC targeting data | “Which targets should be scaled, monitored, or reduced?” |
| Actions | Suggested CPC/action/reason using fixed thresholds | PPC targeting data | “What bid action should I take?” |

Important semantic issue: `Targeting` is renamed `keyword`, while a separate `Customer Search Term` exists but is not used in the current tables. The “Keywords” tab is therefore a targeting report, not a true customer-search-term waste analysis.

### 1.3 Actual database schema and grains

All physical columns are SQLite `TEXT`; constraints and primary keys are absent in `PRAGMA table_info`. Types below describe storage, not inferred business type.

#### `sales`: no physical table

There is no `sales` table. `sales_df` is produced from `orders` and `asins`. Its practical grain is an Amazon order-item row after:

1. retaining rows whose ASIN appears in `asins`,
2. retaining only `sales-channel == "Amazon.com"`, and
3. retaining `quantity > 0`.

It retains the `amazon-order-id` and `sku` columns. The source `orders` table has 10,577 rows, 9,750 unique order IDs, and 10,568 unique `(amazon-order-id, sku)` pairs. Only 2,329 rows satisfy the ASIN-list and Amazon.com filters before the positive-quantity filter, so the dashboard represents a narrow catalog slice rather than all marketplace orders.

`orders` schema:

```text
amazon-order-id TEXT                merchant-order-id TEXT
purchase-date TEXT                  last-updated-date TEXT
order-status TEXT                   fulfillment-channel TEXT
sales-channel TEXT                  order-channel TEXT
url TEXT                            ship-service-level TEXT
product-name TEXT                   sku TEXT
asin TEXT                           item-status TEXT
quantity TEXT                       currency TEXT
item-price TEXT                     item-tax TEXT
shipping-price TEXT                 shipping-tax TEXT
gift-wrap-price TEXT                gift-wrap-tax TEXT
item-promotion-discount TEXT        ship-promotion-discount TEXT
ship-city TEXT                      ship-state TEXT
ship-postal-code TEXT               ship-country TEXT
promotion-ids TEXT                  is-business-order TEXT
price-designation TEXT              signature-confirmation-recommended TEXT
source_system TEXT                  imported_at TEXT
source_file TEXT                    order_uid TEXT
rn [untyped]
```

`asins` is a 12-row product dimension at one row per configured ASIN:

```text
ID TEXT, ASIN TEXT, Item TEXT, Type TEXT,
source_system TEXT, imported_at TEXT
```

#### `transactions`

Observed size/date coverage: 1,550 rows, May–July 2026. The grain is a transaction-event/product-detail row with a status (`Deferred` or `Released`), not a settlement-period summary and not consistently one row per order. One order can have multiple product lines, refunds, or lifecycle states.

```text
Date TEXT
Transaction Status TEXT
Transaction type TEXT
Order ID TEXT
Product Details TEXT
Total product charges TEXT
Total promotional rebates TEXT
Amazon fees TEXT
Other TEXT
Total (USD) TEXT
source_file TEXT
imported_at TEXT
transaction_uid TEXT
```

Observed transaction types and row counts:

```text
Order Payment                                  1,430
Service Fees                                      59
Refund                                            34
Liquidations                                      12
Inventory Reimbursement                           10
Shipping services purchased through Amazon         4
Other                                               1
```

Redacted representative structures:

```text
Order Payment:  Order ID "NNN-NNNNNNN-NNNNNNN", Product Details "<product title...>"
Refund:         Order ID "NNN-NNNNNNN-NNNNNNN", Product Details "<product title...>"
Service Fees:   Order ID "---" or "<fee/reference ID>",
                Product Details "FBA Customer Returns Fee (Apparel and Shoes)",
                                "FBA Inventory Storage Fee", or "AWD Storage Fee"
```

Every row has some `Order ID` text, but `---` and fee/reference identifiers are not Amazon order IDs. Of all 1,550 rows, 1,497 match `orders`; 755 distinct matched IDs are observed. This is a strong partial join, not an absence of linkage.

#### `ppc`

Observed size/date coverage: 24,372 rows over 1,252 dates, 31 campaigns, 36 ad groups, 335 targets, and 4,644 customer search terms. The apparent grain is date × campaign × ad group × target × match type × customer search term. That logical key has 24,179 unique combinations, leaving 193 repeated combinations that require investigation before aggregation.

```text
Portfolio name TEXT
Currency TEXT
Campaign Name TEXT
Ad Group Name TEXT
Targeting TEXT
Match Type TEXT
Customer Search Term TEXT
Impressions TEXT
Clicks TEXT
Click-Thru Rate (CTR) TEXT
Cost Per Click (CPC) TEXT
Spend TEXT
7 Day Total Sales TEXT
Total Advertising Cost of Sales (ACOS) TEXT
Total Return on Advertising Spend (ROAS) TEXT
7 Day Total Orders (#) TEXT
7 Day Total Units (#) TEXT
7 Day Conversion Rate TEXT
7 Day Advertised SKU Units (#) TEXT
7 Day Other SKU Units (#) TEXT
7 Day Advertised SKU Sales TEXT
7 Day Other SKU Sales TEXT
ID TEXT
ID1 TEXT
Date TEXT
source_system TEXT
imported_at TEXT
source_file TEXT
ppc_uid TEXT
```

The report contains advertised-versus-other SKU results but no advertised SKU identifier, campaign budget, bid, placement, campaign type/status, or attributed purchased ASIN. Product-level ad-spend allocation is therefore not currently defensible.

#### `inventory_snapshots`

Observed size: 5,776 rows over 49 snapshot dates. Grain is snapshot date × seller SKU × fulfillment-channel SKU × ASIN × condition/warehouse condition.

```text
seller-sku TEXT
fulfillment-channel-sku TEXT
asin TEXT
condition-type TEXT
Warehouse-Condition-code TEXT
Quantity Available TEXT
snapshot_date TEXT
imported_at TEXT
source_file TEXT
snapshot_uid TEXT
```

### 1.4 Data-quality, correctness, dead-code, and performance findings

#### High priority

- **No sale-state filter.** `prepare_sales_data` filters quantity but not `order-status` or `item-status`. Pending rows can contribute revenue; shipped, pending, shipping, and cancelled records coexist. Revenue should use an explicitly approved order lifecycle rule.
- **Revenue is intentionally narrow.** `revenue = item_price`. Per the clarified business definition, taxes, shipping, gift wrap, and promotion discounts are out of scope and must not be added to or netted against dashboard revenue or profit.
- **Mixed currencies exist.** Orders include USD, CAD, MXN, BRL, blanks, and nulls. The dashboard filters `Amazon.com`, which reduces the risk, but currency should still be asserted rather than assumed. Transactions are explicitly USD and PPC contains one currency.
- **Transactions can be double counted.** There are 16 exact duplicate rows, 16 duplicate `transaction_uid` occurrences, and 94 rows across 45 duplicated economic groups when status/source fields are excluded. Deferred and Released totals must not be added as independent cash events.
- **PPC identity is unreliable.** `ppc_uid` is duplicated 22,397 times, and 193 rows repeat the apparent business grain. Source-file overlap or report re-imports may overstate spend and sales.
- **Inventory identity is also imperfect.** `snapshot_uid` has 25 duplicate occurrences.
- **Everything is TEXT.** Numeric/date parsing is deferred to every app run, with no database constraints preventing malformed values.
- **No COGS source exists in the main model.** `prime_day_app.py` uses a hardcoded sidebar default of `$2.75` per pair; that is scenario logic, not a maintained SKU cost ledger.

#### Metric and UX correctness

- Last-7/30-day filters use `max_date - 7` or `max_date - 30` with an inclusive lower bound, producing eight or 31 calendar dates when data exists at both boundaries. Other calculation functions use `days - 1`, so the codebase is internally inconsistent.
- MTD/YTD are anchored to each dataset’s own maximum date. Sales and PPC can therefore cover different end dates while appearing in one KPI period.
- The weekly trend takes `max(sales max date, PPC max date)`, but Python comparisons can fail if one side is `NaT`; no empty-data guard exists.
- `build_revenue_tacos_trend` left-joins PPC onto sales weeks, silently dropping PPC-only weeks.
- `Avg Daily Sales` divides MTD by 30 and YTD by 365 instead of elapsed/active days.
- `prior_dates` are blank in the KPI comparison despite showing “vs prior.”
- Products and Inventory tabs duplicate the PPC block; the product chart is empty. The navigation promises more than the implementation delivers.
- Product parsing relies on title substrings and includes suspicious rules such as `"black 2" -> 3-pack`. Product attributes should come from a maintained SKU dimension.
- Keyword rules use a universal 25% target ACOS, 12% CVR, and fixed spend/click thresholds. Break-even ACOS must depend on product contribution margin.
- The AI summary makes a synchronous API call during context construction. It lacks structured schema enforcement, caching separate from the whole dataset, provenance links, anomaly tests, and protection against displaying raw exception text.
- HTML values are interpolated without escaping before being rendered with unsafe HTML. Source-controlled values reduce but do not eliminate injection risk.

#### Maintainability and performance

- Every refresh loads full `orders`, `ppc`, and latest-inventory data into Pandas. Push date filters, type casting, and aggregates into a curated SQL layer as history grows.
- The dashboard builds all tabs and charts eagerly, even if a user opens only one tab.
- The entire HTML document is base64-encoded into a data URL and loaded into a fixed-height iframe. Streamlit cannot directly observe or control the tab state inside it.
- `calculations.py` is 1,344 lines and contains overlapping summary/trend implementations.
- `format_delta` is defined twice; SKU-cleaning logic is duplicated; many sales charts computed in `html_dashboard/dashboard.py` are not rendered.
- `days = 7 if LAST_7_DAYS else 30` means MTD and YTD product/keyword auxiliary views silently use 30 days rather than the selected period.
- The repo has no automated tests, schema contracts, data-freshness checks, or reconciliation tests.

### 1.5 Streamlit vs. Flask

#### Why this application feels rigid

The strongest constraints are codebase-specific:

1. Streamlit controls live outside a fully separate iframe document.
2. Tabs are JavaScript state inside the iframe, while filters and cache state are Streamlit state outside it.
3. Every Streamlit interaction reruns data loading/context construction and can trigger the AI call again.
4. The fixed `height=3600` iframe cannot naturally resize to tab content and creates a monolithic page.
5. All tabs are generated eagerly, and the browser cannot request page-specific data.
6. The single context dictionary tightly couples all calculations to all views.

This architecture discards most of Streamlit’s built-in layout, widgets, multipage navigation, and reactivity while retaining its rerun model. Generic Streamlit limitations are not the sole cause.

#### What Flask would buy—and cost

Flask would provide true routes, server-rendered templates or JSON endpoints, URL-addressable filters, finer-grained requests, direct JavaScript interactions, and conventional session/auth middleware. But a rewrite must also supply components Streamlit currently provides: controls, reactive refresh behavior, session state, error/loading states, deployment plumbing, CSRF protection, and authentication/authorization. Flask alone is not a frontend; a polished interactive dashboard would still require Jinja plus JavaScript or a separate frontend framework.

#### Middle ground

First remove the iframe and use native Streamlit multipage/navigation, fragments/forms, cached data marts, and Plotly components. If a custom visualization is truly necessary, isolate it as a Streamlit component rather than embedding the whole app. A framework such as Dash could also suit Plotly-heavy interactions, but changing frameworks before proving the data model creates work without resolving fee/profit ambiguity.

#### Recommendation

**Do not migrate now. Reassess after the transaction mart, profit model, and redesigned information architecture have been used in Streamlit.** Data correctness is the blocking issue, and neither Flask nor another UI framework fixes it. Migrate later only if validated requirements include deep-linked views, many simultaneous users, independent partial data refreshes, complex drill-through/edit workflows, durable user state, or action execution that native Streamlit cannot support cleanly.

If those requirements are proven, migrate after Phase 8 roadmap stages 1–3, not before. Relative effort is high: it is an application rewrite plus frontend/state/auth work, while the data and calculation modules should remain reusable.

---

## Phase 2 — Transactions ↔ sales linkage

### 2.1 Verified linkage

`transactions."Order ID"` can join to `orders."amazon-order-id"` for order-related rows. The recommended bridge is:

```sql
transactions."Order ID" = orders."amazon-order-id"
```

The join should first aggregate each side to a controlled grain:

- Sales: order + SKU/ASIN, using an approved order-state and revenue rule.
- Transactions: economic event + order + product detail, after deduplication and lifecycle resolution.

Do not join raw rows directly: an order may contain multiple order items and multiple transaction lines, causing a many-to-many multiplication.

### 2.2 What can be exact now

For matched Order Payment, Refund, and related order-linked rows:

- product charges,
- promotional rebates,
- aggregate `Amazon fees`,
- other adjustments,
- and resulting transaction total

can be attached exactly to the relevant order/event.

If an order has one sale line, the fee can be assigned exactly to that line. For multi-line orders, the current transaction product text may be mapped to the SKU dimension; otherwise allocate the order’s fee across lines by net product revenue and label that allocation as estimated.

The current table cannot determine how much of `Amazon fees` is referral versus fulfillment. Exact total fee is not the same as exact fee-category detail.

### 2.3 What remains aggregate

Service Fees, storage, returns fees, subscription-like charges, advertising invoices, reimbursements, adjustments, and other non-order events use `---` or non-order reference IDs. These belong in a period fee ledger, classified from `Transaction type` plus normalized `Product Details`.

Allocate only when a business use requires SKU profitability:

1. Direct SKU/ASIN mapping when product detail or a richer report provides one.
2. Product family/category allocation when the fee is category-specific.
3. Storage by average inventory units/cubic volume if those drivers become available.
4. Otherwise by net revenue share or units fulfilled for the same settlement month.
5. Keep company-level fees unallocated in the cash P&L and show them below SKU contribution profit rather than implying false precision.

### 2.4 Timing, status, currency, and event rules

- Keep `sale_date`, `transaction_date`, `settlement_period`, and `imported_at` separately.
- Use accrual views for SKU economics and cash views for Amazon disbursements; do not blend them.
- Resolve Deferred/Released status using a stable event key and latest-known state. If Amazon supplies a transaction identifier in a richer export, use it. The current `transaction_uid` is not unique.
- Model refunds, chargebacks, reversed reimbursements, and liquidation proceeds as separate signed events linked back to the original order where possible.
- Store signed numeric amounts in decimal columns and validate the accounting identity:

```text
Total product charges
+ Total promotional rebates
+ Amazon fees
+ Other
= Total (USD)
```

- Assert currency by marketplace and convert only with an explicit dated FX table. The current transaction extract is USD; order sources contain multiple currencies.
- Publish both “sales through date” and “transactions through date” freshness badges because settlement lag makes a same-day comparison incomplete.

---

## Phase 3 — Fee extraction and categorization

### 3.1 Classification achievable from the current extract

Create a normalized `fee_ledger` with fields including:

```text
fee_event_id, order_id, event_date, settlement_period, status,
transaction_type, product_detail_normalized, fee_category,
fee_subcategory, amount, currency, allocation_method,
is_exact, source_file, imported_at
```

Proposed rules, in precedence order:

| Category | Current-source rule | Precision |
|---|---|---|
| Referral fee | Not explicitly identifiable inside `Amazon fees` | Unavailable as exact category |
| FBA fulfillment fee | Not explicitly identifiable inside `Amazon fees` | Unavailable as exact category |
| FBA returns processing | `Transaction type = Service Fees` and product detail contains customer returns/returns processing | Exact event amount, usually aggregate |
| FBA inventory storage | Service Fees + inventory storage / long-term storage | Exact event amount, aggregate |
| AWD storage | Service Fees + AWD storage | Exact event amount, aggregate |
| Refund fee/reversal | Refund rows; retain signed `Amazon fees` | Exact aggregate Amazon-fee reversal, not component |
| Reimbursement/liquidation | Corresponding transaction type; treat as income/recovery, not negative fee | Exact event |
| Other fee/adjustment | Service Fees/Other plus normalized detail mapping | Exact event, category depends on description |
| Advertising invoice | Product detail indicates advertising | Exact if present; none was proven in the observed examples |

Maintain classification rules in a versioned mapping table, with an `unmapped` queue. Never force an unknown description into referral or FBA.

### 3.2 Required richer source for an exact split

Ingest Amazon’s detailed settlement/transaction report containing amount type, amount description, SKU, order ID, fulfillment ID/shipment ID, and amount. That would permit explicit mappings such as Commission/Referral Fee, FBAPerUnitFulfillmentFee, FBAWeightBasedFee, storage, refund administration, and other report-specific descriptors.

Until then, the dashboard should show:

- **Exact Amazon fees (combined)** for matched order events;
- **Exact other/periodic fee events** where directly present;
- **Estimated referral fee** only if computed from an approved category/price schedule;
- **Estimated fulfillment fee** only from an approved SKU/size-tier rate card;
- and a residual:

```text
Unexplained order fee =
exact combined Amazon fee
− estimated referral fee
− estimated fulfillment fee
```

Residual drift is a diagnostic, not a fee category.

### 3.3 Effective fee rates

Use item-price revenue as the denominator:

```text
effective_fee_rate =
abs(fee_amount) / positive_item_price_revenue
```

Report:

1. category-specific rates where category detail is known;
2. combined order-fee rate by SKU/product family and month for matched orders;
3. periodic-fee burden by month and fee subcategory;
4. total Amazon take rate including allocated periodic fees.

Prefer rolling 28-day or settlement-month rates with minimum-volume thresholds. Segment by SKU only where there are enough matched orders; otherwise back off hierarchically to product type, then global. Display sample size and coverage with every segmented rate.

Do not calculate a single fee percentage using reimbursements, refunds, and service fees in one numerator. Keep event classes separate and preserve signs.

---

## Phase 4 — Profit estimation model

### 4.1 Canonical measures

At order-item/SKU-period grain, revenue is deliberately defined as item price only:

```text
Item-price revenue
= orders.item-price

Contribution profit before ads
= item-price revenue
− COGS
− exact matched Amazon fees
− allocated periodic Amazon fees

Net contribution profit
= contribution profit before ads
− allocated PPC spend

Operating profit
= net contribution profit
− other tracked operating costs
```

Do not add or subtract `item-tax`, `shipping-price`, `shipping-tax`, `gift-wrap-price`, `gift-wrap-tax`, `item-promotion-discount`, or `ship-promotion-discount` in any revenue or profit measure. Refunds remain separate negative economic events in the transaction model; they do not change this definition of the revenue input.

COGS must come from a dated SKU cost ledger:

```text
sku, effective_start, effective_end, unit_cogs, inbound_freight,
duty, prep_cost, packaging_cost, currency, source/approval
```

For packs, use SKU-level COGS rather than multiplying a global “per pair” assumption. COGS should follow the unit sold and reverse on refunded/returned inventory only according to the accounting policy.

### 4.2 PPC allocation

The current PPC export is confirmed not to contain advertised SKU/ASIN. Until a different export supplies that field:

- keep PPC exact at account/campaign/target/search-term period grain;
- show SKU contribution profit **before ads**;
- show account- and campaign-level profit **after ads**, because spend is exact at those grains;
- do not fabricate a SKU allocation from attributed sales or product-name inference;
- display: “SKU-level advertising allocation is unavailable because the PPC export does not contain advertised SKU/ASIN.”

With advertised SKU/ASIN data, allocate spend directly to the advertised SKU for product economics, while also preserving attributed advertised-versus-other SKU sales. Do not allocate spend based solely on attributed ad sales, as that makes weak products appear to consume less cost.

### 4.3 Uncertainty representation

Every profitability record should carry:

```text
fee_exact_amount
fee_estimated_amount
ppc_exact_amount
ppc_allocated_amount
cogs_source/status
join_coverage
confidence_tier
```

Suggested UI:

- **Verified:** exact order-level fee + maintained COGS + directly mapped PPC.
- **Mostly verified:** exact combined order fee, but periodic fee or PPC allocation is estimated.
- **Estimated:** rate-card fees and/or fallback COGS.
- Show a profit range by varying estimated fee/COGS/PPC allocations over observed or approved bounds.
- Tooltips must state the allocation method and coverage. Never merge exact and estimated values without labels.

### 4.4 Reconciliation controls

For each closed settlement month:

```text
Actual transaction total
= product charges + promotions + Amazon fees + other

Estimated/allocated fee total
= sum(exact matched fees) + sum(allocated periodic fees)

Fee variance
= estimated/allocated fee total − actual fee deductions
```

Publish:

- matched-order coverage by rows, orders, and dollars;
- actual versus modeled Amazon fees;
- unexplained residual dollars and percentage;
- Deferred versus Released balance;
- sales-to-transaction lag distribution;
- unmatched sales orders and unmatched transaction references;
- beginning-to-ending revisions caused by late refunds/reimbursements.

Target thresholds should be agreed with finance, for example ≥98% of Released transaction dollars accounted for and unexplained fee variance under 1% for closed periods.

---

## Phase 5 — PPC/advertising analytics redesign

### 5.1 What exists now

The repository already computes:

- spend, ad-attributed sales/orders/units, impressions, clicks;
- CTR, CPC, CVR, ACOS, ROAS, TACOS;
- weekly revenue/TACOS trend;
- target/match-type rollups;
- rule-based actions (`Scale`, `Monitor`, `Lower Bid`, `Pause / Reduce`);
- numeric suggested CPC based on `current CPC × target ACOS / actual ACOS`;
- an LLM executive narrative using precomputed summaries.

This is a reasonable base, but it uses ad-attributed performance in isolation and a fixed 25% target ACOS rather than contribution-margin-aware break-even economics.

### 5.2 Gaps and proposed analytics

| Need | Proposed measure/view | Required data |
|---|---|---|
| True search-term waste | Search terms with spend/no orders, spend above break-even allowance, low CVR, repeated near-duplicates; negative-keyword candidates | Already has search term metrics; add campaign/ad-group/target relationship validation and search-term history |
| Campaign efficiency | Spend, sales, ACOS, TACOS contribution, CVR, new-to-brand if available, budget utilization | Current campaign fields; add daily budget, status, campaign type |
| Product profitability after ads | SKU net contribution before and after directly attributable spend; break-even ACOS | Advertised SKU/ASIN, purchased SKU/ASIN, COGS, fees |
| Placement performance | Top of Search/Product Pages/Rest of Search efficiency | Placement report and placement modifiers |
| Bid quality | Actual bid versus suggested bid, expected impact, confidence, last change | Keyword/target bid, status, change history |
| Budget constraints | Lost opportunity caused by budget caps; pacing | Campaign budget, budget rule, status, hourly or daily delivery |
| Organic/ad interaction | TACOS, organic sales estimate, incrementality proxy | Total sales by SKU and attributed ad sales by SKU |
| Trend quality | Period-over-period decompositions and statistical control bands | Stable daily fact table with deduplication |

### 5.3 AI enhancements

AI should explain deterministic analytics, not replace them.

#### Anomaly detection and explanation

- Detect spend, ACOS, CVR, CPC, clicks, attributed sales, and net-profit changes using robust rolling baselines, minimum-volume gates, weekday seasonality, and change-point detection.
- Decompose causes: for example ACOS rose because CPC increased 12% while CVR fell 18%, concentrated in two search terms.
- Required: daily clean history, campaign/target IDs, bid/budget/status history, search terms, and SKU profitability.
- LLM role: turn the detected facts and drivers into plain language with evidence links.

#### Automated weekly narrative

- Produce “what changed, why, financial impact, recommended next checks.”
- Compare fixed, complete periods; identify data lag and low confidence.
- Required: all curated marts, prior-period baselines, alert results, and freshness metadata.
- Each sentence should reference the metric/query payload used; store the generated report for audit.

#### Bid and budget recommendations

- Compute break-even ACOS from SKU contribution margin, then estimate a safe bid from CVR, average order value, and target profit.
- Include confidence intervals/minimum clicks and constrain daily changes.
- Required: bid, budget, placement, target IDs, advertised/purchased SKU, change history, margin.
- Start **advisory-only** with approve/reject feedback. API execution should be a later, separately authorized feature with limits, audit log, rollback, and human approval.

#### Forecasting

- Forecast spend, attributed sales, total sales, ACOS/TACOS, and contribution profit at campaign/SKU level where volume supports it.
- Use backtested statistical models with seasonality and event flags; report prediction intervals.
- Required: longer stable daily history, budgets/bids/status changes, promotions, stockouts, Prime Day/holiday calendar, prices, and inventory.
- Do not use an LLM as the numeric forecaster; use it to explain model output and risk.

---

## Phase 6 — Business questions the dashboard should answer

| Category | Business questions | KPIs | Proposed module |
|---|---|---|---|
| Growth & revenue | Are sales growing? Which SKUs, channels, regions, and price/mix changes explain it? | Net revenue, orders, units/pairs, AOV, ASP, growth, mix contribution | Executive; Sales & Products |
| True profitability | What did each SKU/order contribute after COGS, Amazon fees, and ads? | Contribution profit, net contribution profit, margin, profit/unit, break-even ACOS, exact/estimated share | Profitability |
| Fee trends | Is Amazon’s take increasing, and which fee class caused it? | Combined order fee rate, referral/FBA rate when available, storage/returns/other fees, residual | Fees & Reconciliation |
| Ad efficiency | Is advertising profitable, not merely attributed-sales efficient? Where is spend wasted? | Spend, ACOS, TACOS, CVR, ROAS, profit after ads, wasted spend, marginal return | Advertising |
| Cash reconciliation | Why does storefront revenue differ from Amazon cash, and how long is the lag? | Released payout, deferred balance, sales-to-settlement bridge, refunds, reimbursements, lag days, unreconciled dollars | Cash & Settlements |
| Inventory/COGS | Can the profit and stock-risk figures be trusted? What may stock out? | COGS coverage/freshness, units on hand, days of cover, stockout date, lost-sales risk | Inventory & Costs |
| Alerts/anomalies | What changed materially and what action is justified? | Margin/fee/PPC/inventory anomalies, estimated dollar impact, confidence, owner/status | Alerts & Actions |
| Data trust | Is the dataset complete, fresh, reconciled, and deduplicated? | Freshness, duplicates, unmatched IDs, reconciliation variance, model coverage | Data Quality |

---

## Phase 7 — Redesigned dashboard blueprint

### 7.1 Information architecture

#### 1. Executive

- **Purpose:** one-page operating scorecard.
- **Questions:** growth, profit, cash, advertising, inventory, and exceptions.
- **Displays:** net revenue, net contribution profit/margin with confidence, Amazon take rate, ad spend/TACOS/profit after ads, payout received, deferred balance, inventory risks; waterfall from sales to profit; prior-period deltas; top three evidence-backed alerts.
- **Sources:** sales mart, fee ledger, COGS ledger, PPC mart, settlement mart, inventory mart.

#### 2. Sales & Products

- **Purpose:** explain demand and mix.
- **Questions:** what grew/declined, which products/regions/pack types drove it, and at what price.
- **Displays:** revenue/orders/units/AOV/ASP, trend, contribution decomposition, SKU table, product mix, geography, refund rate, drill-through to order items.
- **Sources:** canonical order-item sales fact + product dimension + refund link.

#### 3. Profitability

- **Purpose:** make unit economics actionable.
- **Questions:** which SKUs/orders are profitable after all known costs, and how confident is the answer?
- **Displays:** sales-to-profit waterfall; SKU profit/margin/profit per unit; COGS, exact fees, allocated fees, PPC; break-even ACOS; confidence/coverage; scenario toggle for allocation assumptions.
- **Sources:** sales, fee ledger/allocation, SKU COGS, PPC allocation.

#### 4. Fees & Reconciliation

- **Purpose:** audit Amazon deductions.
- **Questions:** what fees were charged, what changed, and does the model reconcile?
- **Displays:** fee trend/category, combined order fee by SKU, periodic fees, actual-versus-modeled variance, residual, unmatched events, Deferred/Released lifecycle, classification queue.
- **Sources:** transaction events, detailed settlement report when available, sales bridge, classification mapping.

#### 5. Advertising

- **Purpose:** optimize paid growth against profit.
- **Questions:** which campaigns/targets/search terms create profitable sales, waste spend, or need budget?
- **Displays:** campaign funnel, ACOS/TACOS/profit after ads, campaign/target/search-term drilldown, wasted-spend table, break-even targets, trend/anomalies, advisory bid/budget queue.
- **Sources:** PPC mart, search-term report, bids/budgets/status, placements, SKU profit.

#### 6. Cash & Settlements

- **Purpose:** explain what Amazon paid and when.
- **Questions:** how does recognized sales activity bridge to cash, what is deferred, and what remains unmatched?
- **Displays:** sales-to-payout waterfall, payout/transaction timeline, lag distribution, refunds/reimbursements/liquidations, deferred balance, settlement drill-through.
- **Sources:** transaction ledger, settlement/payment identifiers from richer export, sales.

#### 7. Inventory & Costs

- **Purpose:** manage stock and cost trust.
- **Questions:** what may stock out, what capital is tied up, and which SKUs lack current cost?
- **Displays:** on-hand/inbound/reserved where available, days of cover, forecast stockout, velocity, COGS current/missing/stale, landed-cost history.
- **Sources:** inventory snapshots, sales velocity, purchase/inbound data if added, COGS ledger.

#### 8. Alerts & Actions

- **Purpose:** one prioritized work queue.
- **Questions:** what changed, why, expected dollar impact, and who should act?
- **Displays:** anomaly cards, evidence, severity/confidence, recommended action, owner/status, approve/reject feedback for PPC advice.
- **Sources:** anomaly outputs across all curated marts; action history.

#### 9. Data Quality

- **Purpose:** make trust visible.
- **Displays:** source freshness, row counts, duplicates, schema failures, order/transaction match coverage, fee reconciliation, unclassified descriptions, missing COGS/PPC mappings.

### 7.2 Engineering work

1. Define canonical accounting and lifecycle rules with finance/operations.
2. Add typed staging models for orders, transactions, PPC, product, inventory, and COGS.
3. Build transaction deduplication/status resolution and a versioned fee classifier.
4. Build order-to-transaction bridge at safe grains; add match diagnostics.
5. Ingest the detailed settlement report for referral/FBA component accuracy.
6. Add SKU dimension and effective-dated COGS ledger.
7. Build exact/allocated fee and PPC modules with lineage and confidence fields.
8. Create daily/order-item/SKU-period marts and settlement/cash marts.
9. Replace duplicated Pandas calculations with tested domain modules.
10. Rebuild views around the proposed IA; remove the whole-app iframe.
11. Add anomaly/forecast services; feed only validated result packets to the narrative AI layer.
12. Add tests for identities, date windows, signs, currencies, joins, deduplication, and reconciliation.

---

## Phase 8 — Phased implementation roadmap

### Stage 0 — Definitions and data contracts (small, prerequisite)

- Agree revenue, refund, order-status, currency, COGS, accrual-versus-cash, and fee-allocation rules.
- Define source freshness and reconciliation thresholds.
- Profile source-file overlap causing UID/business-key duplicates.
- Deliverable: metric dictionary, event-state rules, accepted sample reconciliations.

### Stage 1 — Transaction mart and reconciliation (medium, highest priority)

- Type and normalize `transactions`.
- Resolve Deferred/Released states and duplicates.
- Classify Service Fees/other events; expose unmapped descriptions.
- Safely join order-linked events and build the settlement bridge.
- Ship a Data Quality/Fees reconciliation view in the existing Streamlit app.
- Dependency: Stage 0. This can ship without COGS or PPC changes.

### Stage 2 — Profit foundation (medium/large)

- Add effective-dated SKU COGS.
- Produce exact combined order fees, allocated periodic fees, confidence/coverage, and profit ranges.
- Add Profitability tab and sales-to-profit waterfall.
- Dependency: Stage 1 and approved COGS data.
- Incremental value: contribution profit before ads can ship before SKU-level PPC allocation.

### Stage 3 — PPC mart and profit-aware advertising (medium/large)

- Fix PPC identity/deduplication.
- Ingest advertised/purchased SKU, bid, budget, placement, status, and change history.
- Add search-term waste, SKU profit after ads, break-even ACOS, and advisory actions.
- Dependency: Stage 2 for margin-aware recommendations.

### Stage 4 — Information architecture redesign in Streamlit (medium)

- Remove the monolithic iframe.
- Implement native pages, shared filters, lazy data loading, URL-friendly navigation where practical, and the proposed modules.
- Consolidate calculations and add tests.
- Dependency: stable marts from Stages 1–3. Individual pages can migrate incrementally.

### Stage 5 — AI analytics (medium, incremental)

- Add deterministic anomaly detection and backtested forecasts.
- Generate narratives from structured evidence with citations to dashboard entities.
- Add action feedback and an audit log.
- Keep bid/budget recommendations advisory-only initially.
- Dependency: trustworthy daily marts and profit model.

### Stage 6 — Framework migration decision gate (high if approved)

- Assess actual usage, concurrency, required drill-through/edit flows, authentication, deployment, and Streamlit performance.
- Migrate to Flask plus Jinja/JavaScript or another chosen frontend only if the validated requirements justify it.
- Reuse the typed marts and domain calculation layer; do not combine migration with fee-model discovery.
- Sequence: after Stages 1–3, preferably after the Streamlit IA proves the workflows.

### Stage 7 — Optional controlled ad execution (high risk, separate authorization)

- Integrate the Amazon Ads API only after advisory recommendations are calibrated.
- Require explicit approval, bounded changes, audit records, monitoring, and rollback.
- Dependency: recommendation backtests, stable identifiers, permissions, and operational ownership.

---

## Acceptance criteria for the first meaningful release

The dashboard becomes decision-grade when:

- order-linked transaction coverage and unmatched dollars are visible;
- Deferred and Released states cannot be double counted;
- monthly combined Amazon fees reconcile to source deductions within an agreed tolerance;
- every profit KPI distinguishes exact from allocated/estimated inputs;
- no SKU is shown as “net profitable” without current COGS and a disclosed PPC allocation status;
- PPC waste is evaluated at customer-search-term level;
- freshness, currency, and period boundaries are explicit;
- and every AI statement is traceable to a computed metric or detected event.

---

## Follow-up addendum — Multi-brand scope, revenue, and PPC SKU gap

### A. Brand/ASIN join findings

The `asins` table contains 12 ASINs, all described as Litet sock variants. The exclusion of other Amazon.com orders is overwhelmingly caused by the limited product dimension, not by scattered test records.

Filter waterfall using item price as revenue:

| Population | Rows | Distinct ASINs | Distinct orders | Item-price revenue | Units |
|---|---:|---:|---:|---:|---:|
| All `orders` | 10,577 | 83 | 9,750 | $177,912.20 | 10,868 |
| Amazon.com | 10,453 | 83 | 9,632 | $168,952.90 | 10,621 |
| Amazon.com and quantity > 0 | 9,818 | 83 | 9,035 | $168,803.93 | 10,621 |
| In current `asins` dimension | 2,277 | 12 | 2,131 | $57,902.50 | 2,456 |
| Outside current `asins` dimension | 7,541 | 71 | 6,905 | $110,901.43 | 8,165 |

The current dashboard therefore excludes 76.8% of eligible Amazon.com rows and 65.7% of eligible item-price revenue. The earlier audit’s 2,329 figure described the ASIN/channel match before the positive-quantity filter; the fully prepared `sales_df` population is 2,277 rows.

Product-title clustering of the 7,541 excluded rows:

| Name signal | Rows | Distinct ASINs within titles | Distinct orders | Item-price revenue | Interpretation |
|---|---:|---:|---:|---:|---|
| `Has10` | 5,003 | 41 | 4,576 | $79,422.00 | Clear, coherent brand/product family |
| `Hasten` | 2,390 | 30 | 2,210 | $29,710.45 | Historical title alias of Has10 |
| Other/unclear | 148 | 15 | 136 | $1,768.98 | Mostly unbranded “Spat Cleat Covers” titles; likely legacy listing/title variants |

The group-level ASIN counts are not additive because some ASINs have appeared under different product-title labels over time. Seventeen orders also contain rows from more than one title cluster. The owner has since confirmed that Hasten was Has10’s old name; both clusters therefore resolve to canonical brand `Has10`. SKU prefixes are not useful: they are short, heterogeneous codes rather than stable brand identifiers.

#### Resolved business-owner scope decision

The dashboard will cover the full seller account in one application, with `Litet`, `Has10`, and `All` views. Hasten remains a Has10 title alias and never appears as an independent brand.

This requires:

- a governed product dimension containing every active and historical ASIN/SKU, canonical brand, product family, pack/size/color, effective dates, and listing-title aliases;
- effective-dated COGS and landed-cost records for the second-brand SKUs;
- exhaustive campaign-to-brand mapping using the owner-approved campaign-name rule;
- brand-aware fee, refund, inventory, and profitability views;
- historical alias handling so title changes do not fragment one ASIN;
- brand-level data-quality coverage and reconciliation tests.

The existing ASIN filter must not be expanded ad hoc; it should be replaced by the governed dimension described in the later multi-brand addendum.

### B. Confirmed revenue definition

For this dashboard:

```text
Revenue = orders.item-price

Contribution profit before ads
= item-price revenue
− COGS
− exact matched Amazon fees
− allocated periodic Amazon fees
```

`item-tax`, `shipping-price`, `shipping-tax`, `gift-wrap-price`, `gift-wrap-tax`, `item-promotion-discount`, and `ship-promotion-discount` are outside scope. They must not be added to or subtracted from revenue or profit. This clarification is now reflected in Phase 4 and in the effective-fee-rate denominator.

### C. Design for the confirmed PPC SKU gap

The PPC export has real spend at account/campaign/target/search-term grain but no advertised SKU/ASIN field. The redesigned modules should preserve that boundary:

| Module/grain | Metric shown | Treatment |
|---|---|---|
| Profitability — SKU | Contribution profit before ads | Item-price revenue minus COGS and Amazon fees; fully computable once the fee and COGS models exist |
| Profitability — account/brand where mapping is valid | Profit after ads | Subtract real PPC spend at the supported aggregate grain |
| Advertising — campaign | Campaign profit after ads | Use campaign spend and an explicitly documented revenue/profit comparison; do not imply SKU attribution |
| Advertising — target/search term | PPC efficiency and waste | Spend, sales, ACOS, CVR, and waste rules; not SKU net profit |

Required UI notice:

> SKU-level advertising allocation is unavailable because the PPC export does not contain advertised SKU/ASIN. SKU profit is shown before ads; after-ad profit is shown only at account or supported campaign/brand level.

Campaign-to-brand allocation now follows the exhaustive owner-approved name rule, so all campaign spend has a brand. This does not create SKU attribution: the system must not infer SKU spend from attributed sales, product-title text, or proportional SKU revenue. A future advertised-SKU field can unlock direct SKU profit after ads without changing the item-price revenue, COGS, or Amazon-fee model.

---

## Addendum — Governed multi-brand dimension and unified architecture

### 1. Product/brand dimension

#### Canonical brands and alias resolution

The seller account has two canonical brands: `Litet` and `Has10`. `Hasten` is not a third brand; it is a historical listing-title alias for `Has10`.

```text
title contains "Has10"  -> Has10
title contains "Hasten" -> Has10
ASIN resolved to Has10 + unbranded historical title -> Has10
current governed Litet ASIN -> Litet
otherwise -> Unassigned
```

The third rule is evidence-based alias resolution, not a title guess: every ASIN behind the 148 currently unbranded-title rows also has a Has10/Hasten-branded title in its observed history. The eligible catalog resolves as follows:

| Brand | ASINs | Rows | Item-price revenue | ASIN–SKU links | Title aliases |
|---|---:|---:|---:|---:|---:|
| Litet | 12 | 2,277 | $57,902.50 | 21 | 22 |
| Has10 | 71 | 7,541 | $110,901.43 | 101 | 109 |
| Unassigned | 0 | 0 | $0.00 | 0 | 0 |
| Total | 83 | 9,818 | $168,803.93 | 122 | 131 |

No observed ASIN has conflicting Litet and Has10 evidence. `Unassigned` must remain valid for future imports even though all 83 current ASINs resolve.

#### Governed model

A flat row per ASIN is insufficient because ASINs can have multiple SKUs and titles over time. Use three governed tables or equivalent typed models:

```text
dim_product
  product_key, asin, canonical_brand, product_family,
  canonical_product_name, size, color, pack_type,
  units_per_sellable_unit, first_observed_date, last_observed_date,
  active_status, effective_start, effective_end, is_current,
  assignment_method, assignment_confidence, reviewed_by, reviewed_at

bridge_product_sku
  product_key, asin, sku, seller_marketplace,
  effective_start, effective_end, is_current

product_title_alias
  product_key, asin, title_alias, alias_brand_text,
  first_observed_date, last_observed_date, source
```

The current 12-row `asins` table becomes a Litet seed, not the future dimension. Order history can seed observed effective dates, but active status requires catalog/listing data or owner review. Product family, size, color, pack, and unit conversions should be governed rather than parsed during each dashboard run.

All Hasten titles remain as alias records for lineage, while their canonical brand is Has10. Historical KPIs must group both title eras into one Has10 series.

#### Mixed-title and mixed-brand orders

The 17 previously flagged mixed-title orders are entirely Has10 after alias resolution:

- 16 combine Hasten titles with unbranded aliases on Has10 ASINs.
- 1 combines Has10 and Hasten title aliases.

Across the full eligible population, only one order genuinely contains both a Litet line and a Has10 line. Brand must therefore be assigned **per order line** using ASIN/SKU, never through an order-level dominant-brand rule.

- `brand orders` = distinct orders containing at least one line for that brand.
- `account orders` = distinct orders overall.
- The `All` view counts the cross-brand order once.
- An order-level fee for that order is allocated across lines by item-price revenue and labeled estimated unless transaction detail identifies the line.

### 2. PPC campaign-to-brand mapping

`campaign_brand_map` is keyed by the exact campaign name. The finalized owner-approved rule is exhaustive:

```text
lower(campaign_name) contains "litet" -> Litet
otherwise                             -> Has10
```

There is no `Unmapped/Shared` campaign bucket and no campaign requires manual review. The implemented table stores `campaign_name`, `brand`, `mapping_rule`, and `is_current`.

#### Coverage

| Mapping | Campaigns | Campaign share | Rows | Row share | Spend | Spend share |
|---|---:|---:|---:|---:|---:|---:|
| Litet | 5 | 16.13% | 5,320 | 21.83% | $14,105.97 | 40.26% |
| Has10 | 26 | 83.87% | 19,052 | 78.17% | $20,927.77 | 59.74% |
| Total | 31 | 100% | 24,372 | 100% | $35,033.74 | 100% |

All 31 campaigns, all 24,372 rows, and 100% of observed spend map deterministically.

Mapped Litet campaigns:

```text
LITET Optimize
LITET Ranking Campaign
LITET Scale
LITET discovery
LITET launch
```

The other 26 campaign names map to Has10 by the finalized fallback rule.

### 3. Brand-aware transaction and fee model

Propagate brand through the shared mart:

```text
transaction
  -> Order ID
  -> order line SKU/ASIN
  -> governed product dimension
  -> canonical brand
```

Observed routing coverage:

| Route | Rows | Distinct references | Amazon fees | Transaction total |
|---|---:|---:|---:|---:|
| Litet order-linked | 1,409 | 697 | -$12,273.71 | $27,334.19 |
| Has10 order-linked | 88 | 58 | -$498.65 | $725.92 |
| Non-order/unmatched | 53 | 23 | -$416.43 | -$653.39 |

All 1,497 order-linked rows receive a canonical brand through the same logic. For the 53 non-order/unmatched events:

1. Assign directly only when detail contains a governed SKU/ASIN or uniquely branded family.
2. Otherwise retain `Shared/Unassigned`.
3. Allocate to brands only under an approved driver, preserving source amount, `allocation_method`, and estimated status.
4. Include every event exactly once in `All`.

Fee classification, lifecycle resolution, signing, reconciliation, and effective-rate calculations remain shared. Add `brand` to their output grain. Brand fee rates use that brand’s item-price revenue denominator and minimum-volume fallback rules; do not substitute a Litet rate for Has10.

This confirms the **designed end-to-end brand path**. It is not yet materialized in SQLite or application code, consistent with this pass’s no-code constraint.

### 4. Unified dashboard architecture

Use one codebase, one set of marts, and one global filter:

```text
Brand: Litet | Has10 | All
```

Apply it before aggregation in Executive, Sales & Products, Profitability, Fees & Reconciliation, Advertising, Cash & Settlements, Inventory & Costs, and Alerts & Actions. Data Quality should additionally expose `Unassigned/Shared`.

`All` must be recomputed from additive facts:

- Sum revenue, units, COGS, fees, and spend once.
- Count account orders distinctly.
- Calculate ACOS, TACOS, margins, AOV, and fee rates from combined numerators and denominators—never average brand ratios.
- Include all mapped PPC and any unassigned non-order fees once at account level.
- Display assignment coverage beside combined KPIs.

#### Litet-specific logic that must be generalized

| Existing logic | Unified treatment |
|---|---|
| Hardcoded PPC load filter `campaign_filter="LITET"` | Remove at mart level; apply the governed campaign map and brand filter |
| Twelve-ASIN Litet allowlist | Replace with the governed 83-ASIN dimension |
| “Pairs sold” as a universal KPI | Use `sellable units`; optionally show pieces/pairs for applicable families |
| Hardcoded single/3-pack/6-pack multiplier | Store effective unit conversion in the product dimension |
| White/Black/Blue and sock-size title parsing | Use governed, family-specific attributes |
| Litet title-cleaning rules | Use canonical names and aliases |
| Flat 25% target ACOS | Use effective-dated brand/family/SKU targets derived from contribution margin |
| AI prompt for “LITET, a cycling socks brand” | Supply selected brand and product families dynamically |
| LITET page branding | Use account identity for `All` and selected-brand context otherwise |
| Inventory demand in `pairs_sold` | Forecast sellable units per SKU; conversions are secondary |
| Fixed pack/color/size product mix | Make breakdowns product-family-aware |

Safe to share across brands:

- ingestion, order/transaction lifecycle rules, and fee classification;
- reconciliation and profit formulas;
- PPC metric definitions;
- anomaly/forecast infrastructure;
- filtering, freshness, permissions, and data quality.

Govern per brand, family, or SKU:

- COGS and landed costs;
- product attributes and unit conversions;
- target/break-even ACOS;
- campaign mapping rule and any future effective-dated overrides;
- fee-rate fallback hierarchy;
- alert thresholds, seasonality, inventory service levels, and narrative terminology.

The result is one dimension-driven application, not two dashboards: shared facts and calculation services with effective-dated brand configuration.
