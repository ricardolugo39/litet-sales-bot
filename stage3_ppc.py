"""Stage 3 clean PPC mart, waste detection, and profit-aware advertising."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

import pandas as pd


PPC_GRAIN = [
    "report_date", "campaign_name", "ad_group_name",
    "target", "match_type", "search_term",
]


def apply_stage3_schema(conn: sqlite3.Connection) -> None:
    migration = Path(__file__).with_name("migrations") / "003_stage3_ppc.sql"
    conn.executescript(migration.read_text())


def _text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce",
    ).fillna(0.0)


def _hash_values(*values) -> str:
    payload = "\x1f".join("" if pd.isna(value) else str(value) for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_clean_ppc_fact(
    raw_ppc: pd.DataFrame,
    campaign_brand_map: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Normalize and deterministically collapse repeated business-grain snapshots."""
    raw = raw_ppc.copy()
    rename = {
        "Date": "report_date_raw",
        "Campaign Name": "campaign_name",
        "Ad Group Name": "ad_group_name",
        "Targeting": "target",
        "Match Type": "match_type",
        "Customer Search Term": "search_term",
        "Impressions": "impressions",
        "Clicks": "clicks",
        "Spend": "spend",
        "7 Day Total Sales": "ad_sales",
        "7 Day Total Orders (#)": "ad_orders",
        "7 Day Total Units (#)": "ad_units",
        "7 Day Advertised SKU Units (#)": "advertised_sku_units",
        "7 Day Other SKU Units (#)": "other_sku_units",
        "7 Day Advertised SKU Sales": "advertised_sku_sales",
        "7 Day Other SKU Sales": "other_sku_sales",
    }
    raw = raw.rename(columns=rename)
    raw["report_date"] = pd.to_datetime(
        raw["report_date_raw"], errors="coerce", format="mixed"
    ).dt.normalize()
    text_cols = ["campaign_name", "ad_group_name", "target", "match_type", "search_term"]
    for col in text_cols:
        raw[col] = _text(raw[col])
    numeric_cols = [
        "impressions", "clicks", "spend", "ad_sales", "ad_orders", "ad_units",
        "advertised_sku_units", "other_sku_units",
        "advertised_sku_sales", "other_sku_sales",
    ]
    for col in numeric_cols:
        raw[col] = _number(raw[col])
    raw["imported_ts"] = pd.to_datetime(raw.get("imported_at"), errors="coerce", utc=True)
    raw["_source_id_rank"] = pd.to_numeric(raw.get("ID"), errors="coerce").fillna(-1)
    raw["_source_id1_rank"] = pd.to_numeric(raw.get("ID1"), errors="coerce").fillna(-1)

    metric_cols = numeric_cols
    group_sizes = raw.groupby(PPC_GRAIN, dropna=False)["campaign_name"].transform("size")
    metric_variants = raw.groupby(PPC_GRAIN, dropna=False)[metric_cols].transform("nunique").max(axis=1)
    raw["dedup_group_size"] = group_sizes
    raw["dedup_rule"] = "unique_grain"
    raw.loc[group_sizes.gt(1) & metric_variants.le(1), "dedup_rule"] = "exact_business_duplicate_collapsed"
    raw.loc[group_sizes.gt(1) & metric_variants.gt(1), "dedup_rule"] = "most_complete_cumulative_snapshot"

    # Search-term reports can be captured repeatedly during a day. Select the
    # most complete cumulative snapshot, then latest import/source ID as stable lineage.
    rank_cols = [
        "ad_orders", "ad_sales", "ad_units", "clicks", "spend", "impressions",
        "imported_ts", "_source_id_rank", "_source_id1_rank",
    ]
    raw = raw.sort_values(PPC_GRAIN + rank_cols, ascending=[True] * len(PPC_GRAIN) + [False] * len(rank_cols))
    clean = raw.drop_duplicates(PPC_GRAIN, keep="first").copy()

    mapping = campaign_brand_map[["campaign_name", "brand"]].drop_duplicates()
    clean = clean.merge(mapping, on="campaign_name", how="left", validate="many_to_one")
    if clean["brand"].isna().any():
        missing = sorted(clean.loc[clean["brand"].isna(), "campaign_name"].unique())
        raise ValueError(f"Campaigns missing from campaign_brand_map: {missing}")

    clean["ctr"] = clean["clicks"] / clean["impressions"].where(clean["impressions"].ne(0))
    clean["cpc"] = clean["spend"] / clean["clicks"].where(clean["clicks"].ne(0))
    clean["cvr"] = clean["ad_orders"] / clean["clicks"].where(clean["clicks"].ne(0))
    clean["acos"] = clean["spend"] / clean["ad_sales"].where(clean["ad_sales"].ne(0))
    clean["roas"] = clean["ad_sales"] / clean["spend"].where(clean["spend"].ne(0))
    clean["ppc_fact_key"] = clean.apply(
        lambda row: _hash_values(*[row[col] for col in PPC_GRAIN]), axis=1
    )

    output = clean.rename(
        columns={
            "ID": "selected_source_id",
            "ID1": "selected_source_id1",
            "ppc_uid": "original_ppc_uid",
        }
    )[
        [
            "ppc_fact_key", *PPC_GRAIN, "brand", *numeric_cols,
            "ctr", "cpc", "cvr", "acos", "roas",
            "dedup_group_size", "dedup_rule", "selected_source_id",
            "selected_source_id1", "source_file", "imported_at", "original_ppc_uid",
        ]
    ]
    findings = {
        "raw_rows": len(raw),
        "clean_rows": len(output),
        "removed_rows": len(raw) - len(output),
        "blank_ppc_uid_rows": int(_text(raw_ppc["ppc_uid"]).eq("").sum()),
        "nonblank_ppc_uid_unique": int(_text(raw_ppc["ppc_uid"]).replace("", pd.NA).nunique()),
        "duplicate_grain_groups": int((output["dedup_group_size"] > 1).sum()),
        "exact_duplicate_groups": int(
            output["dedup_rule"].eq("exact_business_duplicate_collapsed").sum()
        ),
        "cumulative_snapshot_groups": int(
            output["dedup_rule"].eq("most_complete_cumulative_snapshot").sum()
        ),
    }
    return output.reset_index(drop=True), findings


