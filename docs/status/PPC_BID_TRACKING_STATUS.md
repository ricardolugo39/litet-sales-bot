# PPC Page + Bid Tracking Status

## Implemented

- Rebuilt Advertising from the supplied `litet_advertising_sample.html`
  structure: four KPIs, 12-week TACOS-versus-break-even chart, expandable
  campaign rows, in-place target/search-term detail, click-confidence dots,
  and a distinct relevance-review treatment.
- Added the revised sample's per-target Spend value and inline match-type badge.
- Added per-target ACOS and ROAS. Targets with zero orders show `—` for both
  ratios rather than a divide-by-zero or misleading efficiency value.
- Corrected keyword identity to group by Amazon `Targeting + Match Type`.
  Selected-period metrics are joined to the observed keyword catalog for each
  active ad group, preventing varying row-level text from fragmenting one
  keyword while retaining zero-activity keywords.
- Added a cached, manually refreshable **Advertising insights** card with raw
  structured-facts disclosure. The cache is fingerprinted by brand, period,
  and facts.
- The insight input includes campaign/target efficiency, suggested-bid
  direction and confidence, relevance flags, and bid-change calibration.
  Calibration stays explicitly `not enough data yet` until at least two
  evaluable followed suggestions and two evaluable owner overrides exist.
- Added the Executive period pattern to Advertising: This week, This month
  (MTD), Last 30 days, and YTD.
- Added the intentionally simple bid model:

  `suggested bid = CVR × measured contribution margin per order × 80%`

  The displayed current-market proxy is explicitly labeled **Avg CPC**, not
  current bid. Suggestions require at least 30 clicks in the selected window.
- Added `ppc_bid_change` and applied migration
  `migrations/004_ppc_bid_changes.sql` to the configured database.
- Added manual entry in the Flask page and `record_bid_change.py`. Each log
  captures brand, target/search-term identity, date, suggestion at that moment,
  actual bid set, optional campaign/ad group, optional Amazon suggested low/high
  snapshot, and notes.
- Added fixed 14-day before/after evaluation for CPC, CVR, ACOS, spend, and
  orders. Both windows must contain at least 30 clicks. Results identify
  suggestion-followed versus owner-overridden changes.
- The implementation is brand-aware. Litet is the initial operating scope;
  Has10 uses the same schema and calculation path.

## Current Litet MTD example

Data through July 24, 2026:

| Metric | Value |
|---|---:|
| Spend | $1,240.03 |
| TACOS | 33.1% |
| ROAS | 1.6x |
| PPC orders | 55 |
| Break-even ACOS | 32.4% |
| Measured contribution margin per order | $10.39 |
| Campaigns | 4 |
| Target/search-term rows | 193 |
| Rows meeting the 30-click suggestion gate | 4 |

No bid-change history is backfilled. Amazon’s suggested range begins only when
the owner records it with a new change.

## Manual command

```bash
python record_bid_change.py \
  --brand Litet \
  --target-kind search_term \
  --target "cycling socks for men" \
  --date 2026-07-26 \
  --suggested-bid 0.71 \
  --actual-bid 0.71 \
  --amazon-low 0.55 \
  --amazon-high 0.80 \
  --campaign "LITET Scale"
```

## Intentionally deferred

These model upgrades were deliberately left out of this pass:

- Confidence-weighted CVR pooling.
- Recency- or seasonality-aware weighting.
- CPC-based elasticity modeling.

The change log and evaluation history were built now so those upgrades can be
compared against the simple model later using actual outcomes.

## Verification

- All 12 real-data brand/period combinations returned HTTP 200.
- `python -m pytest -q` — **240 passed**.
