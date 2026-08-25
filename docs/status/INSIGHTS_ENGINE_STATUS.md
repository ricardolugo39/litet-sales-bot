# Litet Trend & PPC-Correlation Insights Status

## Implemented

- Added a deterministic, brand-parameterized insights engine in
  `insights_engine.py`.
- Added fixed-calendar, last-complete-period WoW/MoM/QoQ comparisons for
  revenue, sellable units, and contribution profit before ads.
- Added overall, color, size, pack-type, and SKU grains with a configurable
  minimum-order gate (default: 10 orders in both periods).
- Added trailing-variance anomaly scoring. A record is notable only when it
  clears the volume gate, changes by at least 15%, and has an absolute z-score
  of at least 2.
- Added physical-unit pack-mix share and blended revenue-per-product-unit
  comparisons. The existing bundle COGS assumptions are unchanged.
- Added weekly PPC/total-sales series, TACOS, ACOS, ROAS, organic-only sales,
  weak-week segmentation at Litet's 21.62% break-even ACOS, and contemporaneous
  plus next-week correlations.
- Added current inventory days-of-cover and advisory next steps to qualifying
  upward trend records.
- Added COGS source/effective-date context.
- Wired the compact structured records into the existing explicit,
  button-triggered AI summary in both Streamlit and Flask. The AI prompt is
  instructed to narrate supplied calculations without recomputing them or
  claiming causality.

## Product dimension check

The governed Litet dimension contains exactly 12 ASINs and matches the confirmed
catalog:

- Blue: two singles (Small/Medium and Large/X-Large).
- Black: two singles and two 3-packs; no 6-pack.
- White: two singles, two 3-packs, and two 6-packs.

All 12 have populated color, size, and pack type. No inferred product-grid
combinations were added.

## COGS effective-date diagnosis and fix

The diagnosis was confirmed:

| Scope | Before: missing lines | Missing ASINs | Date range |
| --- | ---: | ---: | --- |
| Litet seeded ASINs | 1,607 | 12 | 2025-02-21–2026-04-30 |
| Has10 seeded ASINs | 3,925 | 27 | 2023-11-21–2026-04-17 |
| Has10 genuinely unpriced ASINs | 3,549 | 44 | 2023-01-01–2026-05-29 |

All seeded rows started on 2026-05-01. The seed script now derives its initial
effective date from the earliest eligible Amazon order, 2023-01-01, rather than
from the transaction table. `backdate_placeholder_seeds` updates only
`placeholder_seed` rows; vendor-receipt dates and moving-average behavior are
unchanged.

On a temporary copy of the configured database, 39 placeholder rows were
backdated and the 9,818-row profitability mart was rebuilt:

| Scope | After: missing lines |
| --- | ---: |
| Litet seeded ASINs | 0 |
| Has10 seeded ASINs | 0 |
| Has10 genuinely unpriced ASINs | 3,549 |

Applying the same tested rebuild to the configured OneDrive database was
attempted twice, but the environment's external-write approval review timed
out both times. The production file therefore still needs:

```bash
python seed_stage2_cogs.py
```

## Complete-period trend output

The engine intentionally skips partial periods. With data through 2026-07-24:

| Comparison | Current period | Prior period | Revenue change | Orders |
| --- | --- | --- | ---: | ---: |
| WoW | 2026-07-13–2026-07-19 | 2026-07-06–2026-07-12 | -10.08% ($1,024.70 vs $1,139.59) | 29 vs 40 |
| MoM | 2026-06-01–2026-06-30 | 2026-05-01–2026-05-31 | +16.12% ($8,665.22 vs $7,462.54) | 299 vs 226 |
| QoQ | 2026-04-01–2026-06-30 | 2026-01-01–2026-03-31 | +100.27% ($22,459.64 vs $11,214.48) | 715 vs 389 |

The QoQ change is computed but not marked notable because it is not outside the
normal historical variance for that series. This distinction prevents a large
percentage from automatically becoming a high-priority alert.

## PPC correlations

| Analysis | Correlation | Weeks |
| --- | ---: | ---: |
| Spend vs total sales | 0.897 | 75 |
| Spend vs organic-only sales | 0.781 | 75 |
| Spend vs total sales in weak weeks | 0.892 | 70 |
| Spend vs next-week total sales | 0.666 | 74 |

These are investigative signals, not causal proof. The weekly sample can still
reflect seasonality, shared demand drivers, attribution timing, or reverse
causality. The same caveat and each sample size are included in the structured
AI input.

## Verification

The full test suite passes: **53 passed**.
