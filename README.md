# Hasten Litet Analytics

This repository contains the Litet/Has10 analytics pipeline and several user
interfaces built at different stages of the project.

## Applications

| Application | Entry point | Status |
| --- | --- | --- |
| Decision Dashboard v2 | `decision_dashboard_v2/` | Railway deployment target |
| Native Streamlit dashboard | `dashboard.py`, `native_dashboard/` | Local/legacy |
| Flask dashboard | `flask_app.py`, `flask_dashboard/` | Local/legacy |
| Sales chatbot | `app.py` | Local/legacy |
| Prime Day analysis | `prime_day_app.py` | Local utility |

The older application modules remain at the repository root for now because
they share imports and have an established test suite. Moving them before
introducing package boundaries would create unnecessary deployment risk.

## Data pipeline

The raw Seller Central import currently starts in the companion
`litet_inventory/scripts/update_all.py` pipeline. Analytics mart builders,
migrations, and seeds live in this repository:

- `materialize_stage1.py`, `stage1_mart.py`
- `seed_stage2_cogs.py`, `stage2_cogs.py`
- `materialize_stage3.py`, `stage3_ppc.py`
- `migrations/` and `seeds/`

Run the existing ETL and synchronize the verified database to Railway with:

```bash
python scripts/update_and_sync.py
```

See `docs/architecture/DEPLOYMENT.md` for configuration and recovery details.

## Repository layout

```text
decision_dashboard_v2/  deployable Decision Dashboard
flask_dashboard/        previous Flask dashboard
html_dashboard/         shared/previous HTML dashboard code
native_dashboard/       Streamlit dashboard
scripts/                deployment and synchronization commands
migrations/             SQLite analytics schemas
seeds/                  controlled analytics seed data
tests/                  shared regression suite
docs/architecture/      architecture and deployment documentation
docs/status/            historical implementation reports
notebooks/              exploratory analysis
```
