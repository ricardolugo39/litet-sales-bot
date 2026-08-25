# Cross-Page CEO Readability Status

## Executive

- Reduced the headline row from six cards to three: item-price revenue, covered
  profit before ads, and covered profit after ads.
- Each headline metric includes its coverage dates. The after-ads card uses the
  PPC-aligned period rather than implying it covers all sales history.
- Added an always-visible **What changed** card containing the top three
  deterministic findings. It does not call the AI service.
- Retained the explicit AI-summary button as an optional narrated interpretation.
- Moved operating controls into a collapsed data-trust/settlement section below
  the performance content.
- There is no separate Flask Litet-insights page. The concise findings are
  therefore merged into Executive rather than duplicated; the underlying
  structured engine remains available to the AI narration action.

## Profitability

- Added a summary sentence stating how many SKUs are profitable before ads and
  their aggregate positive contribution.
- Added deliberate labels for profit, margin, and missing-COGS columns.
- Tables now use horizontal overflow, a content-width table, and explicit
  right-edge padding so the final header and values remain visible rather than
  clipping.

## Advertising

- Added a plain-English verdict before the KPI row: profitable/unprofitable,
  TACOS versus break-even ACOS, and covered profit after ads.
- Existing KPI cards and drill-down tables remain supporting detail.

## Inventory & Costs

- The inventory table is explicitly sorted by days of cover ascending with
  missing values last. The lowest-cover SKUs appear first.

## Alerts & Actions

- Replaced the three category tables with one cross-category ranked action
  queue.
- Every row retains category, severity, item, impact, reason, and suggested next
  step.
- Critical items rank ahead of High and Medium; impact/urgency ranks items
  within each severity level.

## Verification

- Real-data-copy render: all five changed routes returned HTTP 200.
- Executive rendered three KPI cards and three always-visible insights.
- Inventory's first displayed cover values were `0.0`, `0.0`, `0.0`, `12.0`,
  and `18.53`.
- Alerts rendered exactly one table.
- Full test suite: **58 passed**.

This pass changes Flask presentation and prioritization only. The marts,
underlying calculations, Streamlit fallback, and the intentionally unchanged
Fees, Cash, and Data Quality pages were not modified.
