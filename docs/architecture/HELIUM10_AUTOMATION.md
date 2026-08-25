# Helium 10 hot-season automation

## Schedule

Run daily at **06:00 America/Bogota** during Has10 hot season.

## Automation instruction

Refresh the Has10 Helium 10 market snapshot for US marketplace ASIN
`B0CHMVPCC7`. Analyze the tracked phrases in
`decision_dashboard_v2/competitor_data.py` with the connected Helium 10 MCP.
Validate that every tracked phrase returns a row; preserve the existing organic
and peer ranks unless a multi-ASIN comparison refresh returns replacements.
Update search volume, 30-day search-volume trend, suggested bid, and capture
date. Run the Decision Dashboard tests, commit only the Helium snapshot changes,
push `main`, wait for Railway, and verify `/health` and the Has10 PPC page. If
Helium 10, GitHub, tests, or Railway fails, do not publish a partial snapshot;
report the failure in this thread.

## Seasonal review

Review the daily cadence after football season. A weekly schedule is sufficient
outside the seasonal demand window.
