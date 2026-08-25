# Global Period Scoping Status

## Global control

The Flask header now owns the single period selector:

- This week
- This month (MTD)
- Last 30 days
- YTD

`brand` and `period` are both URL parameters and are preserved by every sidebar
link, the logo link, brand changes, Executive drill-through links, and the
Advertising bid-change redirect.

All pages use a common reporting-through date: the earlier of the selected
brand scope's latest sales date and latest PPC date. This keeps an identical
period selection on the same calendar boundaries across transactional pages.

## Fully period-scoped pages

- **Executive:** existing period calculations now use the global state.
- **Sales & Products:** revenue, orders, sellable units, AOV, revenue trend,
  and product table filter sale rows before aggregation.
- **Profitability:** revenue, measured coverage, product profitability, and
  missing-COGS detail filter sale rows before aggregation.
- **Advertising:** Spend, TACOS, ROAS, PPC orders, campaign rows, target/search
  term rows, contribution-margin input, and bid suggestions use the selected
  period.
- **Fees & Reconciliation:** fee categories and reconciliation controls are
  recomputed from fee/transaction rows inside the selected transaction-date
  window.
- **Cash & Settlements:** Released/Deferred balances and settlement detail use
  transaction dates inside the selected period.

## Intentionally current-state pages

- **Inventory & Costs:** stock remains the latest available snapshot. The
  selected period controls only the demand velocity used for days of cover.
  Presenting a historical selection as historical stock would be false because
  the page does not reconstruct inventory as of an earlier date.
- **Alerts & Actions:** the queue remains current. A period selection is carried
  through navigation, but it does not freeze operational alerts in the past.
- **Data Quality:** governed-product, reconciliation-coverage, and missing
  reference checks remain current quality state rather than historical totals.

Each exception is labeled on its page.

## Updated PPC sample details

Advertising now also includes the revised reference fields:

- Spend per target/search term.
- Match type as a compact inline Broad/Exact/Phrase badge beside the target.

The previously implemented suggestion gate, confidence dots, relevance flags,
manual bid log, Amazon range capture, and 14-day evaluation remain in place.

## Verification

- Exercised all nine pages × three brand scopes × four period options against
  the real database: **108/108 returned HTTP 200**.
- `python -m pytest -q` — **237 passed**.
