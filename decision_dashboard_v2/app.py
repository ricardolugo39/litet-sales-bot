import os
import secrets
import sqlite3
import gzip
import hmac
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "decision_dashboard_v2"
from flask import Flask, after_this_request, redirect, render_template, request, send_file, url_for, session, abort

if __package__:
    from .helium_store import save_snapshot
else:
    from helium_store import save_snapshot

if __package__:
    from .analytics import (action_queue, advertising_detail, brand_split, cost_diagnosis, executive_actions, executive_diagnosis, family_diagnostics, keyword_opportunities, keyword_playbook,
                            market_context, monthly_trend, overview, periods, ppc_periods, pnl_statement, seasonality_matrix,
                            ppc_change_impact, ppc_coverage, ppc_decisions, ppc_organic_trend, price_change_performance, price_change_traffic_diagnostic, pricing_case, prime_big_deals_performance, product_diagnostics, product_portfolio)
    from .interventions import (recent_interventions, record_action_proposal,
                                record_adjustment_proposal, record_pricing_case,
                                update_intervention_status)
else:  # Supports `python app.py` from this directory.
    from analytics import (action_queue, advertising_detail, brand_split, cost_diagnosis, executive_actions, executive_diagnosis, family_diagnostics, keyword_opportunities, keyword_playbook,
                           market_context, monthly_trend, overview, periods, ppc_periods, pnl_statement, seasonality_matrix,
                           ppc_change_impact, ppc_coverage, ppc_decisions, ppc_organic_trend, price_change_performance, price_change_traffic_diagnostic, pricing_case, prime_big_deals_performance, product_diagnostics, product_portfolio)
    from interventions import (recent_interventions, record_action_proposal,
                               record_adjustment_proposal, record_pricing_case,
                               update_intervention_status)

from decision_dashboard_v2.ppc_evidence import (
    STATE_TABLES, build_workspace, get_evaluation, save_policy,
    evaluate_candidate, save_evaluation, decision_card, current_evaluations,
)

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SESSION_SECRET") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024


@app.after_request
def prevent_stale_dashboard(response):
    """Operational pages must reflect the latest DB and workflow state."""
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

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
        for table in ("interventions", "helium_snapshots", *STATE_TABLES):
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
def number(value):
    if value is None: return "—"
    numeric=float(value)
    if numeric.is_integer(): return f"{numeric:,.0f}"
    return f"{numeric:,.2f}".rstrip("0").rstrip(".")

@app.template_filter("percent")
def percent(value):
    try: return "—" if value is None else f"{float(value):.1%}"
    except (TypeError, ValueError): return "—"

@app.template_filter("rank_class")
def rank_class(value):
    if value is None: return "muted"
    return "good" if value <= 10 else "warn" if value <= 20 else "bad"

@app.template_filter("rank_label")
def rank_label(value):
    return "Not ranked" if value is None else f"#{value:g}"

