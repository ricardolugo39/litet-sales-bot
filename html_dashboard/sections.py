from .tables import df_to_html_table


def money(v):
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return "$0.00"


def num(v):
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return "0"


def pct(v):
    try:
        return f"{float(v) * 100:,.1f}%"
    except Exception:
        return "0.0%"


def build_navbar():
    return """
    <nav class="navbar">
        <div class="nav-inner">
            <button class="nav-link active" onclick="showTab('executive-tab', this)">Executive</button>
            <button class="nav-link" onclick="showTab('sales-tab', this)">Sales</button>
            <button class="nav-link" onclick="showTab('ppc-tab', this)">PPC</button>
            <button class="nav-link" onclick="showTab('products-tab', this)">Products</button>
            <button class="nav-link" onclick="showTab('inventory-tab', this)">Inventory</button>
            <button class="nav-link" onclick="showTab('keywords-tab', this)">Keywords</button>
            <button class="nav-link" onclick="showTab('actions-tab', this)">Actions</button>
        </div>

        <script>
            function showTab(tabId, btn) {
                const tabs = document.querySelectorAll('.dashboard-tab');
                tabs.forEach(tab => tab.style.display = 'none');

                const selected = document.getElementById(tabId);
                if (selected) {
                    selected.style.display = 'block';
                }

                const buttons = document.querySelectorAll('.nav-link');
                buttons.forEach(button => button.classList.remove('active'));

                if (btn) {
                    btn.classList.add('active');
                }
            }
        </script>
    </nav>
    """


def format_delta(value):
    if value is None:
        return ""

    try:
        value = float(value)
    except Exception:
        return ""

    direction_class = "positive" if value >= 0 else "negative"
    sign = "+" if value >= 0 else ""

    return f'<div class="kpi-delta {direction_class}">{sign}{value:,.1f}% vs prior</div>'


def format_delta(value):
    if value is None:
        return ""

    try:
        value = float(value)
    except Exception:
        return ""

    direction_class = "positive" if value >= 0 else "negative"
    sign = "+" if value >= 0 else ""

    return f'<div class="kpi-delta {direction_class}">{sign}{value:,.1f}% vs prior</div>'


def build_hero(
    period,
    revenue,
    orders,
    pairs_sold,
    aov,
    tacos=None,
    kpi_comparison=None,
):
    if not isinstance(kpi_comparison, dict):
        kpi_comparison = {}

    metrics = kpi_comparison.get("metrics", {})
    current_dates = kpi_comparison.get("current_dates", {})

    current_start = current_dates.get("start", "")
    current_end = current_dates.get("end", "")

    date_html = ""

    if current_start and current_end:
        date_html = f"""
        <div class="date-range">
            Current: <strong>{current_start} to {current_end}</strong>
        </div>
        """

    return f"""
    <section class="hero section-anchor" id="executive">
        <div class="hero-top">
            <div>
                <h1>LITET Performance Dashboard</h1>

                <p>
                    Internal operating view for sales, PPC,
                    product mix, and inventory risk.
                </p>

                {date_html}
            </div>

            <div class="period-pill">
                Period: {period}
            </div>
        </div>

        <div class="kpi-grid kpi-grid-five">

            <div class="kpi">
                <div class="kpi-label">Revenue</div>
                <div class="kpi-value">{money(revenue)}</div>
                {format_delta(metrics.get("revenue"))}
            </div>

            <div class="kpi">
                <div class="kpi-label">Orders</div>
                <div class="kpi-value">{num(orders)}</div>
                {format_delta(metrics.get("orders"))}
            </div>

            <div class="kpi">
                <div class="kpi-label">Pairs Sold</div>
                <div class="kpi-value">{num(pairs_sold)}</div>
                {format_delta(metrics.get("pairs_sold"))}
            </div>

            <div class="kpi">
                <div class="kpi-label">AOV</div>
                <div class="kpi-value">{money(aov)}</div>
                {format_delta(metrics.get("aov"))}
            </div>

            <div class="kpi">
                <div class="kpi-label">TACOS</div>
                <div class="kpi-value">{pct(tacos)}</div>
                <div class="kpi-delta neutral">Overall PPC efficiency</div>
            </div>

        </div>
    </section>
    """