def build_margin_benchmarks(
    profitability: pd.DataFrame,
    dim_product: pd.DataFrame,
) -> pd.DataFrame:
    profit = profitability.copy()
    profit = profit[
        profit["cogs_status"].eq("available")
        & profit["contribution_profit_before_ads"].notna()
    ].copy()
    profit = profit.merge(
        dim_product[["asin", "product_family"]].drop_duplicates("asin"),
        on="asin",
        how="left",
    )
    profit["product_family"] = profit["product_family"].fillna("All")
    rows = []
    for brand, brand_df in profit.groupby("brand"):
        for family, family_df in list(brand_df.groupby("product_family")) + [("All", brand_df)]:
            revenue = pd.to_numeric(family_df["item_price_revenue"], errors="coerce").sum()
            contribution = pd.to_numeric(
                family_df["contribution_profit_before_ads"], errors="coerce"
            ).sum()
            orders = family_df["order_id"].nunique()
            rows.append(
                {
                    "benchmark_key": _hash_values(brand, family),
                    "brand": brand,
                    "product_family": family,
                    "complete_sale_lines": len(family_df),
                    "complete_orders": orders,
                    "revenue": revenue,
                    "contribution_profit_before_ads": contribution,
                    "break_even_acos": contribution / revenue if revenue > 0 else None,
                    "average_order_revenue": revenue / orders if orders > 0 else None,
                    "coverage_note": "complete COGS and matched-fee sale lines only",
                }
            )
    return pd.DataFrame(rows)


def _recompute_metrics(grouped: pd.DataFrame) -> pd.DataFrame:
    grouped["ctr"] = grouped["clicks"] / grouped["impressions"].where(grouped["impressions"].ne(0))
    grouped["cpc"] = grouped["spend"] / grouped["clicks"].where(grouped["clicks"].ne(0))
    grouped["cvr"] = grouped["ad_orders"] / grouped["clicks"].where(grouped["clicks"].ne(0))
    grouped["acos"] = grouped["spend"] / grouped["ad_sales"].where(grouped["ad_sales"].ne(0))
    grouped["roas"] = grouped["ad_sales"] / grouped["spend"].where(grouped["spend"].ne(0))
    return grouped


