import pandas as pd


def _to_datetime(series):
    return (
        pd.to_datetime(series, errors="coerce", utc=True)
        .dt.tz_localize(None)
    )


def _filter_period(df, period):
    d = df.copy()

    if "purchase_date" not in d.columns:
        return d

    d["purchase_date"] = _to_datetime(d["purchase_date"])

    max_date = d["purchase_date"].max()

    if pd.isna(max_date):
        return d

    if period == "LAST_7_DAYS":
        start_date = max_date - pd.Timedelta(days=7)
    elif period == "LAST_30_DAYS":
        start_date = max_date - pd.Timedelta(days=30)
    elif period == "MTD":
        start_date = pd.Timestamp(max_date.year, max_date.month, 1)
    elif period == "YTD":
        start_date = pd.Timestamp(max_date.year, 1, 1)
    else:
        start_date = max_date - pd.Timedelta(days=30)

    return d[d["purchase_date"] >= start_date].copy()


def _money_columns(df):
    d = df.copy()

    for col in ["revenue", "aov", "revenue_per_day"]:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)
            d[col] = d[col].apply(lambda x: f"${x:,.2f}")

    for col in ["pairs_sold", "orders"]:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)
            d[col] = d[col].apply(lambda x: f"{x:,.0f}")

    for col in ["revenue_share"]:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)
            d[col] = d[col].apply(lambda x: f"{x:,.1f}%")

    return d


def _aggregate(df, group_col):
    if group_col not in df.columns:
        return pd.DataFrame()

    d = df.copy()

    d["revenue"] = pd.to_numeric(d["revenue"], errors="coerce").fillna(0)
    d["pairs_sold"] = pd.to_numeric(d.get("pairs_sold", 0), errors="coerce").fillna(0)

    order_col = "amazon-order-id" if "amazon-order-id" in d.columns else None

    if order_col:
        out = (
            d.groupby(group_col, as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                orders=(order_col, "nunique"),
                pairs_sold=("pairs_sold", "sum"),
            )
        )
    else:
        out = (
            d.groupby(group_col, as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                pairs_sold=("pairs_sold", "sum"),
            )
        )
        out["orders"] = 0

    total_revenue = out["revenue"].sum()

    out["aov"] = out.apply(
        lambda row: row["revenue"] / row["orders"] if row["orders"] > 0 else 0,
        axis=1,
    )

    out["revenue_share"] = out["revenue"] / total_revenue * 100 if total_revenue > 0 else 0

    out = out.sort_values("revenue", ascending=False)

    return _money_columns(out)


def build_sales_analysis(sales_df, period="MTD"):
    df = _filter_period(sales_df, period)

    if df.empty:
        return {
            "sales_by_asin": pd.DataFrame(),
            "sales_by_type": pd.DataFrame(),
            "sales_by_size": pd.DataFrame(),
            "sales_by_color": pd.DataFrame(),
            "sales_by_state": pd.DataFrame(),
            "velocity_df": pd.DataFrame(),
            "heatmap_df": pd.DataFrame(),
        }

    # Sales by product
    product_group_cols = []

    if "product_name" in df.columns:
        product_group_cols.append("product_name")

    if "asin" in df.columns:
        product_group_cols.append("asin")

    if product_group_cols:
        temp = df.copy()
        temp["revenue"] = pd.to_numeric(temp["revenue"], errors="coerce").fillna(0)
        temp["pairs_sold"] = pd.to_numeric(temp.get("pairs_sold", 0), errors="coerce").fillna(0)

        order_col = "amazon-order-id" if "amazon-order-id" in temp.columns else None

        if order_col:
            sales_by_asin = (
                temp.groupby(product_group_cols, as_index=False)
                .agg(
                    revenue=("revenue", "sum"),
                    orders=(order_col, "nunique"),
                    pairs_sold=("pairs_sold", "sum"),
                )
            )
        else:
            sales_by_asin = (
                temp.groupby(product_group_cols, as_index=False)
                .agg(
                    revenue=("revenue", "sum"),
                    pairs_sold=("pairs_sold", "sum"),
                )
            )
            sales_by_asin["orders"] = 0

        total_revenue = sales_by_asin["revenue"].sum()

        sales_by_asin["aov"] = sales_by_asin.apply(
            lambda row: row["revenue"] / row["orders"] if row["orders"] > 0 else 0,
            axis=1,
        )

        sales_by_asin["revenue_share"] = (
            sales_by_asin["revenue"] / total_revenue * 100 if total_revenue > 0 else 0
        )

        sales_by_asin = sales_by_asin.sort_values("revenue", ascending=False).head(20)
        sales_by_asin = _money_columns(sales_by_asin)
    else:
        sales_by_asin = pd.DataFrame()

    # Grouped sales
    sales_by_type = _aggregate(df, "type") if "type" in df.columns else pd.DataFrame()
    sales_by_size = _aggregate(df, "size") if "size" in df.columns else pd.DataFrame()
    sales_by_color = _aggregate(df, "color") if "color" in df.columns else pd.DataFrame()

    # State
    state_col = None

    for col in ["ship_state", "ship-state", "state", "buyer_state"]:
        if col in df.columns:
            state_col = col
            break

    sales_by_state = _aggregate(df, state_col) if state_col else pd.DataFrame()

    # Sales velocity
    velocity_df = pd.DataFrame()

    if "purchase_date" in df.columns and "product_name" in df.columns:
        temp = df.copy()
        temp["purchase_date"] = _to_datetime(temp["purchase_date"])
        temp["revenue"] = pd.to_numeric(temp["revenue"], errors="coerce").fillna(0)
        temp["pairs_sold"] = pd.to_numeric(temp.get("pairs_sold", 0), errors="coerce").fillna(0)

        days_in_period = max((temp["purchase_date"].max() - temp["purchase_date"].min()).days + 1, 1)

        velocity_df = (
            temp.groupby("product_name", as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                pairs_sold=("pairs_sold", "sum"),
            )
            .sort_values("revenue", ascending=False)
        )

        velocity_df["pairs_per_day"] = velocity_df["pairs_sold"] / days_in_period
        velocity_df["revenue_per_day"] = velocity_df["revenue"] / days_in_period

        velocity_df["pairs_per_day"] = velocity_df["pairs_per_day"].apply(lambda x: f"{x:,.1f}")
        velocity_df = _money_columns(velocity_df.head(20))

    # Daily heatmap base table
    heatmap_df = pd.DataFrame()

    if "purchase_date" in df.columns:
        temp = df.copy()
        temp["purchase_date"] = _to_datetime(temp["purchase_date"])
        temp["weekday"] = temp["purchase_date"].dt.day_name()
        temp["revenue"] = pd.to_numeric(temp["revenue"], errors="coerce").fillna(0)

        heatmap_df = (
            temp.groupby("weekday", as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                orders=("amazon-order-id", "nunique")
                if "amazon-order-id" in temp.columns
                else ("revenue", "count"),
            )
        )

        weekday_order = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        heatmap_df["weekday"] = pd.Categorical(
            heatmap_df["weekday"],
            categories=weekday_order,
            ordered=True,
        )

        heatmap_df = heatmap_df.sort_values("weekday")
        heatmap_df = _money_columns(heatmap_df)
    
    last_4_weeks_sku_table = build_last_4_weeks_sku_table(sales_df)

    return {
        "sales_by_asin": sales_by_asin,
        "sales_by_type": sales_by_type,
        "sales_by_size": sales_by_size,
        "sales_by_color": sales_by_color,
        "sales_by_state": sales_by_state,
        "velocity_df": velocity_df,
        "heatmap_df": heatmap_df,
        "last_4_weeks_sku_table": last_4_weeks_sku_table,
    }

