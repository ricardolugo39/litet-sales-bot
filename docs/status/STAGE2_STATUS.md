# Stage 2 Weighted-Average COGS Status

## Implemented

- `cogs_ledger`: effective-dated, ASIN-keyed moving-average cost history.
- `vendor_receipts`: manually entered receipt/batch log.
- Idempotent placeholder seeding from `seeds/cogs_placeholder_seed.csv`.
- Transactional vendor-receipt posting that:
  1. reads the latest inventory snapshot quantity for the ASIN;
  2. calculates the weighted-average unit cost;
  3. closes the prior current ledger row;
  4. inserts the new current row with full calculation metadata.
- `sales_profitability`: item-price sales joined to the COGS row effective on the sale date.
- Explicit `cogs_status = missing`; missing COGS never becomes zero and affected profit remains null.
- Exact order-level Amazon fees allocated to order lines by item-price revenue.
- A **Profitability** dashboard tab showing brand coverage and a visible “COGS: Missing” table.
- Tests for seeding, excluded ASIN handling, weighted-average receipts, missing inventory fallback, and historical as-of joins.

## Seed results

- Seed rows loaded: 39.
- Effective start: `2026-05-01`, the earliest date in the current `transactions` table.
- Source: `placeholder_seed`.
- Current rows: 39.
- Excluded placeholder ASIN `XXXXXXXXX`: 0 rows.
- All 39 seeded ASINs exist in the governed product dimension.
- All 39 have a record in the latest inventory snapshot dated `2026-07-24`.

The seed uses ASIN as the authoritative key. SKU remains descriptive only. Has10 two-pack costs are already represented as $7.00 in the supplied seed and are not recalculated from SKU.

## Profitability coverage

The mart contains 9,818 eligible Amazon.com positive-quantity sale lines.

| Brand | COGS available lines | COGS missing lines | Available revenue | Missing-cost revenue |
|---|---:|---:|---:|---:|
| Litet | 670 | 1,607 | $19,816.50 | $38,086.00 |
| Has10 | 67 | 7,474 | $1,029.28 | $109,872.15 |
| Total | 737 | 9,081 | $20,845.78 | $147,958.15 |

Most historical lines are intentionally marked missing because the approved seed begins on `2026-05-01`; the order history begins in 2023. The implementation does not backdate placeholder costs beyond the chosen effective start.

Among COGS-covered lines, 715 also have matched Amazon fees and therefore produce contribution profit before ads. Lines missing either COGS or an order fee retain null profit rather than presenting an incomplete figure as final.

## Entering a new vendor receipt

From the repository root, use one of:

```bash
./venv/bin/python record_vendor_receipt.py \
  --asin B0CHMYK31Z \
  --received-date 2026-08-01 \
  --quantity 500 \
  --unit-cost 3.25 \
  --source vendor_invoice \
  --notes "Invoice 1234"
```

or provide the total batch cost:

```bash
./venv/bin/python record_vendor_receipt.py \
  --asin B0CHMYK31Z \
  --received-date 2026-08-01 \
  --quantity 500 \
  --total-cost 1625 \
  --source vendor_invoice \
  --notes "Invoice 1234"
```

The command records the receipt, recalculates COGS, and refreshes all 9,818 profitability rows. Do not insert directly into `vendor_receipts`; use this command so the receipt and ledger update occur in one database transaction.

The formula is:

```text
new average =
  (latest snapshot quantity × current average
   + received quantity × receipt unit cost)
  / (latest snapshot quantity + received quantity)
```

Each receipt records:

- the inventory snapshot date;
- on-hand quantity used;
- prior and new cost inputs through the linked ledger row;
- whether inventory came from the latest snapshot or used a fallback;
- the resulting COGS-ledger key.

## Inventory fallback

If the ASIN is absent from the latest snapshot, on-hand quantity defaults to zero and `inventory_qty_status` is set to `missing_asin_snapshot_default_zero`. If the inventory table is unavailable, the status is `missing_inventory_table_default_zero`. A negative quantity is rejected as unreliable and replaced with zero under `invalid_negative_default_zero`.

When no prior COGS row exists, the new batch unit cost becomes the initial average and the status is additionally flagged `missing_prior_cogs_batch_cost_used`.

These fallbacks are persisted on both the receipt and ledger row; they are not silent.

## Files and commands

- Migration: `migrations/002_stage2_cogs.sql`
- Seed: `seeds/cogs_placeholder_seed.csv`
- COGS logic: `stage2_cogs.py`
- Seed/materialization: `seed_stage2_cogs.py`
- Receipt entry: `record_vendor_receipt.py`
- Tests: `tests/test_stage2_cogs.py`

Re-run the seed/profitability materializer safely with:

```bash
./venv/bin/python seed_stage2_cogs.py
```

The seed is idempotent and will not replace a current vendor-receipt cost.

## Remaining limitations

- The inventory input is a periodic latest snapshot, not a perpetual inventory ledger. Moving-average accuracy depends on that snapshot representing on-hand units appropriately when the receipt is posted.
- The receipt command currently supports one receipt at a time. CSV batch import and an owner-facing entry form are not yet implemented.
- Historical sales before `2026-05-01` remain explicitly missing unless the owner approves an earlier placeholder effective date or supplies historical batch costs.
- Referral and FBA fee components remain inseparable in the current transaction source.
- PPC remains unavailable at SKU/ASIN level, so this view reports contribution profit before ads.