def aggregate_ppc(
    fact: pd.DataFrame,
    dimensions: list[str],
    profitability: pd.DataFrame,
) -> pd.DataFrame:
    metrics = ["impressions", "clicks", "spend", "ad_sales", "ad_orders"]
    revenue = profitability.groupby("brand")["item_price_revenue"].sum().to_dict()
    total_revenue = profitability["item_price_revenue"].sum()
    outputs = []
    brand_grouped = fact.groupby(["brand", *dimensions], as_index=False).agg(
        {metric: "sum" for metric in metrics}
    )
    brand_grouped["scope"] = brand_grouped["brand"]
    brand_grouped["tacos"] = brand_grouped.apply(
        lambda row: row["spend"] / revenue.get(row["brand"], 0)
        if revenue.get(row["brand"], 0) else None,
        axis=1,
    )
    outputs.append(brand_grouped)

    all_grouped = fact.groupby(dimensions, as_index=False).agg({metric: "sum" for metric in metrics})
    all_grouped["brand"] = "All"
    all_grouped["scope"] = "All"
    all_grouped["tacos"] = all_grouped["spend"] / total_revenue if total_revenue else None
    outputs.append(all_grouped)
    out = pd.concat(outputs, ignore_index=True)
    out = _recompute_metrics(out)
    out["period_start"] = str(fact["report_date"].min().date())
    out["period_end"] = str(fact["report_date"].max().date())
    return out[
        [
            "scope", "brand", *dimensions, "period_start", "period_end",
            *metrics, "ctr", "cpc", "cvr", "acos", "roas", "tacos",
        ]
    ]


