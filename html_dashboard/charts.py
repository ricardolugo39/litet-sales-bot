import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio


def _clean_money_col(df, col):
    d = df.copy()

    if col not in d.columns:
        return d

    d[col] = (
        d[col]
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
    )

    d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)

    return d


def _short_label(value, max_len=42):
    value = str(value)

    if len(value) <= max_len:
        return value

    return value[:max_len] + "..."


def build_line_chart(df, x_col, y_col, title=""):
    if df is None or df.empty or x_col not in df.columns or y_col not in df.columns:
        return '<div class="chart-empty">No chart data</div>'

    chart_df = df.copy()
    chart_df[x_col] = pd.to_datetime(chart_df[x_col], errors="coerce")
    chart_df[y_col] = pd.to_numeric(chart_df[y_col], errors="coerce").fillna(0)
    chart_df = chart_df.dropna(subset=[x_col]).sort_values(x_col)

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=chart_df[x_col],
            y=chart_df[y_col],
            mode="lines+markers",
            name=y_col,
            line=dict(width=3, color="#2563eb"),
            marker=dict(size=7, color="#2563eb"),
        )
    )

    fig.update_layout(
        height=340,
        margin=dict(l=60, r=40, t=55, b=45),
        template="plotly_white",
        title=title,
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
    )

    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs="cdn",
        config={"displayModeBar": False, "responsive": True},
    )


def build_bar_chart(df, label_col, value_col, title=""):
    if df is None or df.empty or label_col not in df.columns or value_col not in df.columns:
        return '<div class="chart-empty">No chart data</div>'

    chart_df = df.copy().head(10)
    chart_df = _clean_money_col(chart_df, value_col)

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=chart_df[label_col].astype(str),
            y=chart_df[value_col],
            name=value_col,
            marker_color="#2563eb",
        )
    )

    fig.update_layout(
        height=340,
        margin=dict(l=60, r=40, t=55, b=70),
        template="plotly_white",
        title=title,
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=False,
        font=dict(size=12),
    )

    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs=False,
        config={"displayModeBar": False, "responsive": True},
    )


def build_sales_tacos_chart(df):
    if df is None or df.empty:
        return '<div class="chart-empty">No chart data</div>'

    required_cols = ["week_label", "revenue", "tacos_pct"]

    for col in required_cols:
        if col not in df.columns:
            return f'<div class="chart-empty">Missing column: {col}</div>'

    chart_df = df.copy()
    chart_df["revenue"] = pd.to_numeric(chart_df["revenue"], errors="coerce").fillna(0)
    chart_df["tacos_pct"] = pd.to_numeric(chart_df["tacos_pct"], errors="coerce").fillna(0)

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=chart_df["week_label"],
            y=chart_df["revenue"],
            mode="lines+markers",
            name="Revenue",
            yaxis="y",
            line=dict(width=3, color="#2563eb"),
            marker=dict(size=7, color="#2563eb"),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=chart_df["week_label"],
            y=chart_df["tacos_pct"],
            mode="lines+markers",
            name="TACOS %",
            yaxis="y2",
            line=dict(width=3, color="#f97316"),
            marker=dict(size=7, color="#f97316"),
        )
    )

    tacos_min = chart_df["tacos_pct"].min()
    tacos_max = chart_df["tacos_pct"].max()

    fig.update_layout(
        height=360,
        margin=dict(l=70, r=70, t=55, b=55),
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="x unified",
        title=dict(
            text="Revenue + TACOS Trend",
            x=0,
            xanchor="left",
            font=dict(size=18),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
        xaxis=dict(
            title="Week",
            showgrid=True,
            gridcolor="#edf2f7",
        ),
        yaxis=dict(
            title="Revenue $",
            showgrid=True,
            gridcolor="#edf2f7",
            zeroline=False,
            tickprefix="$",
        ),
        yaxis2=dict(
            title="TACOS %",
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False,
            ticksuffix="%",
            range=[
                max(0, tacos_min - 5),
                tacos_max + 5,
            ],
        ),
    )

    return pio.to_html(
        fig,
        include_plotlyjs="cdn",
        full_html=False,
        config={"displayModeBar": False, "responsive": True},
    )


def build_horizontal_bar_chart(
    df,
    x_col,
    y_col,
    title="",
    max_rows=8,
):
    if df is None or df.empty or x_col not in df.columns or y_col not in df.columns:
        return '<div class="chart-empty">No chart data</div>'

    d = df.copy().head(max_rows)
    d = _clean_money_col(d, x_col)
    d = d.sort_values(x_col, ascending=False)

    max_value = d[x_col].max()

    if max_value <= 0:
        return '<div class="chart-empty">No chart data</div>'

    rows_html = ""

    for _, row in d.iterrows():
        label = _short_label(row[y_col], max_len=55)
        value = float(row[x_col])
        width = max((value / max_value) * 100, 3)

        rows_html += f"""
        <div class="custom-bar-row">
            <div class="custom-bar-label">{label}</div>
            <div class="custom-bar-track">
                <div class="custom-bar-fill" style="width:{width}%"></div>
            </div>
            <div class="custom-bar-value">${value:,.0f}</div>
        </div>
        """

    return f"""
    <div class="custom-bar-chart">
        <div class="custom-chart-title">{title}</div>
        {rows_html}
    </div>
    """


def build_vertical_bar_chart(
    df,
    x_col,
    y_col,
    title="",
):
    if df is None or df.empty or x_col not in df.columns or y_col not in df.columns:
        return '<div class="chart-empty">No chart data</div>'

    d = df.copy()
    d = _clean_money_col(d, y_col)

    fig = px.bar(
        d,
        x=x_col,
        y=y_col,
        color_discrete_sequence=["#2563eb"],
    )

    fig.update_layout(
        title=title,
        template="plotly_white",
        height=340,
        margin=dict(l=60, r=30, t=55, b=70),
        xaxis=dict(
            title="",
            tickangle=0,
        ),
        yaxis=dict(
            title="Revenue",
            tickprefix="$",
            showgrid=True,
            gridcolor="#e5e7eb",
            zeroline=False,
        ),
        showlegend=False,
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
    )

    return fig.to_html(
        include_plotlyjs=False,
        full_html=False,
        config={"displayModeBar": False, "responsive": True},
    )


def build_donut_chart(
    df,
    names_col,
    values_col,
    title="",
):
    if df is None or df.empty or names_col not in df.columns or values_col not in df.columns:
        return '<div class="chart-empty">No chart data</div>'

    d = df.copy()
    d = _clean_money_col(d, values_col)

    fig = px.pie(
        d,
        names=names_col,
        values=values_col,
        hole=0.55,
        color_discrete_sequence=["#2563eb", "#f97316", "#16a34a", "#7c3aed"],
    )

    fig.update_traces(
        textposition="inside",
        textinfo="percent",
    )

    fig.update_layout(
        title=title,
        template="plotly_white",
        height=340,
        margin=dict(l=20, r=20, t=55, b=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
        ),
        paper_bgcolor="white",
        font=dict(size=12),
    )

    return fig.to_html(
        include_plotlyjs=False,
        full_html=False,
        config={"displayModeBar": False, "responsive": True},
    )