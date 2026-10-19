"""Amazon US reporting-date normalization helpers."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd


AMAZON_US_TIMEZONE = ZoneInfo("America/Los_Angeles")


def amazon_us_reporting_date(value: object) -> str | None:
    """Return the Seller Central calendar date for an ISO timestamp."""
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        return parsed.date().isoformat()
    return parsed.tz_convert(AMAZON_US_TIMEZONE).date().isoformat()


def amazon_us_reporting_dates(values: pd.Series) -> pd.Series:
    """Vectorized Pacific reporting dates as timezone-naive timestamps."""
    def normalize(value: object) -> pd.Timestamp:
        try:
            parsed = pd.Timestamp(value)
        except (TypeError, ValueError):
            return pd.NaT
        if pd.isna(parsed):
            return pd.NaT
        if parsed.tzinfo is None:
            return parsed.normalize()
        return parsed.tz_convert(AMAZON_US_TIMEZONE).tz_localize(None).normalize()

    return values.map(normalize)
