# Complete Executive Redesign Status

## KPI cards

Executive now has exactly three headline cards:

1. Revenue
2. Profit — final covered profit after real period PPC spend
3. TACOS

All three show the same latest complete-week scope. WoW compares that value
with the preceding week; MoM compares the same weekly-grain value with four
weeks earlier. No whole-window aggregate competes with the scoped card value.

For the latest complete Litet week, 2026-07-13–2026-07-19:

| KPI | Value | WoW | Four-week MoM |
| --- | ---: | ---: | ---: |
| Revenue | $1,024.70 | -10.1% | -35.7% |
| Final profit after ads | -$20.03 | +86.2% | +90.1% |
| TACOS | 40.9% | +21.8% | +17.4% |

The engine contains 74 real weekly rows and 17 real monthly rows. Final profit
is period contribution profit before ads minus that period's PPC spend; TACOS
is that period's spend divided by total item-price revenue.

## AI-synthesized insights

- Removed the deterministic sentence template and the separate general AI
  summary mechanism.
- Executive now uses one synthesis mechanism over the complete structured fact
  set: every trend grain, pack mix, correlations, inventory flags, anomaly
  scores, real Executive period series, and revenue breakdowns.
- The cache is keyed by brand plus a hash of the underlying facts and reused for
  the current UTC day. **Refresh insights** forces a recompute.
- The prompt prohibits invented numbers, causal claims from correlations, and
  raw SKU/ASIN labels.
- **See the numbers** exposes the complete JSON supplied to the model.

Verified response-contract example:

> White multipacks drove the latest revenue change while final profit remained
> under pressure.

The expandable facts shown beside that response include the underlying period
series, pack/color/size shares, every accepted trend record, inventory cover,
and PPC correlation sample sizes.

A live model call was not completed in this build session. Sending the private
sales, profit, PPC, inventory, and COGS-derived fact set to OpenAI required
explicit data-disclosure approval, and the execution request was rejected.
Once approved, loading Litet Executive without a current cache or clicking
**Refresh insights** runs the implemented synthesis and stores the daily cache.

## Consolidated visuals

- One performance card switches between:
  - monthly Revenue & final profit;
  - monthly TACOS with a labeled dashed break-even ACOS reference.
- One revenue-mix card switches between Pack type, Color, and Size.
- Each mix legend row shows current revenue share and percentage-point change
  versus the previous complete month.

June Litet breakdown examples:

- Pack type: 3-pack 68.3% (-0.3pt), single 26.1% (+4.6pt), 6-pack 5.6% (-4.3pt).
- Color: White 74.7% (-5.5pt), Black 21.4% (+7.6pt), Blue 4.0% (-2.0pt).
- Size: Small/Medium 61.0% (+1.0pt), Large/X-Large 39.0% (-1.0pt).

## Sales & Products and labels

- Long revenue histories aggregate automatically: monthly beyond one year,
  weekly beyond 90 days, daily only for short ranges.
- The tooltip contains one labeled period date.
- No unexplained vertical marker is added.
- Top Products uses `canonical_product_name` as its bar label.
- SKU-grain insight facts also use the canonical product name; the real rendered
  Litet fact set contained no raw SKU label.

## Responsive behavior

At widths below 768px:

- Executive KPI cards collapse to one column.
- The performance-chart and revenue-mix cards collapse to one column.
- The donut and its legend stack vertically.
- Shared KPI rows on the other CEO-readability pages collapse to one column.
- Segmented controls remain horizontally scrollable rather than clipping.

## Verification

- Real-data-copy Executive render: HTTP 200, three KPIs, two insights, two
  consolidated chart containers, and no raw test SKU in rendered text.
- Full automated suite: **66 passed**.
- Inventory urgency sort, Fees, Cash totals, and the ranked Alerts queue remain
  covered by the existing regression suite.
