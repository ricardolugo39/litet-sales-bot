# Flask + Tabler Migration Status

## Result

The presentation layer is available as a separate Flask application while the
existing Streamlit application remains unchanged and runnable.

Run the Flask version with:

```bash
python flask_app.py
```

Then open `http://127.0.0.1:5050/executive?brand=all`.

## Ported

- Tabler base layout with a single native sidebar, header, responsive cards,
  tables, and mobile navigation.
- Deep-linkable brand scope on every route using `?brand=litet`,
  `?brand=has10`, or `?brand=all`.
- Executive, including six KPI cards, the shared Plotly sales-trend figure,
  operating controls, and an explicit button-triggered AI summary.
- Sales & Products.
- Profitability.
- Fees & Reconciliation.
- Advertising.
- Cash & Settlements.
- Inventory & Costs.
- Alerts & Actions.
- Data Quality.

The routes call the Stage 4 `native_dashboard.data_service` directly. Shared
Plotly builders were moved to `native_dashboard/charts.py` so the Flask and
Streamlit presentations use the same chart logic.

## Presentation safeguards

- The sidebar is one Tabler navigation component; no layered or duplicated
  navigation is used.
- KPI cards use a responsive CSS grid, `min-width: 0`, fluid number sizing,
  tabular numerals, normal wrapping, and `overflow-wrap` protection.
- The layout fixture explicitly includes `$168,803.93`, `-$12,456.78`, and
  long labels/product names.
- Litet uses cobalt, Has10 uses coral, and All uses aubergine throughout the
  sidebar selection, controls, KPI accents, buttons, and Plotly figures.

## Verification

Automated tests render all nine routes in all three brand scopes. They verify
query-parameter persistence, one active navigation item, long and negative KPI
values, invalid-scope handling, and that the AI call happens only after the
explicit POST action.

Page-by-page rendered-markup inspection:

| Page | Status | Active nav | KPI cards | Data tables | Charts |
| --- | ---: | ---: | ---: | ---: | ---: |
| Executive | 200 | 1 | 6 | 0 | 1 |
| Sales & Products | 200 | 1 | 4 | 1 | 2 |
| Profitability | 200 | 1 | 4 | 2 | 0 |
| Fees & Reconciliation | 200 | 1 | 5 | 2 | 0 |
| Advertising | 200 | 1 | 5 | 4 | 0 |
| Cash & Settlements | 200 | 1 | 3 | 1 | 0 |
| Inventory & Costs | 200 | 1 | 4 | 1 | 0 |
| Alerts & Actions | 200 | 1 | 3 | 3 | 0 |
| Data Quality | 200 | 1 | 0 | 3 | 0 |

Test result: **49 passed**.

The workspace browser runtime had no available browser, so screenshots could
not be captured. The visual-equivalent inspection used fully rendered Flask
HTML with a deterministic fixture sized to the observed content extremes.
After the configured OneDrive SQLite file finished hydrating, a temporary local
copy was used to render all nine `All`-scope routes against real data; every
route returned HTTP 200. A screenshot pass can be repeated when a browser
runtime is available.

## Assumptions and deployment

- This remains a single-user internal tool, so no authentication or user
  session infrastructure was added.
- Tabler, Plotly.js, and the selected web fonts load from pinned public CDNs.
  Vendor these assets before deploying into an offline environment.
- `flask_app.py` uses Flask's development server for local validation. A
  production deployment should use a WSGI server and the existing database
  path/environment configuration.
- No marts, calculations, reconciliation logic, COGS logic, PPC logic, or
  underlying query definitions were changed.
