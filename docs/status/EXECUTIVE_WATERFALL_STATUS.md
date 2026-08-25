# Executive Waterfall Status

Implemented the **Where the money goes** bridge on Executive for This week,
This month (MTD), Last 30 days, and YTD.

- The bridge uses covered sale lines from the profitability mart, COGS from the
  as-of-sale COGS calculation, Amazon and other fees from `fee_ledger`, and
  spend from the clean PPC mart.
- Every step shows dollars and its share of bridge revenue. The final bar uses
  success/danger coloring according to its sign.
- Revenue links to Sales & Products; COGS and profit steps link to
  Profitability; fee steps link to Fees & Reconciliation; ad spend links to
  Advertising. Plotly bars and the accessible step cards are both clickable.
- If PPC does not span the selected period, ad spend and final profit are shown
  as unavailable rather than zero. Incomplete profitability coverage is also
  disclosed, and uncovered sales are excluded rather than assigned zero costs.

## Current Litet MTD example

Data through July 23, 2026:

| Step | Amount | Share of bridge revenue |
|---|---:|---:|
| Revenue | $3,338.89 | 100.0% |
| COGS | -$634.55 | 19.0% |
| Amazon fees | -$1,672.75 | 50.1% |
| Other / periodic fees | +$1.20 | 0.0% |
| Profit before ads | $1,032.79 | 30.9% |
| Ad spend | -$1,203.23 | 36.0% |
| Final profit | -$170.44 | -5.1% |

The bridge covers $3,338.89 of $3,603.78 selected-period revenue (92.6%).
Eleven sale lines lack a matched fee/profit result, so their $264.89 of revenue
is disclosed outside the bridge instead of being presented with zero costs.

## Verification

`python -m pytest -q` — **93 passed**.
