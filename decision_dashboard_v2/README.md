# Hasten Decision Center v2

Run locally:

```bash
python app.py
```

Open `http://127.0.0.1:5051`.

This app reads the existing SQLite database without modifying it. It intentionally
keeps ordered sales, net sales, net proceeds, and profit as separate concepts.

## Database model

Production uses one canonical SQLite database on a Railway persistent volume:

```text
LITET_DB_PATH=/data/litet.db
HASTEN_DECISION_DB=/data/litet.db
```

The second setting puts the intervention log in the same database. Local apps use
an automatically refreshed read-only cache when offline; that cache is disposable
and is not another source of truth.

Production command:

```bash
gunicorn --bind 0.0.0.0:$PORT decision_dashboard_v2.wsgi:app
```

## V2 decision model

- **Executive:** ranks exceptions by actual performance and shows parent-level market context.
- **Products:** analyzes pack/color/size/ASIN results from Amazon actuals, then adds separately labeled Helium 10 parent estimates.
- **PPC:** keeps targeting keywords and customer search terms distinct. High ACoS alone never triggers a bid reduction; missing organic-rank evidence is shown explicitly.
- **Decisions:** opens product-specific pricing cases with contribution per unit, break-even incremental units, required lift, and a measurement plan.

The curated competitor snapshot is in `competitor_data.py`. Refresh its values from
Helium 10 on the capture cadence before using competitor trends for a live decision.
Competitor estimates are never added to the company P&L.
