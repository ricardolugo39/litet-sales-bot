# Helium 10 daily market automation

## Schedule

Run daily at **06:00 America/Bogota**. Has10 receives hot-season priority, but
the same run must always refresh Litet.

## Automation instruction

Refresh both Helium 10 market snapshots for the US marketplace:

- Has10 parent ASIN `B0CHMVPCC7`.
- Litet parent ASIN `B0DSCFD253`, compared with the competitor parent ASINs in
  `MARKET_SNAPSHOTS`.

Analyze each brand's tracked phrases in
`decision_dashboard_v2/competitor_data.py` with the connected Helium 10 MCP.
Validate that every tracked phrase returns a row; preserve the existing organic
and peer ranks unless a multi-ASIN comparison refresh returns replacements.
Update search volume, 30-day search-volume trend, suggested bid, and capture
date. Run the Decision Dashboard tests, commit only the Helium snapshot changes,
push `main`, wait for Railway, and verify `/health` plus both brand PPC pages. If
Helium 10, GitHub, tests, or Railway fails, do not publish a partial snapshot;
report the failure in this thread.

## Seasonal review

Review Has10's daily cadence after football season. Litet remains included in
the scheduled refresh; a weekly cadence for both brands is sufficient outside
the seasonal demand window.
