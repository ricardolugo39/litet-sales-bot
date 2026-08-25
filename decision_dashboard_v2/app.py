import os
import sqlite3
import gzip
import hmac
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from flask import Flask, after_this_request, redirect, render_template, request, send_file, url_for

try:
    from .analytics import (action_queue, advertising_detail, brand_split, cost_diagnosis, executive_actions, family_diagnostics, keyword_opportunities, keyword_playbook,
                            market_context, monthly_trend, overview, periods, ppc_periods, pnl_statement, seasonality_matrix,
                            ppc_coverage, ppc_decisions, ppc_organic_trend, pricing_case, product_diagnostics)
    from .interventions import recent_interventions, record_pricing_case
except ImportError:  # Supports `python app.py` from this directory.
    from analytics import (action_queue, advertising_detail, brand_split, cost_diagnosis, executive_actions, family_diagnostics, keyword_opportunities, keyword_playbook,
                           market_context, monthly_trend, overview, periods, ppc_periods, pnl_statement, seasonality_matrix,
                           ppc_coverage, ppc_decisions, ppc_organic_trend, pricing_case, product_diagnostics)
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


def _preserve_interventions(candidate, current):
    """Carry the Railway-owned decision log into a newly uploaded snapshot."""
    if not current.exists():
        return
    with sqlite3.connect(candidate) as conn:
        conn.execute("ATTACH DATABASE ? AS current_db", (str(current),))
        exists = conn.execute(
            "SELECT 1 FROM current_db.sqlite_master WHERE type='table' AND name='interventions'"
        ).fetchone()
        if exists:
            # Qualify `main`: an unqualified DROP can resolve to the attached DB
            # when the uploaded snapshot has no intervention table yet.
            conn.execute("DROP TABLE IF EXISTS main.interventions")
            conn.execute("CREATE TABLE main.interventions AS SELECT * FROM current_db.interventions")
        conn.commit()

@app.get("/health")
def health():
    """Railway health check that also verifies the analytics database."""
    db_path = os.getenv("LITET_DB_PATH")
    if not db_path:
        return {"status": "error", "reason": "LITET_DB_PATH is not configured"}, 503
    if not Path(db_path).exists():
        # The first deploy must stay reachable long enough to receive its
        # initial authenticated snapshot.
        return {"status": "initializing", "reason": "awaiting initial database upload"}
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("SELECT 1 FROM business_traffic LIMIT 1").fetchone()
    except (OSError, sqlite3.Error) as exc:
        return {"status": "error", "reason": str(exc)}, 503
    return {"status": "ok"}


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
        _preserve_interventions(candidate, db_path)
        os.replace(candidate, db_path)
        return {"status": "ok", "bytes": db_path.stat().st_size}
    except (OSError, sqlite3.Error, ValueError) as exc:
        candidate.unlink(missing_ok=True)
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

@app.template_filter("compact_money")
def compact_money(value):
    if value is None: return "—"
    sign="-" if value < 0 else ""; value=abs(value)
    return f"{sign}${value/1000:.1f}k" if value >= 1000 else f"{sign}${value:,.0f}"

@app.template_filter("number")
def number(value): return "—" if value is None else f"{value:,.0f}"

@app.template_filter("percent")
def percent(value): return "—" if value is None else f"{value:.1%}"

def selection():
    choices=ppc_periods(); selected=request.args.get("period")
    if selected: start,end=selected.split("|")
    else:
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
    ctx.update(actions=actions,prior_period=prior,trend=monthly_trend(brand),pnl=pnl_statement(start,end,brand),costs=cost_diagnosis(start,end,brand),brands=brand_split(start,end),market=market_context(brand),ceo_action=executive_actions(start,end,brand,actions))
    return render_template("dashboard.html",**ctx)

@app.get("/products")
def products():
    ctx=common("products"); start,end,brand=ctx["start"],ctx["end"],ctx["brand"]
    ctx.update(families=family_diagnostics(start,end,brand),products=product_diagnostics(start,end,brand),market=market_context(brand),seasonality=seasonality_matrix(brand))
    return render_template("dashboard.html",**ctx)

@app.get("/ppc")
def ppc():
    ctx=common("ppc"); start,end,brand=ctx["start"],ctx["end"],ctx["brand"]
    ctx.update(ppc_rows=ppc_decisions(start,end,brand),advertising=advertising_detail(start,end,brand),organic_trend=ppc_organic_trend(brand),playbook=keyword_playbook(start,end,brand),keyword_opportunities=keyword_opportunities(start,end,brand))
    return render_template("dashboard.html",**ctx)

@app.get("/decisions")
def decisions():
    ctx=common("decisions"); actions,prior=action_queue(ctx["start"],ctx["end"],ctx["brand"]); ctx.update(actions=actions,prior_period=prior,interventions=recent_interventions())
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