def selection():
    choices=ppc_periods(); selected=request.args.get("period")
    selected_parts=selected.split("|") if selected else []
    try:
        start,end=selected_parts
        if date.fromisoformat(start)>date.fromisoformat(end): raise ValueError
    except (TypeError, ValueError):
        aligned=next((p for p in choices if p.get("group") == "Monthly periods" and p["has_economics"]),choices[0]); start,end=aligned["period_start"],aligned["period_end"]
    else:
        exact=next((p for p in choices
                    if p["period_start"]==start and p["period_end"]==end),None)
        if exact is None:
            # Old bookmarked MTD cutoffs should advance to the consolidated
            # calendar-month choice after newer slices complete that month.
            month_choice=next((p for p in choices
                               if p.get("group")=="Monthly periods"
                               and p["period_start"][:7]==start[:7]),None)
            if month_choice:
                start,end=month_choice["period_start"],month_choice["period_end"]
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
    # Do not display retired PPC heuristics beside the evidence-based workspace.
    ad_words = ("ppc", "bid", "keyword", "acos", "exact", "advertis", "generic traffic")
    ceo_action["steps"] = [step for step in ceo_action.get("steps", [])
                           if not step.get("proposal") and not any(word in step.get("action", "").lower() for word in ad_words)]
    ceo_action["steps"].insert(0, {"action": "Review current advertising evidence",
                                 "why": "Use attribution-mature results, total contribution and traffic dependence before selecting a documented bid experiment."})
    ceo_action["headline"] = "Evaluate advertising changes using company contribution, traffic and documented tests."
    ceo_action["productive_terms"] = []
    selected_metrics=ctx["metrics"]
    pnl_start,pnl_end=start,end
    if not selected_metrics.get("net_sales"):
        settled=next((p for p in ctx["periods"]
                      if p.get("group") == "Monthly periods"
                      and p.get("has_economics")),None)
        if settled:
            pnl_start,pnl_end=settled["period_start"],settled["period_end"]
            ctx["metrics"]=overview(pnl_start,pnl_end,brand)
    ctx.update(actions=actions,prior_period=prior,trend=monthly_trend(brand),
               pnl=pnl_statement(pnl_start,pnl_end,brand),
               costs=cost_diagnosis(pnl_start,pnl_end,brand),
               brands=brand_split(pnl_start,pnl_end),market=market_context(brand),
               ceo_action=ceo_action,
               diagnosis=executive_diagnosis(pnl_start,pnl_end,brand,ceo_action))
    return render_template("dashboard.html",**ctx)

@app.get("/products")
def products():
    ctx=common("products"); start,end,brand=ctx["start"],ctx["end"],ctx["brand"]
    portfolio=product_portfolio(start,end,brand)
    ctx.update(families=family_diagnostics(start,end,brand),portfolio=portfolio,
               products=portfolio["products"],market=market_context(brand),seasonality=seasonality_matrix(brand))
    return render_template("dashboard.html",**ctx)

def _evidence_dates(values):
    try:
        start = date.fromisoformat(values.get("start", ""))
        end = date.fromisoformat(values.get("end", ""))
    except (ValueError, TypeError):
        raise ValueError("Choose valid reporting dates") from None
    if start > end:
        raise ValueError("The start date must not follow the end date")
    return start.isoformat(), end.isoformat()


def _evidence_review(page):
    brand = request.args.get("brand", "Litet")
    if brand not in {"Litet", "Has10", "All"}:
        return "Select a valid brand", 400
    if request.args.get("start") or request.args.get("end"):
        try:
            start, end = _evidence_dates(request.args)
        except ValueError as exc:
            return str(exc), 400
    else:
        _, start, end, brand = selection()
    from decision_dashboard_v2.analytics import database_path
    review = build_workspace(database_path(), start, end, brand)
    session.setdefault("evidence_csrf", secrets.token_urlsafe(32))
    evaluation = get_evaluation(brand, request.args.get("evaluation"))
    saved = current_evaluations(review, brand)
    for target in review["targets"]:
        selected = evaluation if evaluation and evaluation["result"]["target_key"] == target["key"] else saved.get(target["key"])
        target["card"] = decision_card(review, target, selected)
    return render_template("ppc_workspace.html", page=page, brand=brand,
                           start=start, end=end, review=review,
                           csrf_token=session["evidence_csrf"], evaluation=evaluation)


@app.get("/ppc")
def ppc():
    return _evidence_review("ppc")


def _evidence_redirect(message=None, evaluation=None, error=False):
    values = dict(brand=request.form.get("brand", "Litet"),
                  start=request.form.get("start"), end=request.form.get("end"))
    if message:
        values["evidence_error" if error else "evidence_saved"] = message
    if evaluation:
        values["evaluation"] = evaluation
    return redirect(url_for("ppc", **values))


