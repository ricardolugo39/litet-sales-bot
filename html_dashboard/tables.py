import json


def df_to_html_table(df, max_rows=20):
    if df is None or len(df) == 0:
        return "<p class='empty'>No data available.</p>"

    d = df.copy().head(max_rows)

    for col in d.columns:
        d[col] = d[col].apply(
            lambda x: json.dumps(x, default=str) if isinstance(x, (dict, list)) else x
        )

    return d.to_html(index=False, classes="data-table", border=0)