def _normalized_term(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", str(value).lower())
    normalized = []
    for token in tokens:
        if len(token) > 3 and token.endswith("s"):
            token = token[:-1]
        normalized.append(token)
    return " ".join(sorted(normalized))


def _infer_family(row) -> str:
    if row.brand == "Litet":
        return "Socks"
    text = f"{row.campaign_name} {row.ad_group_name} {row.target}".lower()
    if "sock" in text:
        return "Socks"
    if "cleat" in text or "spat" in text:
        return "Cleat Covers"
    return "All"


def build_negative_keyword_candidates(
    fact: pd.DataFrame,
    benchmarks: pd.DataFrame,
    lookback_days: int = 30,
) -> pd.DataFrame:
    end = fact["report_date"].max()
    start = end - pd.Timedelta(days=lookback_days - 1)
    recent = fact[fact["report_date"].between(start, end)].copy()
    dims = ["brand", "campaign_name", "ad_group_name", "target", "match_type", "search_term"]
    grouped = recent.groupby(dims, as_index=False).agg(
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        spend=("spend", "sum"),
        ad_sales=("ad_sales", "sum"),
        ad_orders=("ad_orders", "sum"),
    )
    grouped = _recompute_metrics(grouped)
    grouped["normalized_term"] = grouped["search_term"].map(_normalized_term)
    cluster = grouped.groupby(["brand", "normalized_term"]).agg(
        near_duplicate_count=("search_term", "nunique"),
        cluster_spend=("spend", "sum"),
        cluster_orders=("ad_orders", "sum"),
    ).reset_index()
    grouped = grouped.merge(cluster, on=["brand", "normalized_term"], how="left")

    benchmark_lookup = benchmarks.set_index(["brand", "product_family"]).to_dict("index")
    brand_cvr = recent.groupby("brand").apply(
        lambda x: x["ad_orders"].sum() / x["clicks"].sum() if x["clicks"].sum() else 0,
        include_groups=False,
    ).to_dict()
    selected = []
    for row in grouped.itertuples(index=False):
        family = _infer_family(row)
        bench = benchmark_lookup.get((row.brand, family))
        margin_level = f"brand_product_family:{family}"
        if not bench or not bench.get("break_even_acos") or bench["break_even_acos"] <= 0:
            bench = benchmark_lookup.get((row.brand, "All"), {})
            margin_level = "brand_fallback"
        break_even = float(bench.get("break_even_acos") or 0)
        avg_order_revenue = float(bench.get("average_order_revenue") or 0)
        allowance = break_even * avg_order_revenue
        reasons = []
        recommendation = None
        if row.spend > 0 and row.ad_orders == 0 and allowance > 0 and row.spend >= allowance:
            reasons.append("spend with no orders exceeds break-even first-order allowance")
            recommendation = "negative_exact"
        if (
            pd.notna(row.acos)
            and break_even > 0
            and row.acos > break_even
            and row.ad_orders <= 1
            and allowance > 0
            and row.spend >= allowance * 2
        ):
            reasons.append("ACOS exceeds contribution-margin break-even ACOS")
            recommendation = recommendation or "negative_exact_review"
        low_cvr_threshold = max(float(brand_cvr.get(row.brand, 0)) * 0.5, 0.02)
        if row.clicks >= 10 and row.ad_orders == 0 and row.cvr < low_cvr_threshold:
            reasons.append("conversion rate is below half the brand baseline")
            recommendation = recommendation or "negative_exact"
        if (
            row.near_duplicate_count > 1
            and row.cluster_orders == 0
            and allowance > 0
            and row.cluster_spend >= allowance
        ):
            reasons.append("near-duplicate term cluster collectively exceeds allowance with no orders")
            recommendation = recommendation or "negative_phrase_review"
        if not recommendation:
            continue
        selected.append(
            {
                "candidate_key": _hash_values(
                    start.date(), end.date(), row.brand, row.campaign_name,
                    row.ad_group_name, row.target, row.match_type, row.search_term,
                ),
                "period_start": str(start.date()),
                "period_end": str(end.date()),
                "brand": row.brand,
                "campaign_name": row.campaign_name,
                "ad_group_name": row.ad_group_name,
                "target": row.target,
                "match_type": row.match_type,
                "search_term": row.search_term,
                "normalized_term": row.normalized_term,
                "near_duplicate_count": int(row.near_duplicate_count),
                "impressions": row.impressions,
                "clicks": row.clicks,
                "spend": row.spend,
                "ad_sales": row.ad_sales,
                "ad_orders": row.ad_orders,
                "cvr": row.cvr,
                "acos": row.acos,
                "break_even_acos": break_even or None,
                "break_even_spend_allowance": allowance or None,
                "margin_level": margin_level,
                "recommendation": recommendation,
                "reason": "; ".join(reasons),
            }
        )
    return pd.DataFrame(selected)


def build_profit_after_ads(
    fact: pd.DataFrame,
    profitability: pd.DataFrame,
    benchmarks: pd.DataFrame,
) -> pd.DataFrame:
    profit = profitability.copy()
    profit["sale_date_ts"] = pd.to_datetime(profit["sale_date"], errors="coerce", utc=True).dt.tz_localize(None)
    complete = profit[profit["contribution_profit_before_ads"].notna()]
    bench = benchmarks[benchmarks["product_family"].eq("All")].set_index("brand")
    rows = []
    for brand in sorted(fact["brand"].unique()):
        brand_profit = profit[profit["brand"].eq(brand)]
        brand_complete = complete[complete["brand"].eq(brand)]
        if brand_complete.empty:
            continue
        start_ts = brand_complete["sale_date_ts"].min()
        end_ts = min(brand_complete["sale_date_ts"].max(), fact["report_date"].max())
        brand_fact = fact[
            fact["brand"].eq(brand)
            & fact["report_date"].between(start_ts, end_ts)
        ]
        brand_profit = brand_profit[brand_profit["sale_date_ts"].between(start_ts, end_ts)]
        brand_complete = brand_complete[
            brand_complete["sale_date_ts"].between(start_ts, end_ts)
        ]
        period_start = str(start_ts.date())
        period_end = str(end_ts.date())
        spend = brand_fact["spend"].sum()
        pre_ad = brand_complete["contribution_profit_before_ads"].sum()
        covered_revenue = brand_complete["item_price_revenue"].sum()
        total_revenue = brand_profit["item_price_revenue"].sum()
        margin = float(bench.at[brand, "break_even_acos"]) if brand in bench.index else None
        rows.append(
            {
                "row_key": _hash_values("brand", brand),
                "scope_level": "brand",
                "brand": brand,
                "campaign_name": None,
                "period_start": period_start,
                "period_end": period_end,
                "profit_before_ads": pre_ad,
                "profit_coverage_revenue": covered_revenue,
                "total_item_price_revenue": total_revenue,
                "profit_coverage_pct": covered_revenue / total_revenue if total_revenue else 0,
                "ad_sales": brand_fact["ad_sales"].sum(),
                "ad_spend": spend,
                "break_even_acos": margin,
                "estimated_ad_contribution_after_spend": (
                    brand_fact["ad_sales"].sum() * margin - spend if margin is not None else None
                ),
                "profit_after_ads": pre_ad - spend,
                "calculation_status": "partial_profit_coverage; exact_brand_spend",
            }
        )
        for campaign, campaign_df in brand_fact.groupby("campaign_name"):
            ad_sales = campaign_df["ad_sales"].sum()
            campaign_spend = campaign_df["spend"].sum()
            rows.append(
                {
                    "row_key": _hash_values("campaign", brand, campaign),
                    "scope_level": "campaign",
                    "brand": brand,
                    "campaign_name": campaign,
                    "period_start": period_start,
                    "period_end": period_end,
                    "profit_before_ads": None,
                    "profit_coverage_revenue": covered_revenue,
                    "total_item_price_revenue": total_revenue,
                    "profit_coverage_pct": covered_revenue / total_revenue if total_revenue else 0,
                    "ad_sales": ad_sales,
                    "ad_spend": campaign_spend,
                    "break_even_acos": margin,
                    "estimated_ad_contribution_after_spend": (
                        ad_sales * margin - campaign_spend if margin is not None else None
                    ),
                    "profit_after_ads": None,
                    "calculation_status": "estimated_campaign_ad_contribution; no_sku_attribution",
                }
            )
    account_start = complete["sale_date_ts"].min()
    account_end = min(complete["sale_date_ts"].max(), fact["report_date"].max())
    account_fact = fact[fact["report_date"].between(account_start, account_end)]
    account_profit = profit[profit["sale_date_ts"].between(account_start, account_end)]
    account_complete = complete[complete["sale_date_ts"].between(account_start, account_end)]
    all_profit = account_complete["contribution_profit_before_ads"].sum()
    all_spend = account_fact["spend"].sum()
    all_covered_revenue = account_complete["item_price_revenue"].sum()
    all_revenue = account_profit["item_price_revenue"].sum()
    rows.append(
        {
            "row_key": _hash_values("account", "All"),
            "scope_level": "account",
            "brand": "All",
            "campaign_name": None,
            "period_start": str(account_start.date()),
            "period_end": str(account_end.date()),
            "profit_before_ads": all_profit,
            "profit_coverage_revenue": all_covered_revenue,
            "total_item_price_revenue": all_revenue,
            "profit_coverage_pct": all_covered_revenue / all_revenue if all_revenue else 0,
            "ad_sales": account_fact["ad_sales"].sum(),
            "ad_spend": all_spend,
            "break_even_acos": all_profit / all_covered_revenue if all_covered_revenue else None,
            "estimated_ad_contribution_after_spend": None,
            "profit_after_ads": all_profit - all_spend,
            "calculation_status": "partial_profit_coverage; exact_account_spend",
        }
    )
    return pd.DataFrame(rows)


def build_stage3(
    raw_ppc: pd.DataFrame,
    campaign_brand_map: pd.DataFrame,
    profitability: pd.DataFrame,
    dim_product: pd.DataFrame,
) -> dict:
    fact, findings = build_clean_ppc_fact(raw_ppc, campaign_brand_map)
    benchmarks = build_margin_benchmarks(profitability, dim_product)
    outputs = {
        "ppc_fact_clean": fact,
        "ppc_campaign_metrics": aggregate_ppc(fact, ["campaign_name"], profitability),
        "ppc_ad_group_metrics": aggregate_ppc(
            fact, ["campaign_name", "ad_group_name"], profitability
        ),
        "ppc_target_metrics": aggregate_ppc(
            fact, ["campaign_name", "ad_group_name", "target", "match_type"], profitability
        ),
        "ppc_search_term_metrics": aggregate_ppc(
            fact,
            ["campaign_name", "ad_group_name", "target", "match_type", "search_term"],
            profitability,
        ),
        "contribution_margin_benchmark": benchmarks,
        "ppc_negative_keyword_candidates": build_negative_keyword_candidates(fact, benchmarks),
        "ppc_profit_after_ads": build_profit_after_ads(fact, profitability, benchmarks),
        "findings": findings,
    }
    return outputs


def _sqlite_ready(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].astype(str).replace("NaT", None)
    return out


def materialize_stage3(conn: sqlite3.Connection, outputs: dict) -> None:
    apply_stage3_schema(conn)
    tables = [
        "ppc_fact_clean", "ppc_campaign_metrics", "ppc_ad_group_metrics",
        "ppc_target_metrics", "ppc_search_term_metrics",
        "contribution_margin_benchmark", "ppc_negative_keyword_candidates",
        "ppc_profit_after_ads",
    ]
    with conn:
        for table in tables:
            conn.execute(f'DELETE FROM "{table}"')
        for table in tables:
            _sqlite_ready(outputs[table]).to_sql(table, conn, if_exists="append", index=False)
