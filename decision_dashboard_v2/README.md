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
multiple orders per click. Earlier exact-target history supplies the prior; same-brand, same-match-type peers are a fallback when the target has no positive order history. No usable historical order evidence produces no modeled rate. The initial visible
assumptions (7-day attribution exclusion, forward-selected history, 10 equivalent
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
attribution-review checkpoint. Current bid access does not gate a historical paid-economics assessment;
a conditional experiment is never labeled proven success. Only a current matching
evaluation that passes the existing guardrails can show a numerical proposed change.
The latest evaluation per exact target persists when returning to the page; stale
or rejected scenarios cannot keep recommending a change. Reporting detail, model
settings and scenario inputs remain available under expandable sections. Checkpoint
dates do not schedule notifications or guarantee report completeness.

Cards separately report mature direct paid accounting: when attributed revenue is
below ad spend, it cannot cover the ads even before product costs. This historical
observation is not a statistical forecast, a causal bid verdict or an estimate of
company-wide incremental contribution. Recent results remain separately labeled,
and matching purchased-product costs are required before calling revenue above
ad spend profitable. Hold is reserved for an evaluated candidate rejected with
a currently verified bid; no candidate or missing bid data is not evidence for Hold.

## Historical assessment (ppc-evidence-2)

`ppc_history.py` assesses each exact brand/campaign/ad-group/target/match identity
using all available attribution-mature history. Prior history ends before the
selected start; selected mature clicks update the prior. Recent attributed orders
never train the model. Candidate history lengths are the available reporting-month
counts, chosen by forward-only negative-binomial order prediction. The final earlier
month is withheld from window selection for a separate, limited audit. All-history
sensitivity must also support an affirmative or negative interval verdict. Prior
weight remains explicit and is capped by observed source clicks to prevent tiny
samples supplying invented evidence. Targets with no mature clicks remain pending.

The economic inputs are the latest available month per SKU, up to the decision
cutoff, using exact allocated Amazon fees and recorded COGS. The minimum and maximum
observed SKU margins form an explicit purchased-mix scenario. Current purchased ASIN
mix is not known, so this is not a guaranteed profit bound. Missing product coverage
is labeled and cannot become a confident whole-catalog result. New-product catalog
membership respects first observed dates in historical views.

Measured recent CPC (or selected mature CPC when no recent clicks exist) is compared
with modeled contribution per click. The central break-even CPC range reflects
product-margin scenarios; the larger sensitivity range includes order-rate, history
length and observed average-order-value scenarios. These are model-conditional,
not independently calibrated future-profit confidence bounds. Rates and order values
can change with prices, query quality and placement. Outputs can be Reduce,
Test reduction, Hold, Hold/test expansion or product-mix review, without requiring a
current base bid or saved business policy. Targets without recent clicks are routed
to delivery review, not blindly told to reduce an already inactive bid.

A historical economic direction is distinct from an executable bid proposal. The
existing policy, current settings, response-source, scenario, fingerprint, CSRF and
human approval checks still gate numeric base-bid proposals and remain unchanged.
There is no CPC-to-base-bid proportional shortcut and no automatic Amazon action.
Company-level TaCoS, contribution, traffic concentration and descriptive correlations
remain separate context; organic lift and cannibalization are not inferred from
paid-attributed profitability.

Tests cover as-of costs, future-outcome leakage, the held-out audit, thin-history
prior caps, positive/negative/mixed directions without any base-bid input, missing
cost coverage, long-history sensitivity, inactive delivery and the existing
proposal/approval checks.

The older `prior_lookback_days` field is retained only for policy-form compatibility; it is no longer an editable history limiter. History length is selected by forward tests.

Historical validation is retrospective on the latest loaded attribution values. Archived report vintages are not available, so it does not reconstruct exactly what was knowable on each earlier decision date. Prospective test outcomes remain necessary.

## Recorded base-bid settings (ppc-evidence-3)

`ppc_bid_history.py` compares actual executed changes for an exact
brand/campaign/ad-group/target/match identity. It reads the complete executed log,
not only the 50 records shown in the UI. Unexecuted proposals and mismatched targets
are excluded. Old July logs without a match type or complete matching identity
are not silently merged into a different keyword.

Each executed setting is evaluated after its change day and before the next
recorded change, using only attribution-mature outcomes. Legacy naive server
timestamps can straddle Pacific midnight; both candidate change dates are excluded.
Known promotion days are excluded. The first recorded pre-change baseline may be
used with the reported old bid, explicitly labeled weaker evidence than archived
settings snapshots. Unlogged settings, pauses and budget changes cannot be ruled
out; run persistence is an assumption, not a verified configuration history.

For each distinct price the latest observed run is retained as the candidate;
selection never cherry-picks the most profitable run. The most recent balanced
weekdays per run give equal reporting-day counts and weekday distributions.
Missing target rows count as zero delivery only on loaded brand-report dates;
report completeness is still unverified. Exact matched dates and source provenance
are displayed. Candidate ranking maximizes observed direct paid contribution/day
at the lowest observed SKU margin. This is an explicitly conservative scenario
criterion, not a causal optimizer or an estimate of company-wide incremental lift.

Company revenue, TaCoS and contribution are recomputed on exactly those matched
calendar dates. They remain context because other simultaneous changes are included;
if company contribution moves against the direct-paid comparison the conflict is
flagged. Product-mix ranges are not confidence intervals. Where no tested setting
covered costs, the UI says so instead of recommending the least-loss-making setting
as profitable; an existing loss assessment may suggest a human-reviewed pause or
restructure test.

The output is a concrete historical base-bid candidate plus the last-recorded
amount/date. It never populates verified current-bid or executable candidate fields
and does not bypass existing scenario/approval safeguards. A newly recorded change
whose attribution is still pending is kept pending rather than immediately reversed
using older comparisons. The next review accounts for that change's maturity date.
No CPC-to-bid ratio or fixed percentage-cut rule is used. No Amazon setting is changed.
