import os
import sqlite3
import gzip
import hmac
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from flask import Flask, after_this_request, redirect, render_template, request, send_file, url_for

if __package__:
    from .helium_store import save_snapshot
else:
    from helium_store import save_snapshot

if __package__:
    from .analytics import (action_queue, advertising_detail, brand_split, cost_diagnosis, executive_actions, executive_diagnosis, family_diagnostics, keyword_opportunities, keyword_playbook,
                            market_context, monthly_trend, overview, periods, ppc_periods, pnl_statement, seasonality_matrix,
                            ppc_coverage, ppc_decisions, ppc_organic_trend, pricing_case, product_diagnostics, product_portfolio)
    from .interventions import recent_interventions, record_pricing_case
else:  # Supports `python app.py` from this directory.
    from analytics import (action_queue, advertising_detail, brand_split, cost_diagnosis, executive_actions, executive_diagnosis, family_diagnostics, keyword_opportunities, keyword_playbook,
                           market_context, monthly_trend, overview, periods, ppc_periods, pnl_statement, seasonality_matrix,
                           ppc_coverage, ppc_decisions, ppc_organic_trend, pricing_case, product_diagnostics, product_portfolio)
    from interventions import recent_interventions, record_pricing_case

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024

REQUIRED_TABLES = {
    "orders", "business_traffic", "asin_economics", "inventory_snapshots",
    "dim_product", "cogs_ledger", "ppc_fact_clean",
}


def _admin_authorized():
    configured = os.getenv("ADMIN_UPLOAD_TOKEN", "")
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    return bool(configured) and hmac.compare_digest(configured, supplied)


def _validate_database(path):
    with sqlite3.connect(path) as conn:
        result = conn.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise ValueError(f"Database is missing required tables: {', '.join(missing)}")


