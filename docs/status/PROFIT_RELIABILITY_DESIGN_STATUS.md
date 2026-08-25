# Profit Reliability + Design System Status

## Profit reliability

Executive now separates selected-period sales into:

- **Measured:** COGS is available, the exact order fee is allocated, and the
  order is not in Deferred lifecycle.
- **Pending settlement:** COGS is available, but the order is Deferred or its
  matching fee has not posted. The secondary estimate uses only the measured
  contribution margin from the same selected period.
- **Cost unknown:** COGS is unavailable. Revenue is disclosed, but profit is
  never estimated.

The Profit KPI presents measured final profit as the primary number, pending
contribution-profit as a smaller italic estimate, and cost-unknown revenue
without a profit number. The waterfall uses solid, hatched, and neutral-outline
treatments respectively, with an explanatory legend and drill-through links.

### Current MTD example

Data through July 24, 2026:

| Scope | Measured revenue | Measured final profit | Pending revenue | Pending profit estimate (before ads) | Cost-unknown revenue |
|---|---:|---:|---:|---:|---:|
| Litet | $2,249.25 | -$774.65 | $1,499.45 | $310.24 | $0.00 |
| Has10 | $223.84 | -$319.40 | $805.44 | -$34.11 | $0.00 |
| All | $2,473.09 | -$1,094.05 | $2,304.89 | $424.89 | $0.00 |

Measured final profit includes real period PPC spend. The pending estimate is
incremental contribution profit before ads; it is not added to or presented as
confirmed final profit.

## Site-wide visual system

The shared Flask stylesheet now standardizes every page on:

- IBM Plex Sans for UI text and IBM Plex Mono for numbers.
- Ink, muted, and hint text tokens; cobalt Litet scope; coral Has10 scope;
  aubergine All scope; shared danger and success colors.
- Light-neutral page background, white flat cards, hairline borders, no card
  shadows, 12px card radius, and 8px control radius.
- Reusable `.estimate-boundary`, `.reliability-estimated`,
  `.reliability-hatched-fill`, and `.reliability-unknown-fill` classes for
  certain/estimated/unmeasured states. These are shared conventions, not
  inline Executive-only styles.
- The Plotly template uses IBM Plex Sans, and the reliability chart uses
  Plotly's diagonal pattern fill corresponding to the CSS hatch convention.

## Verification

`python -m pytest -q` — **96 passed**.
