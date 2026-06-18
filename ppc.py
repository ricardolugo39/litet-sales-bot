import pandas as pd

from helpers import clean_for_streamlit, to_numeric_sum
from filters import filter_df_by_period


def build_ppc_kpis(ppc_df, sales_df, period="MTD"):
    ppc, _, start_date, max_date = filter_df_by_period(
        ppc_df,
        period,
        ["date", "campaign_date", "report_date", "start_date", "end_date"],
    )

    sales, _, sales_start, sales_max = filter_df_by_period(
        sales_df,
        period,
        ["purchase_date", "purchase-date", "date"],
    )

    if max_date is None:
        max_date = sales_max or pd.Timestamp.today().normalize()

    if start_date is None:
        start_date = sales_start or pd.Timestamp.today().normalize()

    spend = to_numeric_sum(ppc, "spend")
    ad_sales = to_numeric_sum(ppc, "sales")
    ad_orders = to_numeric_sum(ppc, "orders")
    clicks = to_numeric_sum(ppc, "clicks")
    impressions = to_numeric_sum(ppc, "impressions")
    total_revenue = to_numeric_sum(sales, "revenue")

    return {
        "period_start": start_date.date(),
        "period_end": max_date.date(),
        "ad_spend": spend,
        "ad_sales": ad_sales,
        "ad_orders": ad_orders,
        "clicks": clicks,
        "impressions": impressions,
        "acos": spend / ad_sales if ad_sales > 0 else 0,
        "roas": ad_sales / spend if spend > 0 else 0,
        "tacos": spend / total_revenue if total_revenue > 0 else 0,
        "ctr": clicks / impressions if impressions > 0 else 0,
        "cvr": ad_orders / clicks if clicks > 0 else 0,
    }


def classify_keyword_actions(df):
    d = clean_for_streamlit(df)

    if d.empty:
        return d

    for col in ["acos", "cvr", "spend", "sales", "clicks", "orders", "cpc"]:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)

    def action(row):
        acos = row.get("acos", 0)
        cvr = row.get("cvr", 0)
        spend = row.get("spend", 0)
        sales = row.get("sales", 0)
        clicks = row.get("clicks", 0)

        if spend >= 15 and sales == 0 and clicks >= 10:
            return "Pause / Reduce"
        if acos >= 0.45 and spend >= 15:
            return "Lower Bid"
        if acos <= 0.25 and sales > 0 and cvr >= 0.12:
            return "Scale"
        if sales > 0:
            return "Monitor"
        return "Low Data"

    d["dashboard_action"] = d.apply(action, axis=1)

    return d