def build_last_4_weeks_sku_table(sales_df):
    df = sales_df.copy()

    if "purchase_date" not in df.columns or "product_name" not in df.columns:
        return pd.DataFrame()

    df["purchase_date"] = (
        pd.to_datetime(df["purchase_date"], errors="coerce", utc=True)
        .dt.tz_localize(None)
    )

    df = df.dropna(subset=["purchase_date"])

    if df.empty:
        return pd.DataFrame()

    max_date = df["purchase_date"].max()
    start_date = max_date - pd.Timedelta(weeks=3)

    df = df[df["purchase_date"] >= start_date].copy()

    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0)
    df["units_sold"] = pd.to_numeric(df.get("quantity", 0), errors="coerce").fillna(0)

    df["week_start"] = df["purchase_date"].dt.to_period("W").apply(lambda r: r.start_time)
    df["week_label"] = df["week_start"].dt.strftime("%b %d")

    weekly = (
        df.groupby(["product_name", "week_label"], as_index=False)
        .agg(
            units_sold=("units_sold", "sum"),
            revenue=("revenue", "sum"),
        )
    )

    weekly["velocity"] = weekly["units_sold"] / 7
    weekly["avg_price"] = weekly["revenue"] / weekly["units_sold"].replace(0, pd.NA)
    weekly["avg_price"] = weekly["avg_price"].fillna(0)

    units_pivot = weekly.pivot(index="product_name", columns="week_label", values="units_sold")
    velocity_pivot = weekly.pivot(index="product_name", columns="week_label", values="velocity")
    price_pivot = weekly.pivot(index="product_name", columns="week_label", values="avg_price")

    result = pd.DataFrame(index=units_pivot.index)

    for week in units_pivot.columns:
        result[f"{week} Units"] = units_pivot[week].fillna(0)
        result[f"{week} Velocity"] = velocity_pivot[week].fillna(0)
        result[f"{week} Avg Price"] = price_pivot[week].fillna(0)

    result = result.reset_index()

    latest_week = units_pivot.columns[-1]
    result = result.sort_values(f"{latest_week} Units", ascending=False)

    total_row = {"product_name": "TOTAL"}

    for week in units_pivot.columns:
        total_units = units_pivot[week].fillna(0).sum()
        total_revenue = weekly.loc[weekly["week_label"] == week, "revenue"].sum()

        total_row[f"{week} Units"] = total_units
        total_row[f"{week} Velocity"] = total_units / 7
        total_row[f"{week} Avg Price"] = total_revenue / total_units if total_units > 0 else 0

    result = pd.concat([result, pd.DataFrame([total_row])], ignore_index=True)

    for col in result.columns:
        if "Units" in col:
            result[col] = result[col].apply(lambda x: f"{float(x):,.0f}")
        elif "Velocity" in col:
            result[col] = result[col].apply(lambda x: f"{float(x):,.1f}/day")
        elif "Avg Price" in col:
            result[col] = result[col].apply(lambda x: f"${float(x):,.2f}")

    return result