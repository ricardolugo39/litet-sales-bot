# Executive Refinements Status

## Live and selected periods

Executive now supports exactly four KPI periods:

- This week
- This month (MTD)
- Last 30 days
- YTD

All three KPIs—Revenue, final Profit after ads, and TACOS—use the same selected
start/end dates and the same PPC-aligned `through` date.

The live period is explicitly marked in progress. A separate strip displays the
latest complete week and its Revenue, final Profit, and TACOS, so the live
partial week is visible without losing the stable comparison baseline.

With the current data:

| Selected period | Revenue | Final profit | TACOS |
| --- | ---: | ---: | ---: |
| This week through 2026-07-23 | $419.82 | -$32.73 | 50.4% |
| July MTD through 2026-07-23 | $3,388.84 | -$210.58 | 35.5% |
| Last 30 days | $7,028.92 | -$411.93 | 27.3% |
| 2026 YTD through 2026-07-23 | $37,062.96 | -$4,573.97 | 27.0% |

## Comparison definitions

The app now uses one explicit definition everywhere:

- **WoW:** latest complete ISO week versus the preceding complete ISO week.
- **MoM:** latest complete calendar month versus the preceding complete calendar
  month.

The KPI badges include tooltip text naming their comparison periods, and the
definition is printed below the complete-week strip. “MoM” no longer means a
week compared with four weeks earlier. For the current dataset, the complete
month comparison is June versus May.

## Insight corrections

- The synthesis prompt states that Executive Profit always means final profit
  after advertising.
- `profit_before_ads` product-grain records remain auditable raw facts but are
  explicitly ineligible for an Executive profit claim.
- The prompt checks the current-period snapshot first. Negative final profit or
  TACOS materially above break-even should outrank a historical growth fact.
- The selected-period snapshot includes explicit flags for negative final profit
  and TACOS above break-even.

An expected correctly prioritized synthesis based on the current facts is:

> This week through July 23, TACOS is 50.4%, more than twice the 21.6%
> break-even level, and final profit is negative at -$32.73.

The prompt test verifies that the current `profit_after_ads`, TACOS,
break-even value, and attention flags are supplied and that before-ads profit
cannot be presented as Executive profit.

## 3-pack concentration check

The reviewed 91% finding is not a small-sample artifact:

- 3-pack physical product units: **69**
- Total physical product units: **76**
- 3-pack share: **90.8%**
- Orders containing 3-packs: **22**
- Total orders: **29**

Pack-mix facts now carry pack orders, total orders, pack product units, and total
product units. The synthesis must suppress or explicitly caveat pack-mix claims
when either total orders or product units are below 10.

## Chart annotations

- The Revenue & final-profit chart now leaves unsupported profit periods blank.
- A shaded annotation explains that final profit is unavailable before complete
  contribution-profit plus PPC coverage and identifies the first supported
  month (March 2026 in the current data).
- The TACOS chart retains its labeled break-even line and adds an inline
  explanation: below the line, ad spend still leaves margin; above it, spend
  exceeds the profit it generates.

## Breakdown redesign

The Pack type / Color / Size switcher remains unchanged, but the narrow donut
has been replaced with a horizontal bar list:

- deliberately contrasting colors;
- category name;
- current revenue share;
- unclipped percentage-point change versus the prior complete month.

The layout uses `min-width: 0`, fixed nonshrinking delta text, and full-width
tracks, eliminating the clipped `+1.0pt` problem.

## Verification

- All four period URLs returned HTTP 200 against the real database copy.
- The selected KPI values changed for every period.
- Latest complete-week values remain visible alongside the partial period.
- The stale cached synthesis containing “profit before ads” has a different
  data fingerprint and is not reused after these fact/prompt changes.
- Full automated suite: **74 passed**.