def build_ai_section(ai_summary):
    if not isinstance(ai_summary, dict):
        ai_summary = {}

    summary = ai_summary.get("summary", "No AI summary available.")
    sales = ai_summary.get("sales", "")
    ppc = ai_summary.get("ppc", "")
    inventory = ai_summary.get("inventory", "")
    actions = ai_summary.get("actions", [])

    if actions:
        actions_html = "<ol class='ai-actions'>"
        for action in actions:
            actions_html += f"<li>{action}</li>"
        actions_html += "</ol>"
    else:
        actions_html = "<p class='empty'>No AI actions available.</p>"

    return f"""
    <section class="card full ai-card">
        <h2>AI Executive Analyst</h2>

        <div class="ai-summary">
            <strong>Summary</strong>
            <p>{summary}</p>
        </div>

        <div class="ai-grid">
            <div class="insight">
                <span class="tag blue">Sales</span><br>
                {sales}
            </div>

            <div class="insight">
                <span class="tag orange">PPC</span><br>
                {ppc}
            </div>

            <div class="insight">
                <span class="tag red">Inventory</span><br>
                {inventory}
            </div>
        </div>

        <div class="ai-summary">
            <strong>Recommended Actions</strong>
            {actions_html}
        </div>
    </section>
    """


def build_sales_and_attention_section(
    trend_chart,
    revenue,
    orders,
    tacos,
    acos,
    critical_inventory,
):
    return f"""
    <section class="main-grid section-anchor" id="sales">
        <div class="card">
            <h2>Sales Trend</h2>
            {trend_chart}
        </div>

        <div class="card">
            <h2>Executive Attention</h2>
            <div class="insight">
                <span class="tag blue">Sales</span><br>
                Revenue for this period is <strong>{money(revenue)}</strong> across <strong>{num(orders)}</strong> orders.
            </div>
            <div class="insight">
                <span class="tag orange">PPC</span><br>
                TACOS is <strong>{pct(tacos)}</strong> and ACOS is <strong>{pct(acos)}</strong>. Review keyword efficiency before scaling spend.
            </div>
            <div class="insight">
                <span class="tag red">Inventory</span><br>
                <strong>{critical_inventory}</strong> SKUs are currently Critical or High risk.
            </div>
        </div>
    </section>
    """


def build_ppc_product_inventory_section(
    ad_spend,
    ad_sales,
    acos,
    roas,
    product_chart,
    inventory_risk,
):
    return f"""
    <section class="three-grid">
        <div class="card section-anchor" id="ppc">
            <h2>PPC Efficiency</h2>
            <div class="mini-grid">
                <div class="mini-kpi"><span>Ad Spend</span><strong>{money(ad_spend)}</strong></div>
                <div class="mini-kpi"><span>Ad Sales</span><strong>{money(ad_sales)}</strong></div>
                <div class="mini-kpi"><span>ACOS</span><strong>{pct(acos)}</strong></div>
                <div class="mini-kpi"><span>ROAS</span><strong>{float(roas):,.2f}x</strong></div>
            </div>
        </div>

        <div class="card section-anchor" id="products">
            <h2>Product Mix</h2>
            {product_chart}
        </div>

        <div class="card section-anchor" id="inventory">
            <h2>Inventory Risk</h2>
            {df_to_html_table(inventory_risk, max_rows=6)}
        </div>
    </section>
    """


def build_table_section(title, df, max_rows=20, section_id=None):
    id_attr = f'id="{section_id}"' if section_id else ""

    return f"""
    <section class="card full section-anchor" {id_attr}>
        <h2>{title}</h2>
        {df_to_html_table(df, max_rows=max_rows)}
    </section>
    """