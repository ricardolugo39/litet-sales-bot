import pandas as pd
import streamlit as st

from data import load_orders, load_asins, load_ppc
from data_prep import prepare_sales_data, prepare_ppc_data
from sales_analysis import build_sales_analysis

from calculations import (
    get_sales_summary_period,
    get_top_keywords,
    get_product_mix,
    compare_periods,
    get_keyword_bid_recommendations,
)

from helpers import clean_for_streamlit
from ppc import build_ppc_kpis, classify_keyword_actions
from inventory import build_inventory_risk
from ai_analyst import build_ai_summary


try:
    from data import load_latest_inventory_snapshot as load_inventory
except Exception:
    load_inventory = None


@st.cache_data(show_spinner=False)
def load_all_data():
    orders_raw = load_orders()
    asins_raw = load_asins()
    ppc_raw = load_ppc()

    sales_df = prepare_sales_data(
        orders_raw,
        asins_raw,
    )

    ppc_df = prepare_ppc_data(
        ppc_raw,
        campaign_filter="LITET",
    )

    inventory_df = pd.DataFrame()

    if load_inventory is not None:
        try:
            inventory_df = load_inventory()
        except Exception:
            inventory_df = pd.DataFrame()

    return sales_df, ppc_df, inventory_df


def build_comparison_view(comparison):
    if not isinstance(comparison, dict):
        return clean_for_streamlit(comparison)

    current = comparison.get("current", {})
    prior = comparison.get("prior", {})

    rows = []

    for metric in ["revenue", "orders", "pairs_sold", "aov"]:
        current_value = current.get(metric, 0)
        prior_value = prior.get(metric, 0)

        if prior_value:
            change_pct = ((current_value / prior_value) - 1) * 100
        else:
            change_pct = None

        rows.append(
            {
                "Metric": metric.replace("_", " ").title(),
                "Current": current_value,
                "Prior": prior_value,
                "Change %": change_pct,
            }
        )

    df = pd.DataFrame(rows)

    def format_value(row, col):
        value = row[col]

        if row["Metric"] in ["Revenue", "Aov"]:
            return f"${float(value):,.2f}"

        return f"{float(value):,.0f}"

    df["Current"] = df.apply(
        lambda row: format_value(row, "Current"),
        axis=1,
    )

    df["Prior"] = df.apply(
        lambda row: format_value(row, "Prior"),
        axis=1,
    )

    df["Change %"] = df["Change %"].apply(
        lambda x: "" if pd.isna(x) else f"{x:,.1f}%"
    )

    return df