def _check_evidence_post():
    supplied = request.form.get("csrf_token", "")
    if not supplied or not hmac.compare_digest(supplied, session.get("evidence_csrf", "")):
        abort(400, "Reload the review page before submitting this form")
    if request.form.get("brand") not in {"Litet", "Has10"}:
        raise ValueError("Select one brand")
    start, end = _evidence_dates(request.form)
    from decision_dashboard_v2.analytics import database_path
    return build_workspace(database_path(), start, end, request.form["brand"])


@app.post("/ppc/evidence/settings")
def evidence_settings():
    try:
        _check_evidence_post()
        save_policy(request.form["brand"], request.form)
    except ValueError as exc:
        return _evidence_redirect(str(exc), error=True)
    return _evidence_redirect("A new settings version was saved. Previous evaluations must be rerun.")


@app.post("/ppc/evidence/evaluate")
def evidence_evaluate():
    try:
        review = _check_evidence_post()
        if request.form.get("fingerprint") != review["fingerprint"]:
            raise ValueError("Data or settings changed. Reload before evaluating")
        result = evaluate_candidate(review, request.form)
        evaluation_id = save_evaluation(request.form["brand"], review, request.form, result)
    except ValueError as exc:
        return _evidence_redirect(str(exc), error=True)
    return _evidence_redirect("Evaluation saved; no Amazon settings changed.", evaluation=evaluation_id)


@app.post("/ppc/evidence/propose")
def evidence_propose():
    try:
        review = _check_evidence_post()
        record = get_evaluation(request.form["brand"], request.form.get("evaluation_id"))
        if not record or record["fingerprint"] != review["fingerprint"] or record["policy_id"] != review["policy"]["id"] or record["model_version"] != review["model_version"]:
            raise ValueError("The evaluation is missing or stale; re-evaluate current data")
        result = evaluate_candidate(review, record["payload"])
        if not result["eligible"]:
            raise ValueError("Proposal blocked: " + "; ".join(result["blockers"]))
        target = next(t for t in review["targets"] if t["key"] == result["target_key"])
        evidence = {"evaluation_id": record["id"], "model_version": review["model_version"], "policy_id": review["policy"]["id"], "fingerprint": review["fingerprint"], "spend": target["mature"]["spend"], "clicks": target["mature"]["clicks"], "orders": target["mature"]["ad_orders"], "ad_sales": target["mature"]["ad_sales"], "acos": target["mature"]["acos"]}
        record_action_proposal({"brand": target["brand"], "campaign_name": target["campaign_name"], "ad_group_name": target["ad_group_name"], "entity_type": "target", "entity_name": target["target"], "match_type": target["match_type"], "action_type": "evidence_bid_test", "old_value": result["inputs"]["current_bid"], "new_value": result["inputs"]["candidate_bid"], "period_start": review["mature_start"], "period_end": review["mature_end"], "objective": f"Evidence {record['id']} / policy {review['policy']['id']}: " + result["inputs"]["hypothesis"], "baseline": evidence})
    except ValueError as exc:
        return _evidence_redirect(str(exc), error=True)
    return _evidence_redirect("Test proposal recorded for human review. It has not been applied to Amazon.", evaluation=record["id"])


@app.post("/ppc/evidence/status/<int:intervention_id>")
def evidence_status(intervention_id):
    try:
        review = _check_evidence_post()
        row = next((i for i in review["interventions"] if i["audit_id"] == intervention_id), None)
        if not row:
            raise ValueError("Decision record not found for this brand")
        status = request.form.get("status")
        transitions = {"proposed": {"approved", "dismissed"}, "approved": {"executed", "dismissed"}, "executed": {"monitoring", "completed", "reverted"}, "monitoring": {"completed", "reverted"}}
        if status not in transitions.get(row["status"], set()):
            raise ValueError("This status transition is not available")
        if status == "approved" and row.get("action_type") != "evidence_bid_test":
            raise ValueError("Legacy proposals require a fresh evidence evaluation before approval")
        if status == "approved" and row.get("action_type") == "evidence_bid_test":
            import json
            baseline = json.loads(row.get("baseline_json") or "{}")
            record = get_evaluation(request.form["brand"], baseline.get("evaluation_id"))
            if not record or record["fingerprint"] != review["fingerprint"] or record["policy_id"] != review["policy"]["id"] or record["model_version"] != review["model_version"]:
                raise ValueError("Evidence changed since this proposal; create a fresh evaluation before approval")
            if not evaluate_candidate(review, record["payload"])["eligible"]:
                raise ValueError("The proposal no longer meets your declared guardrails")
        if status == "executed" and request.form.get("amazon_confirmed") != "yes":
            raise ValueError("Confirm the actual Amazon change before recording execution")
        update_intervention_status(intervention_id, status)
    except ValueError as exc:
        return _evidence_redirect(str(exc), error=True)
    return _evidence_redirect("Decision status recorded. The app did not change Amazon.")


