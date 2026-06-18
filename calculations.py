import pandas as pd


def _normalize_date_col(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    data = df.copy()
    data = data.dropna(subset=[date_col]).copy()
    data[date_col] = pd.to_datetime(data[date_col]).dt.date
    return data


def _get_period_bounds(reference_date, period: str):
    period = period.upper()

    if period == "LAST_7_DAYS":
        start_date = reference_date - pd.Timedelta(days=6)
        end_date = reference_date
    elif period == "LAST_30_DAYS":
        start_date = reference_date - pd.Timedelta(days=29)
        end_date = reference_date
    elif period == "MTD":
        start_date = reference_date.replace(day=1)
        end_date = reference_date
    elif period == "YTD":
        start_date = reference_date.replace(month=1, day=1)
        end_date = reference_date
    else:
        raise ValueError(f"Unsupported period: {period}")

    return start_date, end_date


def _get_prior_period_bounds(reference_date, period: str):
    period = period.upper()

    if period == "LAST_7_DAYS":
        current_start = reference_date - pd.Timedelta(days=6)
        prior_end = current_start - pd.Timedelta(days=1)
        prior_start = prior_end - pd.Timedelta(days=6)

    elif period == "LAST_30_DAYS":
        current_start = reference_date - pd.Timedelta(days=29)
        prior_end = current_start - pd.Timedelta(days=1)
        prior_start = prior_end - pd.Timedelta(days=29)

    elif period == "MTD":
        current_start = reference_date.replace(day=1)
        prior_end = current_start - pd.Timedelta(days=1)
        prior_start = prior_end.replace(day=1)

        current_days_elapsed = (reference_date - current_start).days + 1
        max_days_prior = (prior_end - prior_start).days + 1
        aligned_days = min(current_days_elapsed, max_days_prior)
        prior_end = prior_start + pd.Timedelta(days=aligned_days - 1)

    elif period == "YTD":
        current_start = reference_date.replace(month=1, day=1)
        prior_start = reference_date.replace(year=reference_date.year - 1, month=1, day=1)

        current_days_elapsed = (reference_date - current_start).days
        prior_end = prior_start + pd.Timedelta(days=current_days_elapsed)

    else:
        raise ValueError(f"Unsupported period: {period}")

    return prior_start, prior_end


def _filter_period(
    df: pd.DataFrame,
    date_col: str = "date",
    period: str = "LAST_7_DAYS",
) -> tuple[pd.DataFrame, object, object]:
    data = _normalize_date_col(df, date_col=date_col)

    if data.empty:
        return data, None, None

    reference_date = data[date_col].max()
    start_date, end_date = _get_period_bounds(reference_date, period)

    filtered = data.loc[
        (data[date_col] >= start_date) &
        (data[date_col] <= end_date)
    ].copy()

    return filtered, start_date, end_date


def _filter_period_bounds(
    df: pd.DataFrame,
    start_date,
    end_date,
    date_col: str = "date",
) -> pd.DataFrame:
    data = _normalize_date_col(df, date_col=date_col)

    if data.empty or start_date is None or end_date is None:
        return data.iloc[0:0].copy()

    filtered = data.loc[
        (data[date_col] >= start_date) &
        (data[date_col] <= end_date)
    ].copy()

    return filtered


def _safe_pct_change(current_value, prior_value):
    if prior_value is None or prior_value == 0:
        return None
    return round(((current_value - prior_value) / prior_value) * 100, 2)


def _get_period_slices(df: pd.DataFrame, date_col: str, days: int):
    data = df.copy()
    data = data.dropna(subset=[date_col]).copy()

    if data.empty:
        return data, data, None, None, None

    data[date_col] = pd.to_datetime(data[date_col]).dt.date

    reference_date = data[date_col].max()
    current_start = reference_date - pd.Timedelta(days=days - 1)
    prior_end = current_start - pd.Timedelta(days=1)
    prior_start = prior_end - pd.Timedelta(days=days - 1)

    current_df = data.loc[
        (data[date_col] >= current_start) &
        (data[date_col] <= reference_date)
    ].copy()

    prior_df = data.loc[
        (data[date_col] >= prior_start) &
        (data[date_col] <= prior_end)
    ].copy()

    return current_df, prior_df, reference_date, current_start, prior_start


def get_sales_summary_period(sales_df: pd.DataFrame, period: str = "MTD") -> dict:
    df, start_date, end_date = _filter_period(sales_df, date_col="date", period=period)

    revenue = float(df["revenue"].sum()) if "revenue" in df.columns else 0.0
    units_sold_amazon = int(df["units_sold_amazon"].sum()) if "units_sold_amazon" in df.columns else 0
    pairs_sold = int(df["pairs_sold"].sum()) if "pairs_sold" in df.columns else 0
    orders = int(df["amazon-order-id"].nunique()) if "amazon-order-id" in df.columns else 0

    aov = revenue / orders if orders > 0 else 0.0
    avg_unit_price_amazon = revenue / units_sold_amazon if units_sold_amazon > 0 else 0.0
    avg_selling_price_per_pair = revenue / pairs_sold if pairs_sold > 0 else 0.0

    return {
        "period": period.upper(),
        "start_date": start_date,
        "end_date": end_date,
        "revenue": round(revenue, 2),
        "units_sold_amazon": units_sold_amazon,
        "pairs_sold": pairs_sold,
        "orders": orders,
        "aov": round(aov, 2),
        "avg_unit_price_amazon": round(avg_unit_price_amazon, 2),
        "avg_selling_price_per_pair": round(avg_selling_price_per_pair, 2),
    }


def get_sales_breakdown(
    sales_df: pd.DataFrame,
    period: str = "MTD",
    group_by: str = "color",
    metric: str = "revenue",
    top_n: int = 10
) -> pd.DataFrame:
    valid_group_bys = {"type", "color", "item_name", "asin", "size"}
    valid_metrics = {"revenue", "pairs_sold", "units_sold_amazon", "orders"}

    if group_by not in valid_group_bys:
        raise ValueError(f"Unsupported group_by: {group_by}")

    if metric not in valid_metrics:
        raise ValueError(f"Unsupported metric: {metric}")

    df, start_date, end_date = _filter_period(sales_df, date_col="date", period=period)

    grouped = (
        df.groupby(group_by, as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            pairs_sold=("pairs_sold", "sum"),
            units_sold_amazon=("units_sold_amazon", "sum"),
            orders=("amazon-order-id", "nunique"),
        )
    )

    total_metric = grouped[metric].sum()
    grouped[f"{metric}_pct"] = grouped[metric] / total_metric if total_metric > 0 else 0

    grouped = grouped.sort_values(metric, ascending=False).head(top_n).copy()
    grouped["period"] = period.upper()
    grouped["start_date"] = start_date
    grouped["end_date"] = end_date

    return grouped


def compare_periods(
    sales_df: pd.DataFrame,
    period: str = "MTD",
    metric: str = "revenue",
    group_by: str | None = None,
    top_n: int = 10,
) -> dict:
    valid_group_bys = {None, "type", "color", "item_name", "asin", "size"}
    valid_metrics = {"revenue", "pairs_sold", "units_sold_amazon", "orders"}

    if group_by not in valid_group_bys:
        raise ValueError(f"Unsupported group_by: {group_by}")

    if metric not in valid_metrics:
        raise ValueError(f"Unsupported metric: {metric}")

    data = _normalize_date_col(sales_df, date_col="date")
    if data.empty:
        return {
            "period": period.upper(),
            "metric": metric,
            "current_period": {"start": None, "end": None},
            "prior_period": {"start": None, "end": None},
            "current": {},
            "prior": {},
            "change_abs": {},
            "change_pct": {},
            "top_drivers": [],
        }

    reference_date = data["date"].max()
    current_start, current_end = _get_period_bounds(reference_date, period)
    prior_start, prior_end = _get_prior_period_bounds(reference_date, period)

    current_df = _filter_period_bounds(data, current_start, current_end, date_col="date")
    prior_df = _filter_period_bounds(data, prior_start, prior_end, date_col="date")

    def summarize(dataframe: pd.DataFrame) -> dict:
        revenue = float(dataframe["revenue"].sum()) if "revenue" in dataframe.columns else 0.0
        units_sold_amazon = int(dataframe["units_sold_amazon"].sum()) if "units_sold_amazon" in dataframe.columns else 0
        pairs_sold = int(dataframe["pairs_sold"].sum()) if "pairs_sold" in dataframe.columns else 0
        orders = int(dataframe["amazon-order-id"].nunique()) if "amazon-order-id" in dataframe.columns else 0

        aov = revenue / orders if orders > 0 else 0.0
        avg_unit_price_amazon = revenue / units_sold_amazon if units_sold_amazon > 0 else 0.0
        avg_selling_price_per_pair = revenue / pairs_sold if pairs_sold > 0 else 0.0

        return {
            "revenue": round(revenue, 2),
            "units_sold_amazon": units_sold_amazon,
            "pairs_sold": pairs_sold,
            "orders": orders,
            "aov": round(aov, 2),
            "avg_unit_price_amazon": round(avg_unit_price_amazon, 2),
            "avg_selling_price_per_pair": round(avg_selling_price_per_pair, 2),
        }

    current = summarize(current_df)
    prior = summarize(prior_df)

    change_abs = {
        "revenue": round(current["revenue"] - prior["revenue"], 2),
        "units_sold_amazon": current["units_sold_amazon"] - prior["units_sold_amazon"],
        "pairs_sold": current["pairs_sold"] - prior["pairs_sold"],
        "orders": current["orders"] - prior["orders"],
        "aov": round(current["aov"] - prior["aov"], 2),
        "avg_unit_price_amazon": round(current["avg_unit_price_amazon"] - prior["avg_unit_price_amazon"], 2),
        "avg_selling_price_per_pair": round(current["avg_selling_price_per_pair"] - prior["avg_selling_price_per_pair"], 2),
    }

    change_pct = {
        "revenue": _safe_pct_change(current["revenue"], prior["revenue"]),
        "units_sold_amazon": _safe_pct_change(current["units_sold_amazon"], prior["units_sold_amazon"]),
        "pairs_sold": _safe_pct_change(current["pairs_sold"], prior["pairs_sold"]),
        "orders": _safe_pct_change(current["orders"], prior["orders"]),
        "aov": _safe_pct_change(current["aov"], prior["aov"]),
        "avg_unit_price_amazon": _safe_pct_change(current["avg_unit_price_amazon"], prior["avg_unit_price_amazon"]),
        "avg_selling_price_per_pair": _safe_pct_change(current["avg_selling_price_per_pair"], prior["avg_selling_price_per_pair"]),
    }

    result = {
        "period": period.upper(),
        "metric": metric,
        "reference_date": reference_date,
        "current_period": {
            "start": current_start,
            "end": current_end,
        },
        "prior_period": {
            "start": prior_start,
            "end": prior_end,
        },
        "current": current,
        "prior": prior,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "top_drivers": [],
    }

    if group_by is not None:
        current_grouped = (
            current_df.groupby(group_by, as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                pairs_sold=("pairs_sold", "sum"),
                units_sold_amazon=("units_sold_amazon", "sum"),
                orders=("amazon-order-id", "nunique"),
            )
        )

        prior_grouped = (
            prior_df.groupby(group_by, as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                pairs_sold=("pairs_sold", "sum"),
                units_sold_amazon=("units_sold_amazon", "sum"),
                orders=("amazon-order-id", "nunique"),
            )
        )

        drivers = current_grouped.merge(
            prior_grouped,
            on=group_by,
            how="outer",
            suffixes=("_current", "_prior"),
        ).fillna(0)

        current_metric_col = f"{metric}_current"
        prior_metric_col = f"{metric}_prior"

        drivers["change_abs"] = drivers[current_metric_col] - drivers[prior_metric_col]

        total_change = drivers["change_abs"].sum()
        if total_change != 0:
            drivers["contribution_pct"] = (drivers["change_abs"] / total_change) * 100
        else:
            drivers["contribution_pct"] = 0

        drivers = drivers.sort_values("change_abs", ascending=False).head(top_n).copy()

        result["top_drivers"] = drivers.to_dict(orient="records")

    return result


def explain_change(
    sales_df: pd.DataFrame,
    period: str = "MTD",
    metric: str = "revenue",
    dimension: str = "asin",
    top_n: int = 10,
) -> pd.DataFrame:
    valid_dimensions = {"type", "color", "item_name", "asin", "size"}
    valid_metrics = {"revenue", "pairs_sold", "units_sold_amazon", "orders"}

    if dimension not in valid_dimensions:
        raise ValueError(f"Unsupported dimension: {dimension}")

    if metric not in valid_metrics:
        raise ValueError(f"Unsupported metric: {metric}")

    data = _normalize_date_col(sales_df, date_col="date")
    if data.empty:
        base_cols = [
            f"{metric}_current",
            f"{metric}_prior",
            "change_abs",
            "change_pct",
            "contribution_pct",
        ]
        if dimension == "asin":
            return pd.DataFrame(columns=["asin", "item_name"] + base_cols)
        return pd.DataFrame(columns=[dimension] + base_cols)

    reference_date = data["date"].max()
    current_start, current_end = _get_period_bounds(reference_date, period)
    prior_start, prior_end = _get_prior_period_bounds(reference_date, period)

    current_df = _filter_period_bounds(data, current_start, current_end, date_col="date")
    prior_df = _filter_period_bounds(data, prior_start, prior_end, date_col="date")

    # key change is here
    group_cols = ["asin", "item_name"] if dimension == "asin" else [dimension]

    def grouped_agg(df: pd.DataFrame, suffix: str) -> pd.DataFrame:
        grouped = (
            df.groupby(group_cols, as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                pairs_sold=("pairs_sold", "sum"),
                units_sold_amazon=("units_sold_amazon", "sum"),
                orders=("amazon-order-id", "nunique"),
            )
        )

        grouped = grouped.rename(columns={
            "revenue": f"revenue_{suffix}",
            "pairs_sold": f"pairs_sold_{suffix}",
            "units_sold_amazon": f"units_sold_amazon_{suffix}",
            "orders": f"orders_{suffix}",
        })
        return grouped

    current_grouped = grouped_agg(current_df, "current")
    prior_grouped = grouped_agg(prior_df, "prior")

    merged = current_grouped.merge(
        prior_grouped,
        on=group_cols,
        how="outer",
    ).fillna(0)

    current_metric_col = f"{metric}_current"
    prior_metric_col = f"{metric}_prior"

    merged["change_abs"] = merged[current_metric_col] - merged[prior_metric_col]
    merged["change_pct"] = merged.apply(
        lambda row: _safe_pct_change(row[current_metric_col], row[prior_metric_col]),
        axis=1,
    )

    total_change = merged["change_abs"].sum()
    if total_change != 0:
        merged["contribution_pct"] = (merged["change_abs"] / total_change) * 100
    else:
        merged["contribution_pct"] = 0

    merged = merged.sort_values("change_abs", ascending=False).head(top_n).copy()

    merged["period"] = period.upper()
    merged["current_start"] = current_start
    merged["current_end"] = current_end
    merged["prior_start"] = prior_start
    merged["prior_end"] = prior_end
    merged["metric"] = metric
    merged["dimension"] = dimension

    return merged

def get_sales_summary(sales_df: pd.DataFrame, days: int = 7) -> dict:
    current_df, prior_df, reference_date, current_start, prior_start = _get_period_slices(
        sales_df, date_col="date", days=days
    )

    def summarize(data: pd.DataFrame) -> dict:
        revenue = float(data["revenue"].sum()) if "revenue" in data.columns else 0.0
        units_sold_amazon = int(data["units_sold_amazon"].sum()) if "units_sold_amazon" in data.columns else 0
        pairs_sold = int(data["pairs_sold"].sum()) if "pairs_sold" in data.columns else 0
        orders = int(data["amazon-order-id"].nunique()) if "amazon-order-id" in data.columns else 0

        aov = revenue / orders if orders > 0 else 0.0
        avg_selling_price_per_pair = revenue / pairs_sold if pairs_sold > 0 else 0.0
        avg_unit_price_amazon = revenue / units_sold_amazon if units_sold_amazon > 0 else 0.0

        return {
            "revenue": round(revenue, 2),
            "units_sold_amazon": units_sold_amazon,
            "pairs_sold": pairs_sold,
            "orders": orders,
            "aov": round(aov, 2),
            "avg_unit_price_amazon": round(avg_unit_price_amazon, 2),
            "avg_selling_price_per_pair": round(avg_selling_price_per_pair, 2),
        }

    current = summarize(current_df)
    prior = summarize(prior_df)

    change_pct = {
        "revenue": _safe_pct_change(current["revenue"], prior["revenue"]),
        "units_sold_amazon": _safe_pct_change(current["units_sold_amazon"], prior["units_sold_amazon"]),
        "pairs_sold": _safe_pct_change(current["pairs_sold"], prior["pairs_sold"]),
        "orders": _safe_pct_change(current["orders"], prior["orders"]),
        "aov": _safe_pct_change(current["aov"], prior["aov"]),
    }

    return {
        "period_days": days,
        "reference_date": reference_date,
        "current_period": {
            "start": current_start,
            "end": reference_date,
        },
        "prior_period": {
            "start": prior_start,
            "end": current_start - pd.Timedelta(days=1) if current_start is not None else None,
        },
        "current": current,
        "prior": prior,
        "change_pct": change_pct,
    }


def get_ppc_summary(ppc_df: pd.DataFrame, days: int = 7) -> dict:
    current_df, prior_df, reference_date, current_start, prior_start = _get_period_slices(
        ppc_df, date_col="date", days=days
    )

    def summarize(data: pd.DataFrame) -> dict:
        spend = float(data["spend"].sum()) if "spend" in data.columns else 0.0
        ad_sales = float(data["sales"].sum()) if "sales" in data.columns else 0.0
        clicks = int(data["clicks"].sum()) if "clicks" in data.columns else 0
        impressions = int(data["impressions"].sum()) if "impressions" in data.columns else 0
        orders = int(data["orders"].sum()) if "orders" in data.columns else 0
        units = int(data["units"].sum()) if "units" in data.columns else 0

        ctr = clicks / impressions if impressions > 0 else 0.0
        cvr = orders / clicks if clicks > 0 else 0.0
        acos = spend / ad_sales if ad_sales > 0 else None
        roas = ad_sales / spend if spend > 0 else None
        cpc = spend / clicks if clicks > 0 else 0.0

        return {
            "spend": round(spend, 2),
            "ad_sales": round(ad_sales, 2),
            "orders": orders,
            "units": units,
            "clicks": clicks,
            "impressions": impressions,
            "ctr": round(ctr, 4),
            "cvr": round(cvr, 4),
            "cpc": round(cpc, 2),
            "acos": round(acos, 4) if acos is not None else None,
            "roas": round(roas, 2) if roas is not None else None,
        }

    current = summarize(current_df)
    prior = summarize(prior_df)

    change_pct = {
        "spend": _safe_pct_change(current["spend"], prior["spend"]),
        "ad_sales": _safe_pct_change(current["ad_sales"], prior["ad_sales"]),
        "orders": _safe_pct_change(current["orders"], prior["orders"]),
        "clicks": _safe_pct_change(current["clicks"], prior["clicks"]),
    }

    return {
        "period_days": days,
        "reference_date": reference_date,
        "current_period": {
            "start": current_start,
            "end": reference_date,
        },
        "prior_period": {
            "start": prior_start,
            "end": current_start - pd.Timedelta(days=1) if current_start is not None else None,
        },
        "current": current,
        "prior": prior,
        "change_pct": change_pct,
    }


def get_marketing_summary(sales_df: pd.DataFrame, ppc_df: pd.DataFrame, days: int = 7) -> dict:
    sales_daily = (
        sales_df.groupby("date", as_index=False)
        .agg(
            total_sales=("revenue", "sum"),
            orders=("amazon-order-id", "nunique"),
            pairs_sold=("pairs_sold", "sum"),
        )
    )

    ppc_daily = (
        ppc_df.groupby("date", as_index=False)
        .agg(
            spend=("spend", "sum"),
            ad_sales=("sales", "sum"),
            ad_orders=("orders", "sum"),
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
        )
    )

    marketing_daily = sales_daily.merge(ppc_daily, on="date", how="left").fillna(0)

    current_df, prior_df, reference_date, current_start, prior_start = _get_period_slices(
        marketing_daily, date_col="date", days=days
    )

    def summarize(data: pd.DataFrame) -> dict:
        total_sales = float(data["total_sales"].sum()) if "total_sales" in data.columns else 0.0
        spend = float(data["spend"].sum()) if "spend" in data.columns else 0.0
        ad_sales = float(data["ad_sales"].sum()) if "ad_sales" in data.columns else 0.0
        total_orders = int(data["orders"].sum()) if "orders" in data.columns else 0
        ad_orders = int(data["ad_orders"].sum()) if "ad_orders" in data.columns else 0
        pairs_sold = int(data["pairs_sold"].sum()) if "pairs_sold" in data.columns else 0
        clicks = int(data["clicks"].sum()) if "clicks" in data.columns else 0
        impressions = int(data["impressions"].sum()) if "impressions" in data.columns else 0

        tacos = spend / total_sales if total_sales > 0 else None
        acos = spend / ad_sales if ad_sales > 0 else None
        roas = ad_sales / spend if spend > 0 else None
        ad_sales_share = ad_sales / total_sales if total_sales > 0 else None
        ctr = clicks / impressions if impressions > 0 else 0.0

        return {
            "total_sales": round(total_sales, 2),
            "ad_sales": round(ad_sales, 2),
            "spend": round(spend, 2),
            "total_orders": total_orders,
            "ad_orders": ad_orders,
            "pairs_sold": pairs_sold,
            "clicks": clicks,
            "impressions": impressions,
            "tacos": round(tacos, 4) if tacos is not None else None,
            "acos": round(acos, 4) if acos is not None else None,
            "roas": round(roas, 2) if roas is not None else None,
            "ad_sales_share": round(ad_sales_share, 4) if ad_sales_share is not None else None,
            "ctr": round(ctr, 4),
        }

    current = summarize(current_df)
    prior = summarize(prior_df)

    change_pct = {
        "total_sales": _safe_pct_change(current["total_sales"], prior["total_sales"]),
        "ad_sales": _safe_pct_change(current["ad_sales"], prior["ad_sales"]),
        "spend": _safe_pct_change(current["spend"], prior["spend"]),
        "pairs_sold": _safe_pct_change(current["pairs_sold"], prior["pairs_sold"]),
        "total_orders": _safe_pct_change(current["total_orders"], prior["total_orders"]),
        "tacos": _safe_pct_change(current["tacos"], prior["tacos"]) if current["tacos"] is not None and prior["tacos"] is not None else None,
        "acos": _safe_pct_change(current["acos"], prior["acos"]) if current["acos"] is not None and prior["acos"] is not None else None,
    }

    return {
        "period_days": days,
        "reference_date": reference_date,
        "current_period": {
            "start": current_start,
            "end": reference_date,
        },
        "prior_period": {
            "start": prior_start,
            "end": current_start - pd.Timedelta(days=1) if current_start is not None else None,
        },
        "current": current,
        "prior": prior,
        "change_pct": change_pct,
    }


def get_top_keywords(ppc_df: pd.DataFrame, days: int = 7, min_clicks: int = 5, top_n: int = 20) -> pd.DataFrame:
    df = ppc_df.copy()
    df = df.dropna(subset=["date"]).copy()

    reference_date = df["date"].max()
    start_date = reference_date - pd.Timedelta(days=days - 1)

    df = df[df["date"] >= start_date].copy()

    grouped = (
        df.groupby(["keyword", "match_type"], as_index=False)
        .agg(
            spend=("spend", "sum"),
            sales=("sales", "sum"),
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
            orders=("orders", "sum"),
        )
    )

    grouped["acos"] = grouped["spend"] / grouped["sales"]
    grouped["roas"] = grouped["sales"] / grouped["spend"]
    grouped["cvr"] = grouped["orders"] / grouped["clicks"]
    grouped["ctr"] = grouped["clicks"] / grouped["impressions"]
    grouped["cpc"] = grouped["spend"] / grouped["clicks"]

    grouped.loc[grouped["sales"] == 0, "acos"] = None
    grouped.loc[grouped["spend"] == 0, "roas"] = None
    grouped.loc[grouped["clicks"] == 0, "cvr"] = None
    grouped.loc[grouped["impressions"] == 0, "ctr"] = None
    grouped.loc[grouped["clicks"] == 0, "cpc"] = None

    grouped = grouped[grouped["clicks"] >= min_clicks]
    grouped = grouped.sort_values("sales", ascending=False)

    return grouped.head(top_n)


def get_top_products(
    sales_df: pd.DataFrame,
    days: int = 7,
    metric: str = "revenue",
    top_n: int = 10
) -> pd.DataFrame:
    df = sales_df.copy()
    df = df.dropna(subset=["date"]).copy()

    reference_date = df["date"].max()
    start_date = reference_date - pd.Timedelta(days=days - 1)

    df = df[df["date"] >= start_date].copy()

    grouped = (
        df.groupby(
            ["asin", "item_name", "type", "color", "size"],
            as_index=False
        )
        .agg(
            revenue=("revenue", "sum"),
            units_sold_amazon=("units_sold_amazon", "sum"),
            pairs_sold=("pairs_sold", "sum"),
            orders=("amazon-order-id", "nunique"),
        )
    )

    grouped["aov"] = grouped["revenue"] / grouped["orders"]
    grouped["avg_price_per_pair"] = grouped["revenue"] / grouped["pairs_sold"]

    grouped.loc[grouped["orders"] == 0, "aov"] = None
    grouped.loc[grouped["pairs_sold"] == 0, "avg_price_per_pair"] = None

    grouped = grouped.sort_values(metric, ascending=False)

    return grouped.head(top_n)


def get_product_mix(sales_df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    df = sales_df.copy()
    df = df.dropna(subset=["date"]).copy()

    reference_date = df["date"].max()
    start_date = reference_date - pd.Timedelta(days=days - 1)

    df = df[df["date"] >= start_date]

    grouped = (
        df.groupby("type", as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            pairs_sold=("pairs_sold", "sum"),
            orders=("amazon-order-id", "nunique"),
        )
    )

    total_revenue = grouped["revenue"].sum()
    total_pairs = grouped["pairs_sold"].sum()

    grouped["revenue_pct"] = grouped["revenue"] / total_revenue
    grouped["pairs_pct"] = grouped["pairs_sold"] / total_pairs

    grouped = grouped.sort_values("revenue", ascending=False)

    return grouped


def get_color_performance(sales_df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    df = sales_df.copy()
    df = df.dropna(subset=["date"]).copy()

    reference_date = df["date"].max()
    start_date = reference_date - pd.Timedelta(days=days - 1)

    df = df[df["date"] >= start_date]

    grouped = (
        df.groupby("color", as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            pairs_sold=("pairs_sold", "sum"),
            orders=("amazon-order-id", "nunique"),
        )
    )

    total_revenue = grouped["revenue"].sum()
    total_pairs = grouped["pairs_sold"].sum()

    grouped["revenue_pct"] = grouped["revenue"] / total_revenue
    grouped["pairs_pct"] = grouped["pairs_sold"] / total_pairs

    grouped = grouped.sort_values("revenue", ascending=False)

    return grouped

def get_metric_trend(
    sales_df: pd.DataFrame,
    ppc_df: pd.DataFrame,
    metric: str,
    lookback_weeks: int = 12,
) -> pd.DataFrame:
    valid_metrics = {
        "revenue",
        "tacos",
        "acos",
        "roas",
        "ad_spend",
        "ad_sales",
        "aov",
        "3_pack_share",
    }

    if metric not in valid_metrics:
        raise ValueError(f"Unsupported metric: {metric}")

    sales = _normalize_date_col(sales_df, date_col="date")
    ppc = _normalize_date_col(ppc_df, date_col="date")

    if sales.empty:
        return pd.DataFrame(columns=["week_start", "week_end", metric])

    reference_date = sales["date"].max()
    trend_start = reference_date - pd.Timedelta(days=(lookback_weeks * 7) - 1)

    sales = sales.loc[
        (sales["date"] >= trend_start) & (sales["date"] <= reference_date)
    ].copy()

    ppc = ppc.loc[
        (ppc["date"] >= trend_start) & (ppc["date"] <= reference_date)
    ].copy()

    # convert back to datetime for weekly grouping
    sales["date"] = pd.to_datetime(sales["date"])
    ppc["date"] = pd.to_datetime(ppc["date"])

    # -----------------------------
    # sales weekly
    # -----------------------------
    sales_weekly = (
        sales.groupby(pd.Grouper(key="date", freq="W-SAT"))
        .agg(
            revenue=("revenue", "sum"),
            orders=("amazon-order-id", "nunique"),
            pairs_sold=("pairs_sold", "sum"),
            units_sold_amazon=("units_sold_amazon", "sum"),
        )
        .reset_index()
    )

    sales_weekly["week_end"] = sales_weekly["date"]
    sales_weekly["week_start"] = sales_weekly["week_end"] - pd.Timedelta(days=6)
    sales_weekly["aov"] = sales_weekly["revenue"] / sales_weekly["orders"]
    sales_weekly.loc[sales_weekly["orders"] == 0, "aov"] = None

    # 3-pack share
    sales["is_3_pack"] = sales["type"].astype(str).str.contains("3-pack", case=False, na=False)

    three_pack_weekly = (
        sales.groupby([pd.Grouper(key="date", freq="W-SAT"), "is_3_pack"])
        .agg(revenue=("revenue", "sum"))
        .reset_index()
    )

    three_pack_pivot = (
        three_pack_weekly.pivot(index="date", columns="is_3_pack", values="revenue")
        .fillna(0)
        .reset_index()
    )

    if True not in three_pack_pivot.columns:
        three_pack_pivot[True] = 0.0
    if False not in three_pack_pivot.columns:
        three_pack_pivot[False] = 0.0

    three_pack_pivot["total_revenue"] = three_pack_pivot[True] + three_pack_pivot[False]
    three_pack_pivot["3_pack_share"] = three_pack_pivot[True] / three_pack_pivot["total_revenue"]
    three_pack_pivot.loc[three_pack_pivot["total_revenue"] == 0, "3_pack_share"] = None
    three_pack_pivot = three_pack_pivot.rename(columns={"date": "week_end"})

    # -----------------------------
    # ppc weekly
    # -----------------------------
    if not ppc.empty:
        ppc_weekly = (
            ppc.groupby(pd.Grouper(key="date", freq="W-SAT"))
            .agg(
                ad_spend=("spend", "sum"),
                ad_sales=("sales", "sum"),
                clicks=("clicks", "sum"),
                impressions=("impressions", "sum"),
                ad_orders=("orders", "sum"),
            )
            .reset_index()
        )
        ppc_weekly["week_end"] = ppc_weekly["date"]
        ppc_weekly["acos"] = ppc_weekly["ad_spend"] / ppc_weekly["ad_sales"]
        ppc_weekly["roas"] = ppc_weekly["ad_sales"] / ppc_weekly["ad_spend"]
        ppc_weekly.loc[ppc_weekly["ad_sales"] == 0, "acos"] = None
        ppc_weekly.loc[ppc_weekly["ad_spend"] == 0, "roas"] = None
    else:
        ppc_weekly = pd.DataFrame(columns=[
            "week_end", "ad_spend", "ad_sales", "clicks", "impressions", "ad_orders", "acos", "roas"
        ])

    # -----------------------------
    # merge all weekly data
    # -----------------------------
    trend = sales_weekly.merge(
        ppc_weekly[["week_end", "ad_spend", "ad_sales", "acos", "roas"]],
        on="week_end",
        how="left",
    ).merge(
        three_pack_pivot[["week_end", "3_pack_share"]],
        on="week_end",
        how="left",
    )

    trend["ad_spend"] = trend["ad_spend"].fillna(0)
    trend["ad_sales"] = trend["ad_sales"].fillna(0)

    trend["tacos"] = trend["ad_spend"] / trend["revenue"]
    trend.loc[trend["revenue"] == 0, "tacos"] = None

    # select output columns based on metric
    base_cols = [
        "week_start",
        "week_end",
        "revenue",
        "ad_spend",
        "ad_sales",
        "tacos",
        "acos",
        "roas",
        "aov",
        "3_pack_share",
        "orders",
        "pairs_sold",
        "units_sold_amazon",
    ]

    trend = trend[base_cols].sort_values("week_start").copy()

    # round useful metrics
    money_cols = ["revenue", "ad_spend", "ad_sales", "aov"]
    ratio_cols = ["tacos", "acos", "roas", "3_pack_share"]

    for col in money_cols:
        if col in trend.columns:
            trend[col] = trend[col].round(2)

    for col in ratio_cols:
        if col in trend.columns:
            trend[col] = trend[col].round(4)

    # keep metric first for readability
    ordered_cols = ["week_start", "week_end", metric] + [c for c in base_cols if c not in {"week_start", "week_end", metric}]
    trend = trend[ordered_cols]

    return trend

def get_metric_trend(
    sales_df: pd.DataFrame,
    ppc_df: pd.DataFrame,
    metric: str,
    lookback_weeks: int = 12,
) -> dict:
    valid_metrics = {
        "revenue",
        "tacos",
        "acos",
        "roas",
        "ad_spend",
        "ad_sales",
        "aov",
        "3_pack_share",
    }

    if metric not in valid_metrics:
        raise ValueError(f"Unsupported metric: {metric}")

    sales = _normalize_date_col(sales_df, date_col="date")
    ppc = _normalize_date_col(ppc_df, date_col="date")

    if sales.empty:
        return {
            "metric": metric,
            "summary": {},
            "weekly_data": [],
        }

    reference_date = sales["date"].max()
    trend_start = reference_date - pd.Timedelta(days=(lookback_weeks * 7) - 1)

    sales = sales.loc[
        (sales["date"] >= trend_start) &
        (sales["date"] <= reference_date)
    ].copy()

    ppc = ppc.loc[
        (ppc["date"] >= trend_start) &
        (ppc["date"] <= reference_date)
    ].copy()

    sales["date"] = pd.to_datetime(sales["date"])
    ppc["date"] = pd.to_datetime(ppc["date"])

    # -----------------------------
    # weekly sales
    # -----------------------------
    sales_weekly = (
        sales.groupby(pd.Grouper(key="date", freq="W-SAT"))
        .agg(
            revenue=("revenue", "sum"),
            orders=("amazon-order-id", "nunique"),
            pairs_sold=("pairs_sold", "sum"),
            units_sold_amazon=("units_sold_amazon", "sum"),
        )
        .reset_index()
    )

    sales_weekly["week_end"] = sales_weekly["date"]
    sales_weekly["week_start"] = sales_weekly["week_end"] - pd.Timedelta(days=6)

    sales_weekly["aov"] = sales_weekly["revenue"] / sales_weekly["orders"]
    sales_weekly.loc[sales_weekly["orders"] == 0, "aov"] = None

    # -----------------------------
    # 3-pack share
    # -----------------------------
    sales["is_3_pack"] = sales["type"].astype(str).str.contains(
        "3-pack",
        case=False,
        na=False
    )

    three_pack_weekly = (
        sales.groupby([pd.Grouper(key="date", freq="W-SAT"), "is_3_pack"])
        .agg(revenue=("revenue", "sum"))
        .reset_index()
    )

    three_pack_pivot = (
        three_pack_weekly
        .pivot(index="date", columns="is_3_pack", values="revenue")
        .fillna(0)
        .reset_index()
    )

    if True not in three_pack_pivot.columns:
        three_pack_pivot[True] = 0.0

    if False not in three_pack_pivot.columns:
        three_pack_pivot[False] = 0.0

    three_pack_pivot["total_revenue"] = (
        three_pack_pivot[True] + three_pack_pivot[False]
    )

    three_pack_pivot["3_pack_share"] = (
        three_pack_pivot[True] / three_pack_pivot["total_revenue"]
    )

    three_pack_pivot.loc[
        three_pack_pivot["total_revenue"] == 0,
        "3_pack_share"
    ] = None

    three_pack_pivot = three_pack_pivot.rename(
        columns={"date": "week_end"}
    )

    # -----------------------------
    # weekly PPC
    # -----------------------------
    if not ppc.empty:
        ppc_weekly = (
            ppc.groupby(pd.Grouper(key="date", freq="W-SAT"))
            .agg(
                ad_spend=("spend", "sum"),
                ad_sales=("sales", "sum"),
                clicks=("clicks", "sum"),
                impressions=("impressions", "sum"),
                ad_orders=("orders", "sum"),
            )
            .reset_index()
        )

        ppc_weekly["week_end"] = ppc_weekly["date"]

        ppc_weekly["acos"] = (
            ppc_weekly["ad_spend"] / ppc_weekly["ad_sales"]
        )

        ppc_weekly["roas"] = (
            ppc_weekly["ad_sales"] / ppc_weekly["ad_spend"]
        )

        ppc_weekly.loc[
            ppc_weekly["ad_sales"] == 0,
            "acos"
        ] = None

        ppc_weekly.loc[
            ppc_weekly["ad_spend"] == 0,
            "roas"
        ] = None

    else:
        ppc_weekly = pd.DataFrame(columns=[
            "week_end",
            "ad_spend",
            "ad_sales",
            "acos",
            "roas",
        ])

    # -----------------------------
    # merge
    # -----------------------------
    trend = (
        sales_weekly
        .merge(
            ppc_weekly[
                ["week_end", "ad_spend", "ad_sales", "acos", "roas"]
            ],
            on="week_end",
            how="left"
        )
        .merge(
            three_pack_pivot[
                ["week_end", "3_pack_share"]
            ],
            on="week_end",
            how="left"
        )
    )

    trend["ad_spend"] = trend["ad_spend"].fillna(0)
    trend["ad_sales"] = trend["ad_sales"].fillna(0)

    trend["tacos"] = trend["ad_spend"] / trend["revenue"]
    trend.loc[trend["revenue"] == 0, "tacos"] = None

    trend = trend.sort_values("week_start").copy()

    # -----------------------------
    # summary layer
    # -----------------------------
    metric_series = trend[metric].dropna()

    if len(metric_series) >= 8:
        last_4 = metric_series.tail(4).mean()
        prior_4 = metric_series.iloc[-8:-4].mean()
    elif len(metric_series) >= 4:
        last_4 = metric_series.tail(4).mean()
        prior_4 = metric_series.head(len(metric_series) - 4).mean()
    else:
        last_4 = metric_series.mean()
        prior_4 = None

    if prior_4 is not None and prior_4 != 0:
        change_pct = round(((last_4 - prior_4) / prior_4) * 100, 2)
    else:
        change_pct = None

    if change_pct is None:
        trend_direction = "insufficient_data"
    elif change_pct > 5:
        trend_direction = "improving" if metric in ["roas", "revenue", "aov", "3_pack_share"] else "worsening"
    elif change_pct < -5:
        trend_direction = "worsening" if metric in ["roas", "revenue", "aov", "3_pack_share"] else "improving"
    else:
        trend_direction = "stable"

    volatility_ratio = (
        metric_series.std() / metric_series.mean()
        if len(metric_series) > 1 and metric_series.mean() != 0
        else 0
    )

    if volatility_ratio > 0.30:
        volatility = "high"
    elif volatility_ratio > 0.15:
        volatility = "moderate"
    else:
        volatility = "low"

    highest_idx = metric_series.idxmax() if not metric_series.empty else None
    lowest_idx = metric_series.idxmin() if not metric_series.empty else None

    summary = {
        "trend_direction": trend_direction,
        "volatility": volatility,
        "last_4_week_avg": round(last_4, 4) if pd.notna(last_4) else None,
        "prior_4_week_avg": round(prior_4, 4) if prior_4 is not None and pd.notna(prior_4) else None,
        "change_pct": change_pct,
        "highest_week": {
            "week_start": str(trend.loc[highest_idx, "week_start"]) if highest_idx is not None else None,
            "week_end": str(trend.loc[highest_idx, "week_end"]) if highest_idx is not None else None,
            "value": round(float(metric_series.max()), 4) if not metric_series.empty else None,
        },
        "lowest_week": {
            "week_start": str(trend.loc[lowest_idx, "week_start"]) if lowest_idx is not None else None,
            "week_end": str(trend.loc[lowest_idx, "week_end"]) if lowest_idx is not None else None,
            "value": round(float(metric_series.min()), 4) if not metric_series.empty else None,
        },
    }

    # round for display
    display_cols = [
        "revenue",
        "ad_spend",
        "ad_sales",
        "aov",
        "tacos",
        "acos",
        "roas",
        "3_pack_share",
    ]

    for col in display_cols:
        if col in trend.columns:
            trend[col] = trend[col].round(4)

    return {
        "metric": metric,
        "trend_period": {
            "start": str(trend["week_start"].min()),
            "end": str(trend["week_end"].max()),
        },
        "summary": summary,
        "weekly_data": trend.to_dict(orient="records"),
    }

def get_keyword_bid_recommendations(
    ppc_df: pd.DataFrame,
    days: int = 30,
    target_acos: float = 0.25,
    min_clicks: int = 10,
    min_spend: float = 15.0,
    pause_clicks_threshold: int = 20,
    strong_cvr_threshold: float = 0.12,
    top_n: int = 50,
) -> pd.DataFrame:
    df = ppc_df.copy()
    df = df.dropna(subset=["date"]).copy()

    if df.empty:
        return pd.DataFrame(columns=[
            "keyword",
            "match_type",
            "spend",
            "sales",
            "clicks",
            "orders",
            "impressions",
            "ctr",
            "cvr",
            "cpc",
            "acos",
            "roas",
            "suggested_cpc",
            "action",
            "reason",
        ])

    reference_date = df["date"].max()
    start_date = reference_date - pd.Timedelta(days=days - 1)

    df = df[df["date"] >= start_date].copy()

    grouped = (
        df.groupby(["keyword", "match_type"], as_index=False)
        .agg(
            spend=("spend", "sum"),
            sales=("sales", "sum"),
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
            orders=("orders", "sum"),
        )
    )

    grouped["ctr"] = grouped["clicks"] / grouped["impressions"]
    grouped["cvr"] = grouped["orders"] / grouped["clicks"]
    grouped["cpc"] = grouped["spend"] / grouped["clicks"]
    grouped["acos"] = grouped["spend"] / grouped["sales"]
    grouped["roas"] = grouped["sales"] / grouped["spend"]

    grouped.loc[grouped["impressions"] == 0, "ctr"] = None
    grouped.loc[grouped["clicks"] == 0, "cvr"] = None
    grouped.loc[grouped["clicks"] == 0, "cpc"] = None
    grouped.loc[grouped["sales"] == 0, "acos"] = None
    grouped.loc[grouped["spend"] == 0, "roas"] = None

    def classify_action(row):
        clicks = row["clicks"]
        spend = row["spend"]
        sales = row["sales"]
        acos = row["acos"]
        cvr = row["cvr"]
        cpc = row["cpc"]

        if clicks < min_clicks and spend < min_spend:
            return pd.Series({
                "suggested_cpc": round(cpc, 2) if pd.notna(cpc) else None,
                "action": "Hold",
                "reason": "Not enough data yet",
            })

        if clicks >= pause_clicks_threshold and sales == 0:
            return pd.Series({
                "suggested_cpc": 0.0,
                "action": "Pause",
                "reason": "Enough clicks with no sales",
            })

        if sales == 0 and spend >= min_spend:
            reduced_cpc = cpc * 0.7 if pd.notna(cpc) else None
            return pd.Series({
                "suggested_cpc": round(reduced_cpc, 2) if reduced_cpc is not None else None,
                "action": "Reduce bid",
                "reason": "Spend present but no sales yet",
            })

        if pd.notna(acos) and acos > target_acos:
            suggested_cpc = cpc * (target_acos / acos) if pd.notna(cpc) and acos > 0 else None
            return pd.Series({
                "suggested_cpc": round(suggested_cpc, 2) if suggested_cpc is not None else None,
                "action": "Reduce bid",
                "reason": "ACOS above target",
            })

        if pd.notna(acos) and acos <= target_acos and pd.notna(cvr) and cvr >= strong_cvr_threshold:
            suggested_cpc = cpc * (target_acos / acos) if pd.notna(cpc) and acos > 0 else cpc
            return pd.Series({
                "suggested_cpc": round(suggested_cpc, 2) if suggested_cpc is not None else None,
                "action": "Increase bid",
                "reason": "Profitable keyword with strong conversion",
            })

        return pd.Series({
            "suggested_cpc": round(cpc, 2) if pd.notna(cpc) else None,
            "action": "Hold",
            "reason": "Borderline or stable performance",
        })

    recommendations = grouped.apply(classify_action, axis=1)
    grouped = pd.concat([grouped, recommendations], axis=1)

    grouped = grouped.sort_values(["spend", "clicks"], ascending=[False, False]).head(top_n).copy()

    numeric_cols = ["spend", "sales", "ctr", "cvr", "cpc", "acos", "roas", "suggested_cpc"]
    for col in numeric_cols:
        if col in grouped.columns:
            grouped[col] = grouped[col].round(4)

    grouped["period_days"] = days
    grouped["target_acos"] = target_acos

    return grouped