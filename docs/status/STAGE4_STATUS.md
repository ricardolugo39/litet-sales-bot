# Stage 4 Native Streamlit Status

## Cutover completed

The production entry point, `dashboard.py`, now uses native Streamlit navigation:

- `st.navigation`
- `st.Page`
- one callable page per module
- one global sidebar brand selector

The base64 document, fixed 3,600-pixel iframe, and client-side JavaScript tab state are no longer part of the application path.

The native pages are:

1. Executive
2. Alerts & Actions
3. Sales & Products
4. Profitability
5. Advertising
6. Fees & Reconciliation
7. Cash & Settlements
8. Inventory & Costs
9. Data Quality

The old `html_dashboard` package remains in the repository for compatibility/history but is not imported or executed by the main dashboard.

## Page-scoped data loading

`native_dashboard/data_service.py` contains small page-specific SQL reads. A page executes only the queries it needs:

- Executive: summary sales, aligned advertising profit, reconciliation, recent sales, and inventory exceptions.
- Sales & Products: product and daily sales aggregates.
- Profitability: profitability and missing-COGS aggregates.
- Fees: fee categories and reconciliation.
- Advertising: campaign metrics, advisory negatives, and aggregate after-ad profit.
- Cash: transaction lifecycle aggregates.
- Inventory: latest snapshot plus recent demand.
- Alerts: only the three exception datasets.
- Data Quality: product coverage, reconciliation, and missing COGS.

No native page loads full `orders`, `ppc`, or inventory history into memory.

Query caching includes:

- SQL text;
- SQL parameters, including selected brand;
- database path;
- database modification time;
- a five-minute TTL.

Therefore changing brand cannot reuse another brand’s cached result. Updating the SQLite database also changes cache identity.

## Global brand behavior

One selector is created before navigation runs:

```text
Brand: Litet | Has10 | All
```

Every page reads the same `global_brand` session-state value and applies it in SQL before aggregation.

`All` behavior:

- additive facts are summed once;
- orders use `COUNT(DISTINCT order_id)`, so the genuine cross-brand order is counted once;
- ACOS, TACOS, AOV, margins, CTR, CVR, and coverage are recomputed from combined numerators and denominators;
- ratios are never averaged across brands;
- unassigned non-order fees remain visible in combined fee/cash/data-quality views.

Integration smoke-test revenue:

| Filter | Item-price revenue |
|---|---:|
| Litet | $57,902.50 |
| Has10 | $110,901.43 |
| All | $168,803.93 |

Switching the selector produced three distinct results with no Streamlit exceptions.

## AI behavior

The AI executive summary is no longer called while constructing dashboard context or when filters change.

- It runs only after **Generate / refresh AI summary** is clicked.
- The result is held separately in session state per brand scope.
- The prompt receives the selected scope and governed product families.
- `All` is described as the combined Litet/Has10 seller account.
- Litet and Has10 prompts use their actual selected brand and product families.
- The legacy context builder now defaults `include_ai=False`.

## Litet-specific logic removed from the native UI

| Previous behavior | Native behavior |
|---|---|
| Twelve-ASIN Litet allowlist | `dim_product` is the only product/brand scope source |
| `campaign_filter="LITET"` | Clean PPC mart plus `campaign_brand_map` |
| “Pairs sold” everywhere | Universal KPI is `sellable units` |
| Title-based color/size/pack parsing | Governed `dim_product` attributes |
| Litet-specific product-name cleaning | Canonical governed product names |
| Fixed 25% target ACOS | Stage 3 contribution-margin break-even ACOS |
| AI prompt hardcoded to Litet socks | Dynamic brand/account and product-family prompt |
| Litet-branded page shell | Seller-account shell with current brand shown on every page |

Pairs/pieces may still be added later as family-specific secondary measures, but they are not presented as a universal account KPI.

## Calculation consolidation

The native dashboard does not import the 1,344-line legacy `calculations.py`.

- Additive roll-ups and ratio rules are centralized in `native_dashboard/metrics.py`.
- Database aggregation and brand predicates are centralized in `native_dashboard/data_service.py`.
- Page modules format and display results but do not reimplement financial formulas.
- Duplicate `format_delta` and duplicated legacy SKU-cleaning blocks were removed.

`calculations.py` remains for the separate legacy Gradio analyst and other non-dashboard scripts; deleting it during this cutover would break those entry points. It is no longer the calculation layer for the production Streamlit dashboard.

## Validation

Automated suite:

```text
Ran 15 tests
OK
```

Stage 4 tests cover:

- brand as part of cached-query identity;
- `All` counting a cross-brand order once;
- combined ACOS/TACOS recomputed from additive facts;
- native navigation present;
- iframe and base64 usage absent from the entry point.

Additional validation:

- Python compilation passed.
- Every page-scoped query ran successfully for `Litet`, `Has10`, and `All`.
- Streamlit `AppTest` loaded the Executive page with zero exceptions.
- `AppTest` switched All → Litet → Has10 and observed the expected revenue changes.

## Files

- Entry point: `dashboard.py`
- Native pages: `native_dashboard/pages.py`
- Page-scoped reads: `native_dashboard/data_service.py`
- Canonical metrics: `native_dashboard/metrics.py`
- Tests: `tests/test_stage4_native_dashboard.py`

## Remaining work

- The old HTML renderer can be deleted after an agreed rollback window.
- The separate Gradio analyst and Prime Day scenario app still use legacy calculations and may be migrated independently.
- URL-persisted filter state and user authentication are not yet implemented.
- The global period selector was intentionally not reintroduced in this cutover; pages state their available/aligned data window. A single governed date-range component should be the next cross-page control.