@app.get("/events/prime-big-deals-2026")
def prime_big_deals():
    return render_template("prime_big_deals.html",
                           page="prime_big_deals",
                           event=prime_big_deals_performance())


@app.get("/sales-tree")
def sales_tree():
    fields = ("before_start", "before_end", "after_start", "after_end")
    values = {key: request.args.get(key, "").strip() for key in fields}
    comparison = None
    error = None
    if any(values.values()):
        try:
            if not all(values.values()):
                raise ValueError("Enter all four dates.")
            bs, be, start, end = (date.fromisoformat(values[key]) for key in fields)
            if bs > be or start > end:
                raise ValueError("Each start date must be on or before its end date.")
            if be >= start:
                raise ValueError("The baseline must end before the comparison period begins.")
            from zoneinfo import ZoneInfo
            last_day = datetime.now(ZoneInfo("America/Los_Angeles")).date() - timedelta(days=1)
            if end > last_day:
                raise ValueError("Choose completed Pacific calendar days only.")
            if (be-bs).days >= 93 or (end-start).days >= 93:
                raise ValueError("Each date range can contain up to 93 days.")
            comparison = (bs, be, start, end)
        except ValueError as exc:
            error = str(exc) or "Enter valid dates."
    if error:
        return render_template("sales_tree.html", error=error, values=values), 400
    result = price_change_performance(14, False, "weekday4", comparison=comparison)
    before, after = result["before"], result["after"]
    def metric(label, left, right, money=False, lower_better=False, detail=""):
        delta = right-left if left is not None and right is not None else None
        pct = delta/left if delta is not None and left is not None and left > 0 else None
        direction = ("neutral" if delta is None or abs(delta)<1e-9 else
                     "bad" if (delta > 0 if lower_better else delta < 0) else "good")
        return {"label": label, "before":left, "after":right, "delta":delta,
                "pct":pct, "money":money, "direction":direction, "detail":detail}
    def per_day(row, key):
        return row[key]/row["days"] if row["days"] else None
    ad_complete = bool(result["ppc_cutoff"] and result["after_dates"]
                       and result["ppc_cutoff"] >= max(result["after_dates"]))
    profit = metric("Contribution after ads / day", before["contribution_after_ads_per_day"] if ad_complete else None,
                    after["contribution_after_ads_per_day"] if ad_complete else None, True)
    gross = metric("Contribution before ads / day", before["contribution_per_day"], after["contribution_per_day"], True)
    ads = metric("Advertising spend / day", per_day(before,"ad_spend") if ad_complete else None,
                 per_day(after,"ad_spend") if ad_complete else None, True, True)
    revenue = metric("Revenue / day",before["revenue_per_day"],after["revenue_per_day"],True)
    def costs(row):
        return row["revenue_per_day"]-row["contribution_per_day"] if row["revenue_per_day"] is not None and row["contribution_per_day"] is not None else None
    costs_metric = metric("Product costs + Amazon fees / day",costs(before),costs(after),True,True)
    packs = metric("Packs sold / day",before["packs_per_day"],after["packs_per_day"])
    price = metric("Realized price / pack",before["price_per_pack"],after["price_per_pack"],True)
    pack_metrics = []
    for p in result["pack_rows"]:
        pack_metrics.append({"name":p["label"], "volume":metric("Packs / day",p["before"]["packs_per_day"],p["after"]["packs_per_day"]),
                             "contribution":metric("Contribution before ads / day",p["before"]["contribution_per_day"],p["after"]["contribution_per_day"],True),
                             "before_count":p["before"]["raw_packs"], "after_count":p["after"]["raw_packs"]})
    bt, at = before["traffic"], after["traffic"]
    traffic = metric("Sessions / day",bt["sessions"]/before["days"] if bt and before["days"] else None,
                     at["sessions"]/after["days"] if at and after["days"] else None)
    conversion = metric("Units ordered / session",bt["units_per_session"] if bt else None,at["units_per_session"] if at else None)
    traffic_diagnostic = None
    if comparison is None and (not bt or not at):
        traffic_diagnostic = result.get("alternate_traffic") or price_change_traffic_diagnostic()
        if traffic_diagnostic:
            d = traffic_diagnostic
            traffic = metric("Sessions / day", d["before"]["sessions"]/d.get("before_days",7), d["after"]["sessions"]/d.get("after_days",7))
            conversion = metric("Units ordered / session",d["before"]["units_per_session"],d["after"]["units_per_session"])
    clicks = metric("Ad clicks / day",per_day(before,"ad_clicks") if ad_complete else None,per_day(after,"ad_clicks") if ad_complete else None)
    cpc = metric("Cost / ad click",before["ad_spend"]/before["ad_clicks"] if ad_complete and before["ad_clicks"] else None,
                 after["ad_spend"]/after["ad_clicks"] if ad_complete and after["ad_clicks"] else None,True,True)
    drivers = []
    for m, impact in ((gross, gross["delta"]), (ads, -ads["delta"] if ads["delta"] is not None else None)):
        if impact is not None and impact < -1e-9:
            drivers.append({"label":m["label"],"impact":impact})
    drivers.sort(key=lambda x:x["impact"])
    percentage_flags = [m for m in [profit, gross, ads, costs_metric, packs, price, revenue, clicks, cpc,
                                   *([] if traffic_diagnostic else [traffic, conversion]),
                                   *[x["volume"] | {"label": x["name"] + " packs / day"} for x in pack_metrics]]
                        if m["pct"] is not None and m["direction"] == "bad"]
    percentage_flags.sort(key=lambda m: abs(m["pct"]), reverse=True)
    if not comparison:
        values = {"before_start": result["before_dates"][0] if result["before_dates"] else "",
                  "before_end": result["before_dates"][-1] if result["before_dates"] else "",
                  "after_start":result["after_dates"][0] if result["after_dates"] else "",
                  "after_end":result["after_dates"][-1] if result["after_dates"] else ""}
    return render_template("sales_tree.html", analysis=result, values=values, custom=bool(comparison),
                           profit=profit,gross=gross,ads=ads,revenue=revenue,costs=costs_metric,packs=packs,price=price,
                           pack_metrics=pack_metrics,traffic=traffic,conversion=conversion,clicks=clicks,cpc=cpc,
                           drivers=drivers,ad_complete=ad_complete,percentage_flags=percentage_flags[:3],traffic_diagnostic=traffic_diagnostic)


