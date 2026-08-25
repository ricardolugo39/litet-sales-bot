# Stage 0/1 Implementation Status

## Implemented

- Idempotent SQLite schema migration: `migrations/001_stage1_analytics.sql`.
- Governed observed product model:
  - `dim_product`
  - `bridge_product_sku`
  - `product_title_alias`
- Exhaustive `campaign_brand_map`:
  - campaign name contains `litet`, case-insensitive → `Litet`
  - every other campaign → `Has10`
- Normalized `transaction_mart` with:
  - typed dates and monetary fields;
  - duplicate economic-event removal;
  - Deferred/Released lifecycle resolution, preferring Released;
  - order matching through `Order ID = amazon-order-id`;
  - brand propagation through the product dimension.
- Normalized `fee_ledger` with exact source amounts, fee category/subcategory, brand, and allocation method.
- Per-brand and combined `fee_reconciliation`.
- Idempotent materializer: `materialize_stage1.py`.
- A **Fees & Data Quality** tab in the existing Streamlit dashboard.
- Automated tests for alias resolution, campaign mapping, lifecycle handling, fee classification, reconciliation, and repeatable materialization.

The migration and materializer were run successfully against the configured SQLite database.

## Materialized table counts

| Table | Rows |
|---|---:|
| `dim_product` | 83 |
| `bridge_product_sku` | 122 |
| `product_title_alias` | 131 |
| `campaign_brand_map` | 31 |
| `transaction_mart` | 1,501 |
| `fee_ledger` | 1,485 |
| `fee_reconciliation` | 4 |

## Product and campaign coverage

- Product dimension: 12 Litet ASINs and 71 Has10 ASINs; no currently observed ASIN remains unassigned.
- Hasten titles resolve to canonical brand Has10 while remaining available as historical aliases.
- PPC mapping: 31/31 campaigns, 24,372/24,372 rows, and 100% of $35,033.74 spend.

| Brand | Campaigns | Rows | Spend |
|---|---:|---:|---:|
| Litet | 5 | 5,320 | $14,105.97 |
| Has10 | 26 | 19,052 | $20,927.77 |

## Transaction and reconciliation results

Lifecycle resolution reduced 1,550 raw transaction rows to 1,501 distinct current economic events.

| Brand | Resolved rows | Matched rows | Row coverage | Dollar coverage | Released balance | Deferred balance | Classified fees | Fee variance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Litet | 1,361 | 1,361 | 100.00% | 100.00% | $13,545.73 | $13,041.90 | -$11,907.23 | $0.00 |
| Has10 | 87 | 87 | 100.00% | 100.00% | $175.45 | $542.63 | -$492.50 | $0.00 |
| Unassigned/non-order | 53 | 0 | 0.00% | 0.00% | -$653.39 | $0.00 | -$661.08 | $0.00 |
| All | 1,501 | 1,448 | 96.47% | 97.66% | $13,067.79 | $13,584.53 | -$13,060.81 | $0.00 |

Additional controls:

- Raw Released balance before deduplication/lifecycle resolution: $13,551.46.
- Raw Deferred balance before resolution: $13,855.26.
- Transaction accounting-identity variance after normalization: effectively $0.00.
- Forty-seven fee-ledger rows remain `Unassigned` because they are non-order service fees without a defensible product/brand key.

## Validation

```text
python -m unittest discover -s tests -v

Ran 3 tests
OK
```

The updated modules also pass Python bytecode compilation.

## Outstanding work

- Referral and FBA fulfillment fees remain combined because the source exposes only `Amazon fees`; a richer settlement export is still required for an exact split.
- Non-order service fees need an approved brand-allocation policy or richer SKU/ASIN detail. They remain explicitly unassigned and appear in `All`.
- `active_status` is currently `Observed`; authoritative active/discontinued status requires catalog data or owner review.
- Lifecycle identity is derived from the available economic fields. A stable source transaction identifier should replace the derived key if Amazon provides one.
- The existing main sales/PPC pages remain Litet-filtered to preserve production behavior. The new Stage 1 Fees & Data Quality tab is multi-brand; the global Litet/Has10/All conversion belongs to the later unified-dashboard stage.
