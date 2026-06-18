import pandas as pd
from .tables import df_to_html_table


def _to_number(value):
    try:
        return float(str(value).replace("$", "").replace(",", "").replace("%", ""))
    except Exception:
        return 0


def _money(value):
    return f"${_to_number(value):,.0f}"


def _short(value, max_len=48):
    value = str(value)
    return value if len(value) <= max_len else value[:max_len] + "..."


def _clean_product_name(value):
    value = str(value).lower()

    # ---------- PACK TYPE ----------
    if "3 pack" in value or "3-pack" in value or "white 3" in value or "black 2" in value:
        pack = "3-pack"
    elif "6 pair" in value or "6-pack" in value:
        pack = "6-pack"
    else:
        pack = "single"

    # ---------- COLOR ----------
    if "white" in value:
        color = "white"
    elif "black" in value:
        color = "black"
    elif "blue" in value:
        color = "blue"
    else:
        color = "unknown"

    # ---------- SIZE ----------
    if "small/medium" in value or "small, medium" in value:
        size = "S/M"
    elif "large/x-large" in value or "large, x-large" in value:
        size = "L/XL"
    else:
        size = "?"

    return f"{pack}, {color}, {size}"


def _bar_list(df, label_col, value_col="revenue", max_rows=8, show_pct=True):
    if df is None or df.empty or label_col not in df.columns or value_col not in df.columns:
        return "<div class='empty'>No data available.</div>"

    d = df.copy().head(max_rows)
    d["_value"] = d[value_col].apply(_to_number)

    max_value = d["_value"].max()
    total_value = d["_value"].sum()

    if max_value <= 0 or total_value <= 0:
        return "<div class='empty'>No data available.</div>"

    rows = ""

    for _, row in d.iterrows():
        label = _short(row[label_col])
        value = row["_value"]
        width = max((value / max_value) * 100, 4)
        share = (value / total_value) * 100

        if show_pct:
            display_value = f"{share:,.1f}%"
        else:
            if value_col == "pairs_per_day":
                display_value = f"{value:,.1f}/day"
            else:
                display_value = _money(value)

        rows += f"""
        <div class="sales-bar-row">
            <div class="sales-bar-label">{label}</div>
            <div class="sales-bar-track">
                <div class="sales-bar-fill" style="width:{width}%"></div>
            </div>
            <div class="sales-bar-value">{display_value}</div>
        </div>
        """

    return f"<div class='sales-bar-list'>{rows}</div>"


def _mix_card(title, df, label_col, value_col="revenue", max_rows=4):
    return f"""
    <div class="sales-card">
        <h3>{title}</h3>
        {_bar_list(df, label_col, value_col, max_rows=max_rows)}
    </div>
    """