@app.get("/price-change")
def price_change():
    try:
        window = int(request.args.get("window", "14"))
    except ValueError:
        window = 14
    include_transition = request.args.get("transition", "exclude") == "include"
    baseline_mode = request.args.get("baseline", "weekday4")
    return render_template(
        "price_change.html", page="price_change",
        analysis=price_change_performance(window, include_transition, baseline_mode),
    )

@app.get("/decisions")
def decisions():
    return _evidence_review("decisions")


def _mark_interventions_in_workflow(playbook,interventions):
    active_keys={(i.get("campaign_name"),i.get("ad_group_name"),i.get("entity_name"),i.get("match_type"))
                 for i in interventions if i.get("status") in {"proposed","approved","executed","monitoring"}}
    if playbook:
        for target in playbook["targets"]:
            key=(target.get("campaign_name"),target.get("ad_group_name"),target.get("target"),target.get("match_type"))
            if key in active_keys:
                target["is_actionable"]=False
                target["in_workflow"]=True


def _interventions_for_brand(interventions,brand):
    if brand == "All":
        return interventions
    return [item for item in interventions if item.get("brand") == brand]


def _intervention_rollup(interventions):
    """Show one current result per exact target; keep superseded runs as history."""
    result_statuses={"executed","monitoring","completed","reverted"}
    current=[]
    history=[]
    seen=set()
    for item in interventions:
        if item.get("status") not in result_statuses:
            continue
        key=(item.get("brand"),item.get("campaign_name"),item.get("ad_group_name"),
             item.get("entity_name"),item.get("match_type"))
        if key in seen:
            history.append(item)
        else:
            seen.add(key)
            current.append(item)
    summary={"working":0,"not_working":0,"watch":0,"waiting":0}
    for item in current:
        if not (item.get("post") or {}).get("days"):
            summary["waiting"]+=1
        elif item.get("result_class")=="good":
            summary["working"]+=1
        elif item.get("result_class")=="bad":
            summary["not_working"]+=1
        else:
            summary["watch"]+=1
    return current,history,summary

