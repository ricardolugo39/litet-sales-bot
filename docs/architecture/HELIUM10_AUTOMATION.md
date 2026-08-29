# Helium 10 production refresh

## Runtime

Run one scheduled Codex automation every day at **06:00 America/Bogota**. The
automation uses the user's OAuth-connected Helium 10 MCP; Helium 10 does not
provide an API key for Railway. Railway stores and serves the resulting data,
but it does not call Helium 10 directly.

Configuration is versioned in `decision_dashboard_v2/helium_config.json`.
Competitor ASINs are discovery seeds. Resolve them through Helium 10 and use
only values returned by MCP. Never copy spreadsheet metrics into a snapshot.

## Required run

1. Read `decision_dashboard_v2/helium_config.json`.
2. Query the US marketplace for both parents: Litet `B0DSCFD253` and Has10
   `B0CHMVPCC7`.
3. Resolve each usable competitor seed with Helium 10. Record the ASIN scope
   returned by MCP as `parent`; do not infer parent/child status from an export.
4. Use listing comparison data for metrics. Map `monthly_sales` to `sales`,
   `monthly_revenue` to `revenue`, `review_count` to `reviews`,
   `reviews_rating` to `rating`, and retain price, LQS, top-10 keyword metrics,
   and sales change under their snapshot contract names.
5. Run `analyze_keywords` for every configured phrase. Run multi-ASIN keyword
   comparison for organic `rank` and competitive `peer_rank`. Match by
   normalized phrase, never response order.
6. Build one JSON document. Missing MCP metrics may be JSON `null`; fabricated
   or downloaded values are prohibited.
7. Publish only after both brands and every configured phrase are present:

   ```bash
   python scripts/publish_helium_snapshot.py /tmp/helium10-snapshot.json
   ```

8. Verify `GET /health`: `helium10.status` must be `ok` and its capture time
   must match the run. Check both brand PPC pages.

If either brand, a configured keyword, validation, publishing, or health check
fails, do not publish. Railway continues serving the last successful snapshot.

## Snapshot contract

```json
{
  "captured_at": "2026-08-29T11:00:00Z",
  "marketplace": "US",
  "brands": {
    "Litet": {"parent_asin": "B0DSCFD253", "own": {}, "competitors": [], "keywords": []},
    "Has10": {"parent_asin": "B0CHMVPCC7", "own": {}, "competitors": [], "keywords": []}
  }
}
```

Each `own` object contains `sales`, `revenue`, `price`, `reviews`, `rating`,
`lqs`, `top10_keywords`, `top10_volume`, and `sales_change`.

Each competitor contains `name`, resolved `parent`, configured `segment`,
`price`, `sales`, `reviews`, `rating`, `top10_keywords`, and `sales_change`.

Each keyword contains `phrase`, `search_volume`, `volume_trend_30d_pct`,
`suggested_bid_usd`, `rank`, `peer_rank`, and `competitors`. It may include
`sponsored_rank` when MCP supplies it.

## Storage behavior

`PUT /admin/helium-snapshot` authenticates with `ADMIN_UPLOAD_TOKEN`, validates
that Litet and Has10 are complete, and appends to canonical SQLite history. The
normal Amazon database upload preserves this history. The dashboard uses the
curated Python snapshot only until the first successful DB snapshot exists.
