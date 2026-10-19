from decision_dashboard_v2.reporting_dates import amazon_us_reporting_date


def test_utc_timestamp_rolls_back_to_prior_pacific_date():
    assert amazon_us_reporting_date("2026-10-17T02:44:16+00:00") == "2026-10-16"


def test_dst_offsets_are_selected_by_calendar_date():
    assert amazon_us_reporting_date("2026-01-15T07:30:00+00:00") == "2026-01-14"
    assert amazon_us_reporting_date("2026-07-15T07:30:00+00:00") == "2026-07-15"


def test_date_only_values_are_already_reporting_dates():
    assert amazon_us_reporting_date("2026-10-17") == "2026-10-17"


def test_invalid_or_blank_timestamp_is_missing():
    assert amazon_us_reporting_date("") is None
    assert amazon_us_reporting_date("not-a-date") is None
