# Period Consistency, Refresh, and Chart Fix Status

## Period-natural comparisons

Each selector now has one matching comparison:

| Selection | Current window | Comparison |
| --- | --- | --- |
| This week | Current Monday through latest PPC-aligned date | Same elapsed weekdays in prior week |
| This month (MTD) | Month start through latest aligned date | Same elapsed days in prior month |
| Last 30 days | Latest aligned 30 days | Immediately preceding 30 days |
| YTD | January 1 through latest aligned date | Same YTD point last year |

If prior-YTD coverage is absent, all cards say **not enough history for a YTD
comparison**.

Concrete correction for Litet This week:

- Before: reused complete-period badges, including Revenue -10.1% and a fixed
  month comparison unrelated to the live July 20–23 value.
- After: July 20–23 is compared with July 13–16:
  - Revenue **+7.7%**
  - final Profit **+75.6%**
  - TACOS **-15.2%**

Only the selected period's natural comparison badge is displayed.

## Baseline-safe changes

Money comparisons switch from percentage to absolute dollars when the prior
baseline is below $100. TACOS switches to percentage-point change below a 1%
baseline. The UI explicitly labels these as **baseline too small for %**.

A regression fixture that previously could produce a meaningless -617% now
shows the absolute change instead.

## Per-period insight cache and mix consistency

- Executive warms four separate daily synthesis-cache entries: This week, MTD,
  Last 30 days, and YTD.
- Cache fingerprints include each period snapshot and selected-period mix, so
  switching periods selects the matching narrative without calling the model on
  every view.
- Manual **Refresh insights** refreshes the currently selected period.
- `selected_period_revenue_mix` is the synthesis source for mix claims.
- The prompt requires the phrase **share of revenue** and prohibits substituting
  a unit-share number from another period.

MTD example:

- Mix panel: 3-pack is **77.9% of revenue**, **+9.7pt vs prior
  month-to-date**.
- Matching synthesis contract: “For this month, 3-pack products are 77.9% of
  revenue, up 9.7 points versus the same point last month.”

This removes the apparent 90.8%-versus-68.3% conflict: 90.8% was explicitly a
complete-week share of physical units, while the selected-period Executive mix
is now consistently revenue share.

Every mix delta includes its basis directly, such as `-0.3pt vs prior
month-to-date`.

## Partial trend period and coverage treatment

- July is included in both performance views.
- The July revenue bar is labeled **Revenue (partial)** and rendered at 42%
  opacity.
- Partial TACOS uses an open marker.
- Unsupported final-profit history remains shaded.
- The overlapping plot annotation was removed. A caption below the chart now
  says: “Final profit is available from March 2026 onward, once
  contribution-profit and ad-spend coverage are both reliable.”
- The TACOS break-even explanation remains inline.

## Data refresh

Executive now has a separate **Refresh data** action, distinct from **Refresh
insights**.

The data action runs in a background thread and:

1. rebuilds Stage 1 governed product, transaction, and fee marts;
2. rebuilds Stage 2 COGS-aligned profitability;
3. rebuilds Stage 3 PPC and advertising marts;
4. clears the shared query cache.

The button displays a running state, polls progress, and reports success/error
plus the last-refreshed UTC timestamp.

The repository has no external source-ingestion connector. The UI therefore
states the exact supported scope: the pipeline rebuilds from the latest raw
tables already ingested into SQLite; it does not claim to pull Amazon APIs or
Access files directly.

## KPI spacing

The date subtitle now has a `0.7rem` top margin below the large KPI value,
visually separating the value from its secondary date range.

## Verification

- All selected-period and comparison paths verified against the real database
  copy.
- July partial-series and March 2026 coverage caption verified in rendered HTML
  and Plotly structures.
- Separate refresh actions and background success/error states covered.
- Full automated suite: **86 passed**.
