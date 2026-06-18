import pandas as pd


def get_date_col(df, possible_cols):
    for col in possible_cols:
        if col in df.columns:
            return col
    return None


def normalize_datetime_col(df, col):
    df[col] = (
        pd.to_datetime(df[col], errors="coerce", utc=True)
        .dt.tz_localize(None)
    )
    return df


def get_period_dates(df, date_col, period):
    d = df.copy()
    d = normalize_datetime_col(d, date_col)

    max_date = d[date_col].max()

    if pd.isna(max_date):
        max_date = pd.Timestamp.today().normalize()

    if period == "LAST_7_DAYS":
        start_date = max_date - pd.Timedelta(days=7)
    elif period == "LAST_30_DAYS":
        start_date = max_date - pd.Timedelta(days=30)
    elif period == "MTD":
        start_date = pd.Timestamp(year=max_date.year, month=max_date.month, day=1)
    elif period == "YTD":
        start_date = pd.Timestamp(year=max_date.year, month=1, day=1)
    else:
        start_date = max_date - pd.Timedelta(days=30)

    return start_date, max_date


def filter_df_by_period(df, period, date_candidates):
    d = df.copy()
    date_col = get_date_col(d, date_candidates)

    if not date_col:
        return d, None, None, None

    d = normalize_datetime_col(d, date_col)
    start_date, max_date = get_period_dates(d, date_col, period)

    d = d[d[date_col] >= start_date].copy()

    return d, date_col, start_date, max_date