@app.get("/decisions/pricing")
def pricing():
    ctx=common("pricing"); asin=request.args.get("asin"); ctx.update(case=pricing_case(ctx["start"],ctx["end"],ctx["brand"],asin),seasonality=seasonality_matrix(ctx["brand"],asin) if asin else None)
    return render_template("dashboard.html",**ctx)

@app.post("/decisions/pricing/approve")
def approve_pricing():
    if request.form.get("price_verified") != "true":
        return ("A verified current Amazon price is required before a pricing case can be queued.", 400)
    record_pricing_case({"brand":request.form["brand"],"asin":request.form["asin"],
      "old_value":float(request.form["old_value"]),"new_value":float(request.form["new_value"]),
      "period_start":request.form["period_start"],"period_end":request.form["period_end"],
      "objective":"Validate incremental contribution; no Amazon price change is executed by this app.",
      "required_lift":float(request.form["required_lift"]),"review_date":(date.today()+timedelta(days=7)).isoformat()})
    return redirect(url_for("decisions",brand=request.form["brand"],period=f"{request.form['period_start']}|{request.form['period_end']}"))

@app.post("/decisions/proposals")
def create_proposal():
    return redirect(url_for("ppc", brand=request.form.get("brand", "Litet"),
                            evidence_error="Fixed-percentage proposals are retired. Evaluate a documented candidate against holding in the evidence workspace."))


@app.post("/decisions/interventions/<int:intervention_id>/status")
def intervention_status(intervention_id):
    from decision_dashboard_v2.interventions import connect as decision_connection
    with decision_connection() as conn:
        row = conn.execute("SELECT action_type FROM interventions WHERE rowid=?", [intervention_id]).fetchone()
    if row and row["action_type"] == "evidence_bid_test":
        return redirect(url_for("ppc", brand=request.form.get("brand", "Litet"), evidence_error="Use the evidence-reviewed controls for this proposal."))
    if request.form.get("status") == "approved":
        return redirect(url_for("ppc", brand=request.form.get("brand", "Litet"), evidence_error="Legacy proposals require a fresh evidence evaluation before approval."))
    update_intervention_status(intervention_id,request.form["status"])
    return redirect(url_for("decisions",brand=request.form.get("brand","Litet"),period=request.form.get("period","")))


@app.post("/decisions/interventions/<int:intervention_id>/adjust")
def adjust_intervention(intervention_id):
    return redirect(url_for("ppc", brand=request.form.get("brand", "Litet"),
                            evidence_error="Evaluate a documented replacement candidate in the evidence workspace before proposing a bid adjustment."))

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5051")), debug=False)