def build_sales_tab(context):
    sales_summary = context.get("sales_summary", {})
    sales_analysis = context.get("sales_analysis", {})
    period = context.get("period", "")

    sales_by_asin = sales_analysis.get("sales_by_asin")
    sales_by_type = sales_analysis.get("sales_by_type")
    sales_by_size = sales_analysis.get("sales_by_size")
    sales_by_color = sales_analysis.get("sales_by_color")
    sales_by_state = sales_analysis.get("sales_by_state")
    velocity_df = sales_analysis.get("velocity_df")
    heatmap_df = sales_analysis.get("heatmap_df")
    last_4_weeks_sku_table = sales_analysis.get("last_4_weeks_sku_table")

    if (
        last_4_weeks_sku_table is not None
        and not last_4_weeks_sku_table.empty
        and "product_name" in last_4_weeks_sku_table.columns
    ):
        last_4_weeks_sku_table = last_4_weeks_sku_table.copy()
        last_4_weeks_sku_table["sku"] = last_4_weeks_sku_table["product_name"].apply(_clean_product_name)

        if (
            last_4_weeks_sku_table is not None
            and not last_4_weeks_sku_table.empty
            and "product_name" in last_4_weeks_sku_table.columns
        ):
            last_4_weeks_sku_table = last_4_weeks_sku_table.copy()
            last_4_weeks_sku_table["sku"] = last_4_weeks_sku_table["product_name"].apply(_clean_product_name)

            cols = ["sku"] + [
                col for col in last_4_weeks_sku_table.columns
                if col != "product_name" and col != "sku"
            ]

            last_4_weeks_sku_table = last_4_weeks_sku_table[cols]

    if velocity_df is not None and not velocity_df.empty and "product_name" in velocity_df.columns:
        velocity_df = velocity_df.copy()
        velocity_df["clean_name"] = velocity_df["product_name"].apply(_clean_product_name)

    if sales_by_asin is not None and not sales_by_asin.empty and "product_name" in sales_by_asin.columns:
        sales_by_asin = sales_by_asin.copy()
        sales_by_asin["clean_name"] = sales_by_asin["product_name"].apply(_clean_product_name)

    best_product = "N/A"

    if sales_by_asin is not None and not sales_by_asin.empty:
        label_col = "clean_name" if "clean_name" in sales_by_asin.columns else "product_name"
        best_product = _short(sales_by_asin.iloc[0][label_col], 28)

    state_col = None

    if sales_by_state is not None and not sales_by_state.empty:
        for col in ["ship-state", "ship_state", "state", "buyer_state"]:
            if col in sales_by_state.columns:
                state_col = col
                break

    weekday_note = ""

    if (
        heatmap_df is not None
        and not heatmap_df.empty
        and "weekday" in heatmap_df.columns
        and "revenue" in heatmap_df.columns
    ):
        h = heatmap_df.copy()
        h["_revenue"] = h["revenue"].apply(_to_number)

        if not h.empty:
            best_day = h.sort_values("_revenue", ascending=False).iloc[0]["weekday"]
            worst_day = h.sort_values("_revenue", ascending=True).iloc[0]["weekday"]
            weekday_note = (
                f"Best sales day: <strong>{best_day}</strong>. "
                f"Lowest: <strong>{worst_day}</strong>."
            )

    period_days_map = {
        "LAST_7_DAYS": 7,
        "LAST_30_DAYS": 30,
        "MTD": 30,
        "YTD": 365,
    }

    period_days = period_days_map.get(period, 30)

    avg_daily_sales = (
        float(sales_summary.get("revenue", 0)) / period_days
    )

    velocity_label_col = (
        "clean_name"
        if velocity_df is not None
        and not velocity_df.empty
        and "clean_name" in velocity_df.columns
        else "product_name"
    )

    velocity_value_col = (
        "pairs_per_day"
        if velocity_df is not None
        and not velocity_df.empty
        and "pairs_per_day" in velocity_df.columns
        else "revenue_per_day"
    
    )
    return f"""
    <div class="sales-v2">

        <section class="sales-hero">
            <div>
                <h1>Sales Performance</h1>
                <p>Commercial view of product demand, mix, geography, and velocity.</p>
            </div>
            <div class="period-pill">Period: {period}</div>
        </section>

        <section class="sales-kpi-grid">
            <div class="sales-kpi">
                <span>Revenue</span>
                <strong>${float(sales_summary.get("revenue", 0)):,.0f}</strong>
            </div>

            <div class="sales-kpi">
                <span>Orders</span>
                <strong>{float(sales_summary.get("orders", 0)):,.0f}</strong>
            </div>

            <div class="sales-kpi">
                <span>Pairs Sold</span>
                <strong>{float(sales_summary.get("pairs_sold", 0)):,.0f}</strong>
            </div>

            <div class="sales-kpi">
                <span>AOV</span>
                <strong>${float(sales_summary.get("aov", 0)):,.2f}</strong>
            </div>

            <div class="sales-kpi">
                <span>Avg Daily Sales</span>
                <strong>${avg_daily_sales:,.0f}</strong>
            </div>
        </section>

        <section class="sales-main-grid">
            <div class="sales-card large">
                <div class="sales-card-header">
                    <h2>Product Performance</h2>
                    <span>Top products by revenue</span>
                </div>
                {_bar_list(sales_by_asin, "clean_name" if sales_by_asin is not None and "clean_name" in sales_by_asin.columns else "product_name", "revenue", max_rows=8)}
            </div>

            <div class="sales-card">
                <div class="sales-card-header">
                    <h2>Sales Mix Summary</h2>
                    <span>Current period concentration</span>
                </div>

                <div class="sales-highlight">
                    <span>Main Driver</span>
                    <strong>{best_product}</strong>
                    <p>Largest revenue contributor for the selected period.</p>
                </div>

                {_mix_card("Pack Type Mix", sales_by_type, "type", "revenue", max_rows=3)}
            </div>
        </section>

        <section class="sales-three-grid">
            {_mix_card("Revenue by Type", sales_by_type, "type", "revenue", max_rows=5)}
            {_mix_card("Revenue by Color", sales_by_color, "color", "revenue", max_rows=5)}
            {_mix_card("Revenue by Size", sales_by_size, "size", "revenue", max_rows=5)}
        </section>

        <section class="sales-two-grid">
            <div class="sales-card">
                <h2>Top States</h2>
                {_bar_list(sales_by_state, state_col, "revenue", max_rows=10) if state_col else "<div class='empty'>No state data available.</div>"}
            </div>

            <div class="sales-card">
                <h2>Sales Rhythm</h2>
                {_bar_list(heatmap_df, "weekday", "revenue", max_rows=7)}
                <p class="sales-note">{weekday_note}</p>
            </div>
        </section>

        <section class="sales-card full">
            <div class="sales-card-header">
                <h2>Fastest Moving SKUs</h2>
                <span>Average pairs sold per day</span>
            </div>

            {_bar_list(
                velocity_df,
                velocity_label_col,
                velocity_value_col,
                max_rows=5,
                show_pct=False,
            )}

            <p class="sales-note">
                Higher values indicate stronger daily sell-through velocity.
            </p>
        </section>

        <section class="sales-card full">
            <div class="sales-card-header">
                <h2>Last 3 Weeks SKU Performance</h2>
                <span>Fixed period, independent from selected filter</span>
            </div>

            {df_to_html_table(last_4_weeks_sku_table, max_rows=20)}
        </section>

        <section class="sales-card full">
            <h2>Sales Detail Table</h2>
            {df_to_html_table(sales_by_asin, max_rows=20)}
        </section>

    </div>
    """