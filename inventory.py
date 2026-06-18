import pandas as pd

from filters import get_date_col, filter_df_by_period


def build_inventory_risk(inventory_df, sales_df):
    if inventory_df is None or inventory_df.empty:
        return pd.DataFrame()

    inv = inventory_df.copy()
    sales = sales_df.copy()

    asin_col_inv = get_date_col(inv, ["asin"])
    asin_col_sales = "asin" if "asin" in sales.columns else None

    if asin_col_inv is None or asin_col_sales is None:
        return pd.DataFrame()

    units_col = None

    for col in [
        "Quantity Available",
        "quantity available",
        "available",
        "available_units",
        "current_total_units",
        "inventory",
        "units",
        "quantity",
    ]:
        if col in inv.columns:
            units_col = col
            break

    if units_col is None:
        return pd.DataFrame()

    sales_recent, _, _, _ = filter_df_by_period(
        sales,
        "LAST_30_DAYS",
        ["purchase_date", "purchase-date", "date"],
    )

    if "pairs_sold" in sales_recent.columns:
        demand_col = "pairs_sold"
    elif "quantity" in sales_recent.columns:
        demand_col = "quantity"
    else:
        return pd.DataFrame()

    demand = (
        sales_recent
        .groupby(asin_col_sales, as_index=False)
        .agg(units_30d=(demand_col, "sum"))
    )

    stock = (
        inv
        .groupby(asin_col_inv, as_index=False)
        .agg(current_units=(units_col, "sum"))
    )

    risk = stock.merge(
        demand,
        left_on=asin_col_inv,
        right_on=asin_col_sales,
        how="left",
    )

    risk["units_30d"] = pd.to_numeric(risk["units_30d"], errors="coerce").fillna(0)
    risk["current_units"] = pd.to_numeric(risk["current_units"], errors="coerce").fillna(0)
    risk["daily_demand"] = risk["units_30d"] / 30

    risk["days_of_inventory"] = risk.apply(
        lambda row: row["current_units"] / row["daily_demand"]
        if row["daily_demand"] > 0
        else None,
        axis=1,
    )

    def risk_level(days):
        if pd.isna(days):
            return "No recent demand"
        if days <= 14:
            return "Critical"
        if days <= 30:
            return "High"
        if days <= 60:
            return "Medium"
        return "Low"

    risk["inventory_risk"] = risk["days_of_inventory"].apply(risk_level)

    return risk.sort_values(
        ["inventory_risk", "days_of_inventory"],
        ascending=[True, True],
    )