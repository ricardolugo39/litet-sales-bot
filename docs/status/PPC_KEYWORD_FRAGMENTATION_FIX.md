# PPC Keyword Fragmentation — Root Cause and Fix

## Root cause found

The raw `ppc` table for July 20–24, 2026 contains both:

- `Targeting`: Amazon's keyword identity.
- `Customer Search Term`: a second, varying text value on each activity row.

For `LITET discovery / discovery / men cycling socks / BROAD`, the raw source
contains 19 daily activity rows and 12 distinct values in the second text
column. Examples include `cycling socks`, `cycling socks for men`,
`mens cycling socks`, and `white cycling socks men`. Every row retains the same
`Targeting = men cycling socks`.

There is no join fan-out and no duplicate import in this example:

- Every affected clean-mart row has `dedup_rule = unique_grain`.
- The clean mart preserves the raw rows one-for-one at its daily activity
  grain.
- The page aggregation caused the fragmentation by preferring the varying
  `search_term` value as `display_target` and grouping on it.

The source column name is direct evidence from `ppc.xlsx`; this was not inferred
from the symptom.

## Six-keyword count

Across the full observed history, the ad group has exactly six distinct Amazon
keyword identities at `Targeting + Match Type`:

1. `men cycling socks` / Broad
2. `aero socks` / Broad
3. `road cycling socks men` / Broad
4. `running socks` / Broad
5. `litet cycling sock` / Broad
6. `litet cycling sock` / Phrase

Only three had activity rows during July 20–24. The page now uses the observed
keyword catalog for active campaign/ad-group pairs and left-joins the selected
period's metrics, so the other three correctly appear with zero activity rather
than disappearing.

## Exact reconciliation after the fix

| Row | Clicks | Spend | Sales | ACOS |
|---|---:|---:|---:|---:|
| `men cycling socks` / Broad | 33 | $73.36 | $134.96 | 54.36% |
| Full `discovery` ad group, 6 keywords | 41 | $88.12 | $134.96 | 65.29% |

The reported keyword now renders once. Match type remains part of identity, so
Broad and Phrase versions of the same targeting text remain correctly separate.

## Other campaigns checked

The problem was systemic in the presentation aggregation:

- `LITET Ranking Campaign / Rankings / cycling socks / Broad`: 24 varying
  source-text values were previously eligible to render as separate rows; they
  now aggregate to one keyword identity.
- `Has10 | Blue | Historic Keywords / Blue / cleat covers / Broad`: 31 varying
  source-text values now aggregate to one keyword identity.
- Multiple Cleat Covers campaign targets showed the same pattern.

The clean PPC fact remains at its existing daily detailed grain; only the
keyword-table aggregation was corrected.

## Verification

- Exact console figures above are covered by a regression test.
- All target metrics are recomputed from summed clicks, spend, sales, and orders
  after grouping—not averaged from row-level ratios.
