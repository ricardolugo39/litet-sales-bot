from .styles import get_styles
from .sales_tab import build_sales_tab

from .charts import (
    build_line_chart,
    build_bar_chart,
    build_sales_tacos_chart,
    build_horizontal_bar_chart,
    build_vertical_bar_chart,
    build_donut_chart,
)

from .sections import (
    build_navbar,
    build_hero,
    build_ai_section,
    build_sales_and_attention_section,
    build_ppc_product_inventory_section,
    build_table_section,
)

from .tables import df_to_html_table


def safe_get(d, key, default=0):
    return d.get(key, default) if isinstance(d, dict) else default


def build_html_dashboard(context):
    period = context.get("period")

    sales_summary = context.get("sales_summary", {})
    marketing_summary = context.get("marketing_summary", {})
    comparison_view = context.get("comparison_view")
    inventory_risk = context.get("inventory_risk")
    keyword_actions = context.get("keyword_actions")
    bid_recs = context.get("bid_recs")
    ai_summary = context.get("ai_summary", {})
    trend_view = context.get("trend_view")

    sales_analysis = context.get("sales_analysis", {})

    sales_by_asin = sales_analysis.get("sales_by_asin")
    sales_by_type = sales_analysis.get("sales_by_type")
    sales_by_size = sales_analysis.get("sales_by_size")
    sales_by_color = sales_analysis.get("sales_by_color")
    sales_by_state = sales_analysis.get("sales_by_state")
    velocity_df = sales_analysis.get("velocity_df")
    heatmap_df = sales_analysis.get("heatmap_df")

    # Clean product names
    if sales_by_asin is not None and not sales_by_asin.empty and "product_name" in sales_by_asin.columns:
        sales_by_asin = sales_by_asin.copy()
        sales_by_asin["clean_name"] = (
            sales_by_asin["product_name"]
            .astype(str)
            .str.replace("LITET Cycling Socks for Men & Women", "", regex=False)
            .str.replace("LITET cycling socks", "", regex=False)
            .str.replace("LITET Cycling Socks", "", regex=False)
            .str.replace("Cycling Socks for Men & Women", "", regex=False)
            .str.replace("cycling socks", "", regex=False)
            .str.replace("LITET", "", regex=False)
            .str.strip(" -")
            .str.strip()
        )
        sales_by_asin["clean_name"] = sales_by_asin["clean_name"].replace("", "Product")

    revenue = safe_get(sales_summary, "revenue")
    orders = safe_get(sales_summary, "orders")
    pairs_sold = safe_get(sales_summary, "pairs_sold")
    aov = safe_get(sales_summary, "aov")

    ad_spend = safe_get(marketing_summary, "ad_spend")
    ad_sales = safe_get(marketing_summary, "ad_sales")
    acos = safe_get(marketing_summary, "acos")
    tacos = safe_get(marketing_summary, "tacos")
    roas = safe_get(marketing_summary, "roas")

    critical_inventory = (
        inventory_risk[
            inventory_risk["inventory_risk"].isin(["Critical", "High"])
        ].shape[0]
        if inventory_risk is not None
        and len(inventory_risk) > 0
        and "inventory_risk" in inventory_risk.columns
        else 0
    )

    navbar = build_navbar()

    hero = build_hero(
        period=period,
        revenue=revenue,
        orders=orders,
        pairs_sold=pairs_sold,
        aov=aov,
        tacos=tacos,
        kpi_comparison=context.get("kpi_comparison", {}),
    )

    ai_section = build_ai_section(ai_summary)

    trend_chart = build_sales_tacos_chart(trend_view)

    sales_attention = build_sales_and_attention_section(
        trend_chart=trend_chart,
        revenue=revenue,
        orders=orders,
        tacos=tacos,
        acos=acos,
        critical_inventory=critical_inventory,
    )

    comparison_section = build_table_section(
        "Period Comparison",
        comparison_view,
        max_rows=10,
    )

    ppc_product_inventory = build_ppc_product_inventory_section(
        ad_spend=ad_spend,
        ad_sales=ad_sales,
        acos=acos,
        roas=roas,
        product_chart="",
        inventory_risk=inventory_risk,
    )

    # SALES CHARTS
    sales_product_chart = build_horizontal_bar_chart(
        sales_by_asin,
        x_col="revenue",
        y_col="clean_name",
        title="Top Products by Revenue",
        max_rows=10,
    )

    sales_type_chart = build_horizontal_bar_chart(
        sales_by_type,
        x_col="revenue",
        y_col="type",
        title="Revenue by Type",
        max_rows=10,
    )

    sales_size_chart = build_horizontal_bar_chart(
        sales_by_size,
        x_col="revenue",
        y_col="size",
        title="Revenue by Size",
        max_rows=10,
    )

    sales_color_chart = build_horizontal_bar_chart(
        sales_by_color,
        x_col="revenue",
        y_col="color",
        title="Revenue by Color",
        max_rows=10,
    )

    state_label_col = None

    if sales_by_state is not None and not sales_by_state.empty:
        for col in ["ship-state", "ship_state", "state", "buyer_state"]:
            if col in sales_by_state.columns:
                state_label_col = col
                break

    sales_state_chart = (
        build_horizontal_bar_chart(
            sales_by_state,
            x_col="revenue",
            y_col=state_label_col,
            title="Top States by Revenue",
            max_rows=10,
        )
        if state_label_col
        else '<div class="chart-empty">No state data available</div>'
    )

    velocity_chart = build_horizontal_bar_chart(
        velocity_df,
        x_col="revenue_per_day",
        y_col="product_name",
        title="Sales Velocity",
        max_rows=10,
    )

    daily_chart = build_vertical_bar_chart(
        heatmap_df,
        x_col="weekday",
        y_col="revenue",
        title="Revenue by Weekday",
    )

    sales_tab_html = build_sales_tab(context)

    keyword_section = build_table_section(
        "Keyword Control Center",
        keyword_actions,
        max_rows=25,
        section_id="keywords",
    )

    bid_recs_section = build_table_section(
        "Keyword Bid Recommendations",
        bid_recs,
        max_rows=25,
        section_id="actions",
    )

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        {get_styles()}
    </head>

    <body>
        <main class="dashboard">

            {navbar}

            <div id="executive-tab" class="dashboard-tab active-tab">
                {hero}
                {ai_section}
                {sales_attention}
                {comparison_section}
            </div>

            <div id="sales-tab" class="dashboard-tab" style="display:none;">
                {sales_tab_html}
            </div>

            <div id="ppc-tab" class="dashboard-tab" style="display:none;">
                {ppc_product_inventory}
            </div>

            <div id="products-tab" class="dashboard-tab" style="display:none;">
                {ppc_product_inventory}
            </div>

            <div id="inventory-tab" class="dashboard-tab" style="display:none;">
                {ppc_product_inventory}
            </div>

            <div id="keywords-tab" class="dashboard-tab" style="display:none;">
                {keyword_section}
            </div>

            <div id="actions-tab" class="dashboard-tab" style="display:none;">
                {bid_recs_section}
            </div>

        </main>
    </body>
    </html>
    """

    return html