def _preserve_railway_tables(candidate, current):
    """Carry Railway-owned state into a newly uploaded analytics snapshot."""
    if not current.exists():
        return
    with sqlite3.connect(candidate) as conn:
        conn.execute("ATTACH DATABASE ? AS current_db", (str(current),))
        for table in ("interventions", "helium_snapshots"):
            schema = conn.execute(
                "SELECT sql FROM current_db.sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if schema:
                # Table names are fixed above; never interpolate request data.
                conn.execute(f"DROP TABLE IF EXISTS main.{table}")
                conn.execute(schema[0])
                conn.execute(f"INSERT INTO main.{table} SELECT * FROM current_db.{table}")
                indexes = conn.execute(
                    "SELECT sql FROM current_db.sqlite_master "
                    "WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                    (table,),
                ).fetchall()
                for index in indexes:
                    conn.execute(index[0])
        conn.commit()

@app.get("/health")
def health():
    """Railway health check that also verifies the analytics database."""
    db_path = os.getenv("LITET_DB_PATH")
    if not db_path:
        # Keep the first deployment reachable so its volume and variables can
        # be configured through Railway before the initial snapshot upload.
        return {"status": "initializing", "reason": "database path is not configured"}
    if not Path(db_path).exists():
        # The first deploy must stay reachable long enough to receive its
        # initial authenticated snapshot.
        return {"status": "initializing", "reason": "awaiting initial database upload"}
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("SELECT 1 FROM business_traffic LIMIT 1").fetchone()
            try:
                row = conn.execute(
                    "SELECT captured_at FROM helium_snapshots "
                    "ORDER BY captured_at DESC, id DESC LIMIT 1"
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
    except (OSError, sqlite3.Error) as exc:
        return {"status": "error", "reason": str(exc)}, 503
    helium = {"status": "awaiting_first_snapshot"}
    if row:
        captured = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - captured).total_seconds() / 3600
        helium = {
            "status": "stale" if age_hours > 48 else "ok",
            "captured_at": row[0],
            "age_hours": round(age_hours, 1),
        }
    return {"status": "ok", "helium10": helium}


@app.get("/admin")
def admin():
    """Browser UI for authenticated database synchronization."""
    return render_template("admin.html")


@app.put("/admin/database")
def upload_database():
    """Replace the canonical DB with an authenticated gzip-compressed snapshot."""
    if not _admin_authorized():
        return {"status": "error", "reason": "unauthorized"}, 401
    db_path = Path(os.environ["LITET_DB_PATH"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="litet-upload-", suffix=".db", dir=db_path.parent)
    os.close(fd)
    candidate = Path(temporary)
    try:
        with gzip.GzipFile(fileobj=request.stream, mode="rb") as source, candidate.open("wb") as target:
            shutil.copyfileobj(source, target)
        _validate_database(candidate)
        _preserve_railway_tables(candidate, db_path)
        os.replace(candidate, db_path)
        return {"status": "ok", "bytes": db_path.stat().st_size}
    except (OSError, sqlite3.Error, ValueError) as exc:
        candidate.unlink(missing_ok=True)
        return {"status": "error", "reason": str(exc)}, 400


@app.put("/admin/helium-snapshot")
def upload_helium_snapshot():
    """Atomically publish one complete Litet + Has10 Helium 10 snapshot."""
    if not _admin_authorized():
        return {"status": "error", "reason": "unauthorized"}, 401
    try:
        payload = request.get_json(force=False)
        snapshot_id = save_snapshot(os.environ["LITET_DB_PATH"], payload)
        return {
            "status": "ok",
            "snapshot_id": snapshot_id,
            "captured_at": payload["captured_at"],
            "brands": sorted(payload["brands"]),
        }
    except (KeyError, OSError, sqlite3.Error, TypeError, ValueError) as exc:
        return {"status": "error", "reason": str(exc)}, 400


@app.get("/admin/database")
def download_database():
    """Download a compressed canonical snapshot for offline read-only use."""
    if not _admin_authorized():
        return {"status": "error", "reason": "unauthorized"}, 401
    db_path = Path(os.environ["LITET_DB_PATH"])
    if not db_path.exists():
        return {"status": "error", "reason": "database not found"}, 404
    fd, temporary = tempfile.mkstemp(prefix="litet-download-", suffix=".db.gz")
    os.close(fd)
    archive = Path(temporary)
    with db_path.open("rb") as source, gzip.open(archive, "wb") as target:
        shutil.copyfileobj(source, target)

    @after_this_request
    def cleanup(response):
        archive.unlink(missing_ok=True)
        return response

    return send_file(archive, mimetype="application/gzip", download_name="litet.db.gz")

@app.template_filter("money")
def money(value):
    if value is None: return "—"
    return f"-${abs(value):,.0f}" if value < 0 else f"${value:,.0f}"

@app.template_filter("money2")
def money2(value):
    if value is None: return "—"
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"

@app.template_filter("compact_money")
def compact_money(value):
    if value is None: return "—"
    sign="-" if value < 0 else ""; value=abs(value)
    return f"{sign}${value/1000:.1f}k" if value >= 1000 else f"{sign}${value:,.0f}"

@app.template_filter("number")
def number(value): return "—" if value is None else f"{value:,.0f}"

@app.template_filter("percent")
def percent(value):
    try: return "—" if value is None else f"{float(value):.1%}"
    except (TypeError, ValueError): return "—"

def selection():
    choices=ppc_periods(); selected=request.args.get("period")
    selected_parts=selected.split("|") if selected else []
    try:
        start,end=selected_parts
        if date.fromisoformat(start)>date.fromisoformat(end): raise ValueError
    except (TypeError, ValueError):
        aligned=next((p for p in choices if p.get("group") == "Monthly periods" and p["has_economics"]),choices[0]); start,end=aligned["period_start"],aligned["period_end"]
    brand=request.args.get("brand","Litet")
    if brand not in {"All","Litet","Has10"}: brand="Litet"
    return choices,start,end,brand

def common(page):
    choices,start,end,brand=selection()
    return dict(page=page,periods=choices,start=start,end=end,brand=brand,metrics=overview(start,end,brand),coverage=ppc_coverage(start,end,brand))

@app.get("/")
def executive():
    ctx=common("executive"); start,end,brand=ctx["start"],ctx["end"],ctx["brand"]; actions,prior=action_queue(start,end,brand)
    ceo_action=executive_actions(start,end,brand,actions)
    ctx.update(actions=actions,prior_period=prior,trend=monthly_trend(brand),pnl=pnl_statement(start,end,brand),costs=cost_diagnosis(start,end,brand),brands=brand_split(start,end),market=market_context(brand),ceo_action=ceo_action,diagnosis=executive_diagnosis(start,end,brand,ceo_action))
    return render_template("dashboard.html",**ctx)

@app.get("/products")
def products():
    ctx=common("products"); start,end,brand=ctx["start"],ctx["end"],ctx["brand"]
    portfolio=product_portfolio(start,end,brand)
    ctx.update(families=family_diagnostics(start,end,brand),portfolio=portfolio,
               products=portfolio["products"],market=market_context(brand),seasonality=seasonality_matrix(brand))
    return render_template("dashboard.html",**ctx)

@app.get("/ppc")
def ppc():
    ctx=common("ppc"); start,end,brand=ctx["start"],ctx["end"],ctx["brand"]
    ctx.update(ppc_rows=ppc_decisions(start,end,brand),advertising=advertising_detail(start,end,brand),organic_trend=ppc_organic_trend(brand),playbook=keyword_playbook(start,end,brand),keyword_opportunities=keyword_opportunities(start,end,brand))
    return render_template("dashboard.html",**ctx)

@app.get("/decisions")
def decisions():
    ctx=common("decisions"); portfolio=product_portfolio(ctx["start"],ctx["end"],ctx["brand"])
    cases=[row for row in portfolio["products"]
           if row["is_ppc_hero"] or row["is_ppc_test_candidate"] or row["status"] in {"Act now","Watch"}]
    cases.sort(key=lambda row: (0 if row["is_ppc_hero"] else 1 if row["is_ppc_test_candidate"] else 2,
                                row["status_rank"], -(row["ordered_sales"] or 0)))
    ctx.update(actions=cases[:6],portfolio=portfolio,prior_period=portfolio["prior_period"],interventions=recent_interventions())
    return render_template("dashboard.html",**ctx)

@app.get("/decisions/pricing")
def pricing():
    ctx=common("pricing"); asin=request.args.get("asin"); ctx.update(case=pricing_case(ctx["start"],ctx["end"],ctx["brand"],asin),seasonality=seasonality_matrix(ctx["brand"],asin) if asin else None)
    return render_template("dashboard.html",**ctx)

@app.post("/decisions/pricing/approve")
def approve_pricing():
    record_pricing_case({"brand":request.form["brand"],"asin":request.form["asin"],
      "old_value":float(request.form["old_value"]),"new_value":float(request.form["new_value"]),
      "period_start":request.form["period_start"],"period_end":request.form["period_end"],
      "objective":"Validate incremental contribution; no Amazon price change is executed by this app.",
      "required_lift":float(request.form["required_lift"]),"review_date":(date.today()+timedelta(days=7)).isoformat()})
    return redirect(url_for("decisions",brand=request.form["brand"],period=f"{request.form['period_start']}|{request.form['period_end']}"))

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5051")), debug=False)