def _find_date_column(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col

    return None


def _find_numeric_column(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col

    return None


def build_revenue_tacos_trend(
    sales_df,
    ppc_df,
    lookback_weeks=12,
):
    sales = sales_df.copy()
    ppc = ppc_df.copy()

    sales_date_col = _find_date_column(
        sales,
        ["purchase_date", "purchase-date", "date"],
    )

    ppc_date_col = _find_date_column(
        ppc,
        ["date", "campaign_date", "report_date", "start_date", "end_date"],
    )

    revenue_col = _find_numeric_column(
        sales,
        ["revenue", "item_price", "sales"],
    )

    spend_col = _find_numeric_column(
        ppc,
        ["spend", "ad_spend", "cost"],
    )

    if (
        sales_date_col is None
        or revenue_col is None
        or ppc_date_col is None
        or spend_col is None
    ):
        return pd.DataFrame()

    # =====================================================
    # NORMALIZE DATES
    # =====================================================

    sales[sales_date_col] = (
        pd.to_datetime(
            sales[sales_date_col],
            errors="coerce",
            utc=True,
        )
        .dt.tz_localize(None)
    )

    ppc[ppc_date_col] = (
        pd.to_datetime(
            ppc[ppc_date_col],
            errors="coerce",
            utc=True,
        )
        .dt.tz_localize(None)
    )

    # =====================================================
    # CLEAN NUMERIC
    # =====================================================

    sales[revenue_col] = pd.to_numeric(
        sales[revenue_col],
        errors="coerce",
    ).fillna(0)

    ppc[spend_col] = pd.to_numeric(
        ppc[spend_col],
        errors="coerce",
    ).fillna(0)

    # =====================================================
    # DATE RANGE
    # =====================================================

    max_sales_date = sales[sales_date_col].max()
    max_ppc_date = ppc[ppc_date_col].max()

    max_date = max(max_sales_date, max_ppc_date)

    start_date = max_date - pd.Timedelta(weeks=lookback_weeks)

    sales = sales[sales[sales_date_col] >= start_date]
    ppc = ppc[ppc[ppc_date_col] >= start_date]

    # =====================================================
    # WEEK START
    # =====================================================

    sales["week"] = (
        sales[sales_date_col]
        .dt.to_period("W")
        .apply(lambda r: r.start_time)
    )

    ppc["week"] = (
        ppc[ppc_date_col]
        .dt.to_period("W")
        .apply(lambda r: r.start_time)
    )

    # =====================================================
    # REVENUE BY WEEK
    # =====================================================

    revenue_weekly = (
        sales.groupby("week", as_index=False)
        .agg(revenue=(revenue_col, "sum"))
    )

    # =====================================================
    # PPC BY WEEK
    # =====================================================

    ppc_weekly = (
        ppc.groupby("week", as_index=False)
        .agg(
            ad_spend=(spend_col, "sum"),
        )
    )

    # =====================================================
    # MERGE
    # =====================================================

    trend = revenue_weekly.merge(
        ppc_weekly,
        on="week",
        how="left",
    )

    trend["ad_spend"] = trend["ad_spend"].fillna(0)

    # =====================================================
    # TACOS
    # =====================================================

    trend["tacos"] = trend.apply(
        lambda row: (
            row["ad_spend"] / row["revenue"]
            if row["revenue"] > 0
            else 0
        ),
        axis=1,
    )

    trend["tacos_pct"] = trend["tacos"] * 100

    # =====================================================
    # FINAL FORMAT
    # =====================================================

    trend = trend.sort_values("week")

    trend["week_label"] = trend["week"].dt.strftime("%b %d")

    return trend[
        [
            "week",
            "week_label",
            "revenue",
            "ad_spend",
            "tacos",
            "tacos_pct",
        ]
    ]
def build_kpi_comparison(comparison_raw, marketing_summary):
    current = comparison_raw.get("current", {}) if isinstance(comparison_raw, dict) else {}
    prior = comparison_raw.get("prior", {}) if isinstance(comparison_raw, dict) else {}

    def change_pct(metric):
        current_value = current.get(metric, 0)
        prior_value = prior.get(metric, 0)

        if prior_value:
            return ((current_value / prior_value) - 1) * 100

        return None

    return {
        "current_dates": {
            "start": str(marketing_summary.get("period_start", "")),
            "end": str(marketing_summary.get("period_end", "")),
        },
        "prior_dates": {
            "start": "",
            "end": "",
        },
        "metrics": {
            "revenue": change_pct("revenue"),
            "orders": change_pct("orders"),
            "pairs_sold": change_pct("pairs_sold"),
            "aov": change_pct("aov"),
        },
    }

def build_dashboard_context(
    sales_df,
    ppc_df,
    inventory_df,
    period="MTD",
    selected_campaign="All Campaigns",
    selected_campaign_col=None,
):
    days = 7 if period == "LAST_7_DAYS" else 30

    ppc_filtered = ppc_df.copy()

    if (
        selected_campaign_col
        and selected_campaign
        and selected_campaign != "All Campaigns"
        and selected_campaign_col in ppc_filtered.columns
    ):
        ppc_filtered = ppc_filtered[
            ppc_filtered[selected_campaign_col] == selected_campaign
        ]

    sales_summary = get_sales_summary_period(
        sales_df,
        period=period,
    )

    marketing_summary = build_ppc_kpis(
        ppc_filtered,
        sales_df,
        period=period,
    )

    comparison_raw = compare_periods(
        sales_df,
        period=period,
        metric="revenue",
        group_by=None,
        top_n=10,
    )

    comparison_view = build_comparison_view(comparison_raw)

    kpi_comparison = build_kpi_comparison(
        comparison_raw,
        marketing_summary,
    )

    product_mix = get_product_mix(
        sales_df,
        days=days,
    )

    top_keywords = get_top_keywords(
        ppc_filtered,
        days=days,
        min_clicks=5,
        top_n=50,
    )

    keyword_actions = classify_keyword_actions(top_keywords)

    bid_recs = get_keyword_bid_recommendations(
        ppc_filtered,
        days=30,
        target_acos=0.25,
        min_clicks=10,
        min_spend=15.0,
        pause_clicks_threshold=20,
        strong_cvr_threshold=0.12,
        top_n=50,
    )

    inventory_risk = (
        build_inventory_risk(
            inventory_df,
            sales_df,
        )
        if inventory_df is not None and not inventory_df.empty
        else pd.DataFrame()
    )

    trend_view = build_revenue_tacos_trend(
        sales_df=sales_df,
        ppc_df=ppc_filtered,
        lookback_weeks=12,
    )

    sales_analysis = build_sales_analysis(
        sales_df=sales_df,
        period=period,
    )

    context = {
        "sales_df": sales_df,
        "ppc_df": ppc_df,
        "inventory_df": inventory_df,
        "period": period,
        "sales_summary": sales_summary,
        "marketing_summary": marketing_summary,
        "comparison_view": comparison_view,
        "product_mix": product_mix,
        "keyword_actions": keyword_actions,
        "bid_recs": bid_recs,
        "inventory_risk": inventory_risk,
        "trend_view": trend_view,
        "kpi_comparison": kpi_comparison,
        "sales_analysis": sales_analysis,
        "selected_campaign": selected_campaign,
    }

    ai_summary = build_ai_summary(context)

    context["ai_summary"] = ai_summary

  

    return context