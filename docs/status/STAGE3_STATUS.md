# Stage 3 PPC Mart and Profit-Aware Advertising Status

## Implemented

- `ppc_fact_clean`: typed, deduplicated daily search-term fact with governed brand.
- Stable row identity derived from the confirmed business grain:

```text
date × campaign × ad group × target × match type × customer search term
```

- Reused the existing `campaign_brand_map`; Stage 3 does not recreate campaign mapping.
- Standard aggregate marts:
  - `ppc_campaign_metrics`
  - `ppc_ad_group_metrics`
  - `ppc_target_metrics`
  - `ppc_search_term_metrics`
- Metrics at brand and combined scopes: spend, impressions, clicks, sales, orders, CTR, CPC, CVR, ACOS, ROAS, and TACOS.
- `contribution_margin_benchmark`: actual break-even ACOS from complete Stage 2 profit lines.
- `ppc_negative_keyword_candidates`: 30-day, margin-aware advisory list with near-duplicate detection.
- `ppc_profit_after_ads`: date-aligned brand/account profit after ads and campaign-level estimated ad contribution.
- New **Advertising** dashboard tab.
- Idempotent migration and materializer.
- Automated tests for identity, duplicate selection, mapping enforcement, and margin-based waste thresholds.

## Deduplication findings

The earlier claim that `ppc_uid` was duplicated more than 22,000 times was caused by null handling:

- 22,398 rows have a blank `ppc_uid`.
- The remaining 1,974 nonblank `ppc_uid` values are all unique.
- The blank values belong to the legacy `access` source.
- The 1,974 populated IDs belong to `ppc.xlsx`.

At the confirmed business grain:

- Raw rows: 24,372.
- Clean rows: 24,179.
- Removed repeated rows: 193.
- Repeated-grain groups: 193, all from the legacy Access data and the same import.
- 182 groups have identical business metrics but different source row IDs.
- 11 groups contain same-day cumulative variants, usually changed impressions or attributed sales/orders.

### Deterministic selection rule

For every business-grain group:

1. Prefer the most complete cumulative result in this order:
   - orders;
   - attributed sales;
   - units;
   - clicks;
   - spend;
   - impressions.
2. Use the latest import timestamp as the next tie-breaker.
3. Use the greatest numeric source `ID`, then `ID1`, as stable lineage tie-breakers.
4. Record `dedup_group_size`, `dedup_rule`, selected source IDs, source file, import timestamp, and original UID.

This avoids “first row wins” behavior and preserves why each row survived.

Deduplication reduced:

| Brand | Raw rows | Clean rows | Raw spend | Clean spend | Raw ad sales | Clean ad sales |
|---|---:|---:|---:|---:|---:|---:|
| Has10 | 19,052 | 18,922 | $20,927.77 | $20,721.57 | $40,698.82 | $40,511.88 |
| Litet | 5,320 | 5,257 | $14,105.97 | $13,970.82 | $22,076.43 | $21,975.47 |
| Total | 24,372 | 24,179 | $35,033.74 | $34,692.39 | $62,775.25 | $62,487.35 |

## Aggregate mart coverage

| Table | Rows |
|---|---:|
| `ppc_fact_clean` | 24,179 |
| `ppc_campaign_metrics` | 62 |
| `ppc_ad_group_metrics` | 78 |
| `ppc_target_metrics` | 1,932 |
| `ppc_search_term_metrics` | 20,492 |
| `contribution_margin_benchmark` | 4 |
| `ppc_negative_keyword_candidates` | 40 |
| `ppc_profit_after_ads` | 10 |

Aggregate tables include brand-specific and `All` scopes. Ratio metrics are recalculated from summed numerators and denominators; brand ratios are never averaged.

## Break-even ACOS

The previous universal 25% target is no longer used by Stage 3 waste analysis.

| Brand/family | Complete profit lines | Break-even ACOS | Average covered order revenue |
|---|---:|---:|---:|
| Litet / Socks | 652 | 21.62% | $30.95 |
| Has10 / Cleat Covers | 60 | 22.02% | $17.25 |

Benchmarks use only sale lines with available COGS and matched fees. Litet campaigns use the Socks benchmark. Has10 campaigns use a family benchmark when campaign/ad-group/target text reliably identifies socks or cleat covers; otherwise they use the Has10 brand benchmark. Every candidate records which margin level was used.

The first-order spend allowance is:

```text
break-even ACOS × average covered order revenue
```

This currently produces approximately:

- Litet: $6.69.
- Has10: $3.80.

## Negative-keyword candidates

The current 30-day window is `2026-06-24` through `2026-07-23`.

| Brand | Recommendation | Candidates | Candidate spend |
|---|---|---:|---:|
| Has10 | `negative_exact` | 9 | $64.32 |
| Litet | `negative_exact` | 18 | $239.56 |
| Litet | `negative_exact_review` | 4 | $114.26 |
| Litet | `negative_phrase_review` | 9 | $23.55 |
| Total |  | 40 | $441.69 |

Rules include:

- spend with no orders above the brand/family first-order allowance;
- zero-order low conversion after sufficient clicks;
- ACOS above break-even with no more than one order and spend above twice the allowance;
- normalized near-duplicate clusters whose combined spend exceeds the allowance with no orders.

Terms with meaningful conversion volume are not automatically proposed as negatives merely because their ACOS is high. All recommendations remain advisory; no Amazon Ads API action is taken.

## Profit-aware advertising

Because PPC has no advertised SKU/ASIN:

- SKU profitability remains before ads.
- Brand/account profit after ads subtracts exact brand/account spend from covered Stage 2 profit.
- Campaign rows report **estimated ad contribution after spend**:

```text
attributed ad sales × applicable contribution margin − campaign spend
```

Campaign rows do not claim SKU profit or reuse total brand profit.

The profit and spend window is aligned to dates where Stage 2 has covered profit: `2026-05-01` through `2026-07-23`.

| Scope | Covered profit before ads | Ad spend | Covered profit after ads | Revenue coverage |
|---|---:|---:|---:|---:|
| Has10 | $171.28 | $284.95 | -$113.67 | 95.11% |
| Litet | $4,141.87 | $5,317.13 | -$1,175.26 | 98.72% |
| All | $4,313.15 | $5,602.08 | -$1,288.93 | 98.56% |

“Covered” is important: profit includes only rows with valid as-of COGS and matched fees. Coverage is displayed in the Advertising view.

## Files and operation

- Migration: `migrations/003_stage3_ppc.sql`
- Mart logic: `stage3_ppc.py`
- Materializer: `materialize_stage3.py`
- Tests: `tests/test_stage3_ppc.py`

Refresh Stage 3 after PPC, COGS, fee, or profitability data changes:

```bash
./venv/bin/python materialize_stage3.py
```

## Remaining limitations

- There is still no advertised SKU/ASIN, so no SKU-level PPC allocation.
- Product-family margin selection can use only reliable campaign/ad-group/target text; otherwise it falls back to brand margin.
- Break-even margins currently depend on placeholder COGS and limited covered history.
- Search-term candidates should be reviewed by the owner before applying negatives.
- Bid and budget changes remain advisory-only; there is no Amazon Ads API integration.
