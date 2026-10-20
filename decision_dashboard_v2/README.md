# Hasten Decision Center v2

Run locally:

```bash
python app.py
```

Open `http://127.0.0.1:5051`.

Analytics read the existing SQLite database. User-saved policies, evaluations and decision records are persisted separately from imported facts. It intentionally
keeps ordered sales, net sales, net proceeds, and profit as separate concepts.

## Database model

Production uses one canonical SQLite database on a Railway persistent volume:

```text
LITET_DB_PATH=/data/litet.db
HASTEN_DECISION_DB=/data/litet.db
```

The second setting puts the intervention log in the same database. Local apps use
an automatically refreshed read-only cache when offline; that cache is disposable
and is not another source of truth.

Production command:

```bash
gunicorn --bind 0.0.0.0:$PORT decision_dashboard_v2.wsgi:app
```

## V2 decision model

- **Executive:** ranks exceptions by actual performance and shows parent-level market context.
- **Products:** analyzes pack/color/size/ASIN results from Amazon actuals, then adds separately labeled Helium 10 parent estimates.
- **PPC:** shows company contribution, traffic concentration, mature vs recent attribution, query relevance and dated market evidence.
- **Decisions:** shares the PPC evidence and human-reviewed test workflow. Product pricing cases remain at `/decisions/pricing`.

The curated competitor snapshot is in `competitor_data.py`. Refresh its values from
Helium 10 on the capture cadence before using competitor trends for a live decision.
Competitor estimates are never added to the company P&L.

## Advertising evidence and experiments

`ppc_evidence.py` is the shared source for PPC and Decisions. It excludes today,
uses Pacific order dates, and never spreads cumulative traffic snapshots into
invented daily sessions. Compatible cumulative boundaries are required. Revenue
is ordered revenue; contribution deducts COGS, order fees and advertising but
excludes refunds and fixed overhead. Exact order fees are summed once per
order/ASIN, with dated Litet FBA/referral estimates explicitly included in coverage.
Incomplete costs or PPC-day coverage suppress contribution totals.

The statistical model is Gamma-Poisson attributed orders per click, allowing
multiple orders per click. Earlier same-brand, same-match-type peers provide the
prior; absent peer evidence produces no modeled rate. The initial visible
assumptions (7-day attribution exclusion, 28-day prior lookback, 10 equivalent
prior clicks, 80% interval) are configurable starting assumptions, not learned
business rules. Risk tolerance, profit reserve and minimum traffic retention
are unset until explicitly saved as a versioned brand policy.

Candidate evaluations compare a documented bid with holding. They sample the
mature order rate and human-supplied ranges for expected daily clicks, CPC,
purchased-product contribution and spillover onto other sales. Ranges are sampled
uniformly and independently; the rate is shared between alternatives. These are
conditional scenarios, not a learned bid-response curve, incremental ROAS, or
causal lift estimates. Correlations (including promotion-excluded results) and
Helium context are descriptive and never override missing economic evidence.
No hardcoded ACoS, click-count or percentage-cut action rules remain on these tabs.

Proposals require confirmed guardrails, current settings, comparable query/product
mix, documented response evidence and complete mature reporting dates. Assumption-only
scenarios can be saved but cannot produce proposals. Human-supplied sources are
labeled and not independently verified. Evaluations retain the model version,
policy version, input ranges and data fingerprint. Proposal creation and approval
recompute eligibility; changed data/settings invalidate earlier evaluations.
Legacy fixed-percent and direct adjustment routes cannot create new bid proposals.
Manual execution requires confirmation of the actual Amazon change. The app does
not change Amazon bids.

Policies and evaluations survive canonical snapshot uploads alongside the
intervention log. Set `DASHBOARD_SESSION_SECRET` to a persistent random secret for
stable CSRF sessions across restarts/workers; otherwise a process-local secret
requires reloading forms after a restart. No new AI API or paid dependency is used.

Focused validation:

```bash
python -m unittest decision_dashboard_v2.test_ppc_evidence decision_dashboard_v2.test_interventions
```

## Decision cards

PPC and Decisions lead with three priority targets (ranked by selected-period spend),
with the remaining targets available in a collapsed list. Each card shows observed
working status, Hold/Increase/Reduce, supported bid amounts, a reason and the next
attribution-review checkpoint. Missing evidence stays "Not enough evidence / Hold";
a conditional experiment is never labeled proven success. Only a current matching
evaluation that passes the existing guardrails can show a numerical proposed change.
The latest evaluation per exact target persists when returning to the page; stale
or rejected scenarios cannot keep recommending a change. Reporting detail, model
settings and scenario inputs remain available under expandable sections. Checkpoint
dates do not schedule notifications or guarantee report completeness.
