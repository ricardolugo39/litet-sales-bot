import json
import pandas as pd


def clean_for_streamlit(data):
    if isinstance(data, pd.DataFrame):
        df = data.copy()
    elif isinstance(data, list):
        df = pd.DataFrame(data)
    elif isinstance(data, dict):
        rows = []

        for key, value in data.items():
            if isinstance(value, dict):
                row = {"section": key}
                row.update(value)
                rows.append(row)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        row = {"section": key}
                        row.update(item)
                        rows.append(row)
                    else:
                        rows.append({"section": key, "value": item})
            else:
                rows.append({"metric": key, "value": value})

        df = pd.DataFrame(rows)
    else:
        df = pd.DataFrame([{"value": data}])

    for col in df.columns:
        df[col] = df[col].apply(
            lambda x: json.dumps(x, default=str) if isinstance(x, (dict, list)) else x
        )

    return df


def safe_get(data, key, default=0):
    if isinstance(data, dict):
        return data.get(key, default)
    return default


def format_money(value):
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"


def format_number(value):
    try:
        return f"{float(value):,.0f}"
    except Exception:
        return "0"


def format_pct(value):
    try:
        return f"{float(value) * 100:,.1f}%"
    except Exception:
        return "0.0%"


def to_numeric_sum(df, col):
    if df is None or df.empty or col not in df.columns:
        return 0

    return pd.to_numeric(df[col], errors="coerce").fillna(0).sum()