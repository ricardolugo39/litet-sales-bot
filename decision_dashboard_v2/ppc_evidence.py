"""Auditable PPC evidence and conditional candidate evaluation.

No fixed click/ACoS thresholds or percentage bid instructions. Descriptive
facts, assumed statistical settings, documented scenarios, and causal claims
are kept distinct. No Amazon mutation occurs here.
"""
import hashlib
import json
import math
import os
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .reporting_dates import amazon_us_reporting_date

MODEL_VERSION = "ppc-evidence-1"
DEFAULTS = {
    "attribution_days": 7,  # The loaded report's 7 Day attribution definition.
    "prior_lookback_days": 28,
    "prior_clicks": 10.0,  # Explicit, unconfirmed modeling assumption.
    "interval_pct": 80.0,
    "max_loss_probability": None,
    "profit_reserve_per_order": None,
    "min_traffic_retention": None,
}
IDENTITY = ("campaign_name", "ad_group_name", "target", "match_type")
STATE_TABLES = ("ppc_evidence_policies", "ppc_evidence_evaluations")


def state_path():
    return os.getenv("HASTEN_DECISION_DB", str(Path(__file__).with_name("decision_log.db")))


def schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ppc_evidence_policies (
      id INTEGER PRIMARY KEY, brand TEXT NOT NULL, created_at TEXT NOT NULL,
      model_version TEXT NOT NULL, payload_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ppc_evidence_evaluations (
      id INTEGER PRIMARY KEY, brand TEXT NOT NULL, created_at TEXT NOT NULL,
      policy_id INTEGER, fingerprint TEXT NOT NULL, model_version TEXT NOT NULL,
      payload_json TEXT NOT NULL, result_json TEXT NOT NULL
    );
    """)


def get_policy(brand):
    policy = {**DEFAULTS, "id": None, "confirmed": False, "created_at": None}
    path = Path(state_path())
    if not path.exists():
        return policy
    with sqlite3.connect(path) as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='ppc_evidence_policies'").fetchone()
        row = conn.execute("SELECT id,created_at,payload_json FROM ppc_evidence_policies WHERE brand=? ORDER BY id DESC LIMIT 1", (brand,)).fetchone() if exists else None
    if row:
        policy.update(json.loads(row[2]), id=row[0], created_at=row[1], confirmed=True)
    return policy


def finite(value, label, minimum=0, maximum=None):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{label} must be a number") from None
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise ValueError(f"{label} is outside its allowed range")
    return result


def save_policy(brand, data):
    if brand not in {"Litet", "Has10"}:
        raise ValueError("Select one brand before saving settings")
    values = {
        "attribution_days": int(finite(data.get("attribution_days"), "Attribution days", 7, 90)),
        "prior_lookback_days": int(finite(data.get("prior_lookback_days"), "Prior lookback days", 1, 730)),
        "prior_clicks": finite(data.get("prior_clicks"), "Prior strength", .01, 10000),
        "interval_pct": finite(data.get("interval_pct"), "Uncertainty interval", 1, 99.9),
        "max_loss_probability": finite(data.get("max_loss_probability"), "Acceptable loss probability", 0, 100) / 100,
        "profit_reserve_per_order": finite(data.get("profit_reserve_per_order"), "Profit reserve per order", 0),
        "min_traffic_retention": finite(data.get("min_traffic_retention"), "Minimum traffic retention", 0, 100) / 100,
    }
    if str(values["attribution_days"]) != str(data.get("attribution_days")):
        raise ValueError("Attribution days must be an integer")
    if str(values["prior_lookback_days"]) != str(data.get("prior_lookback_days")):
        raise ValueError("Prior lookback days must be an integer")
    expected = str(data.get("policy_id") or "")
    with sqlite3.connect(state_path()) as conn:
        schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT id FROM ppc_evidence_policies WHERE brand=? ORDER BY id DESC LIMIT 1", (brand,)).fetchone()
        if expected != (str(row[0]) if row else ""):
            raise ValueError("Settings changed in another view. Reload before saving")
        conn.execute("INSERT INTO ppc_evidence_policies (brand,created_at,model_version,payload_json) VALUES (?,?,?,?)", (brand, datetime.now(ZoneInfo("UTC")).isoformat(), MODEL_VERSION, json.dumps(values)))
        conn.commit()


def quantile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lo = int(position)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (position - lo)


def total(rows):
    values = {key: sum(float(row.get(key) or 0) for row in rows) for key in ("impressions", "clicks", "spend", "ad_orders", "ad_sales", "other_sku_sales")}
    values["cpc"] = values["spend"] / values["clicks"] if values["clicks"] else None
    values["acos"] = values["spend"] / values["ad_sales"] if values["ad_sales"] else None
    return values


def rate_model(clicks, orders, peer_clicks, peer_orders, policy, seed):
    """Gamma-Poisson orders/click, not a binary conversion probability."""
    if peer_clicks <= 0 or peer_orders <= 0:
        return {"available": False, "reason": "No positive, earlier peer order-rate evidence; no fallback prior invented"}
    prior_rate = peer_orders / peer_clicks
    alpha = orders + policy["prior_clicks"] * prior_rate
    beta = clicks + policy["prior_clicks"]
    rng = random.Random(seed)
    samples = [rng.gammavariate(alpha, 1 / beta) for _ in range(2000)]
    tail = (1 - policy["interval_pct"] / 100) / 2
    return {"available": True, "mean": alpha / beta, "low": quantile(samples, tail), "high": quantile(samples, 1 - tail), "alpha": alpha, "beta": beta, "peer_rate": prior_rate, "prior_clicks": policy["prior_clicks"], "measured_clicks": clicks}


def _table(conn, name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def company_evidence(conn, brand, start, end):
    """Orders and ad spend on matching Pacific dates; no traffic interpolation."""
    if end < start:
        return None
    clause, args = ("1=1", []) if brand == "All" else ("p.canonical_brand=?", [brand])
    rows = conn.execute(f'''SELECT o."amazon-order-id" order_id,o.asin,o."purchase-date" timestamp,
       CAST(o.quantity AS REAL) packs,
       CAST(o."item-price" AS REAL)-COALESCE(CAST(o."item-promotion-discount" AS REAL),0) sales
       FROM orders o JOIN dim_product p ON p.asin=o.asin AND p.is_current=1
       WHERE {clause} AND CAST(o.quantity AS REAL)>0
       AND COALESCE(o."order-status",'') NOT IN ('Cancelled','Canceled')
       AND COALESCE(o."item-status",'') NOT IN ('Cancelled','Canceled')''', args).fetchall()
    selected = [r for r in rows if amazon_us_reporting_date(r["timestamp"]) and start <= amazon_us_reporting_date(r["timestamp"]) <= end]
    ad_clause, ad_args = ("1=1", []) if brand == "All" else ("brand=?", [brand])
    ad = conn.execute(f"SELECT SUM(spend) spend,COUNT(DISTINCT report_date) days FROM ppc_fact_clean WHERE {ad_clause} AND report_date BETWEEN ? AND ?", [*ad_args, start, end]).fetchone()
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    sales = sum(r["sales"] or 0 for r in selected)
    spend = ad["spend"] or 0
    result = {"daily_sales": {}, "start": start, "end": end, "days": days, "sales": sales, "packs": sum(r["packs"] for r in selected), "spend": spend, "ad_days": ad["days"], "tacos": spend / sales if sales and ad["days"] == days else None, "sales_per_day": sales / days, "spend_per_day": spend / days if ad["days"] == days else None, "sessions": None, "session_reason": "Compatible cumulative traffic boundaries are unavailable", "contribution": None, "contribution_per_day": None, "exact_fee_share": None, "conversion": None}
    for row in selected:
        day = amazon_us_reporting_date(row["timestamp"])
        result["daily_sales"][day] = result["daily_sales"].get(day, 0) + (row["sales"] or 0)
    if _table(conn, "sales_profitability") and _table(conn, "cogs_ledger"):
        fee_rows = conn.execute("""SELECT order_id,asin,ABS(SUM(amazon_fees)) fee,
          MIN(CASE WHEN fee_status='exact_order_fee_allocated' AND amazon_fees IS NOT NULL THEN 1 ELSE 0 END) ready
          FROM sales_profitability GROUP BY order_id,asin""").fetchall()
        fees = {(r["order_id"],r["asin"]): r for r in fee_rows}
        ledger = [dict(r) for r in conn.execute("SELECT asin,unit_cogs,effective_start,effective_end FROM cogs_ledger ORDER BY effective_start DESC")]
        fba = {}
        if _table(conn, "asin_economics"):
            for row in conn.execute("""SELECT asin,period_start,period_end,
                ABS(SUM(fba_fulfillment_fees))/NULLIF(SUM(net_units_sold),0) rate
                FROM asin_economics WHERE period_type='monthly' AND period_end<?
                GROUP BY asin,period_start,period_end ORDER BY period_end DESC""", [start]):
                if row["asin"] not in fba and row["rate"] is not None and row["rate"] >= 0:
                    fba[row["asin"]] = row["rate"]
        grouped = {}
        for row in selected:
            key = (row["order_id"],row["asin"])
            grouped.setdefault(key, []).append(row)
        contribution = 0; exact_revenue = 0; estimated_revenue = 0; missing = 0
        for key, entries in grouped.items():
            revenue = sum(r["sales"] or 0 for r in entries)
            packs = sum(r["packs"] or 0 for r in entries)
            costs = []
            for entry in entries:
                day = amazon_us_reporting_date(entry["timestamp"])
                cost = next((r["unit_cogs"] for r in ledger if r["asin"] == key[1] and r["effective_start"] <= day and (not r["effective_end"] or day < r["effective_end"])), None)
                costs.append(cost * entry["packs"] if cost is not None else None)
            fee = fees.get(key)
            amount = fee["fee"] if fee and fee["ready"] else None
            if amount is not None:
                exact_revenue += revenue
            elif brand == "Litet" and key[1] in fba:
                from .analytics import clothing_referral_fee
                amount = packs * fba[key[1]] + clothing_referral_fee(revenue, packs)[0]
                estimated_revenue += revenue
            if amount is None or any(cost is None for cost in costs):
                missing += 1
            else:
                contribution += revenue - sum(costs) - amount
        result.update(missing_cost_groups=missing, exact_fee_share=exact_revenue/sales if sales else None, estimated_fee_share=estimated_revenue/sales if sales else None,
                      contribution=contribution-spend if not missing and ad["days"] == days and selected else None,
                      before_ads=contribution if not missing and selected else None)
        result["contribution_per_day"] = result["contribution"] / days if result["contribution"] is not None else None
    if _table(conn, "business_traffic") and start[:7] == end[:7]:
        month_start = start[:7] + "-01"
        boundary = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
        def snapshot(day):
            return {r["child_asin"]: dict(r) for r in conn.execute(f"SELECT b.child_asin,b.sessions_total,b.units_ordered FROM business_traffic b JOIN dim_product p ON p.asin=b.child_asin AND p.is_current=1 WHERE {clause} AND b.period_start=? AND b.period_end=?", [*args, month_start, day])}
        ending = snapshot(end)
        beginning = {a: {"sessions_total": 0, "units_ordered": 0} for a in ending} if start == month_start else snapshot(boundary)
        if ending and set(ending) == set(beginning):
            sessions = sum((ending[a]["sessions_total"] or 0) - (beginning[a]["sessions_total"] or 0) for a in ending)
            units = sum((ending[a]["units_ordered"] or 0) - (beginning[a]["units_ordered"] or 0) for a in ending)
            if sessions >= 0 and units >= 0:
                result.update(sessions=sessions, traffic_units=units, conversion=units / sessions if sessions else None, session_reason="Difference of compatible cumulative snapshots; no daily interpolation")
    return result


def build_workspace(path, start, end, brand, today=None):
    today = today or datetime.now(ZoneInfo("America/Los_Angeles")).date()
    policy = get_policy(brand)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        clause, args = ("1=1", []) if brand == "All" else ("brand=?", [brand])
        freshness = dict(conn.execute(f"SELECT MAX(report_date) latest,MAX(imported_at) imported FROM ppc_fact_clean WHERE {clause}", args).fetchone())
        complete = min(end, (today - timedelta(days=1)).isoformat(), freshness["latest"] or end)
        # A source date proves report availability, not Seller Central completeness.
        cutoff = min((today - timedelta(days=policy["attribution_days"] + 1)).isoformat(), (date.fromisoformat(freshness["latest"]) - timedelta(days=policy["attribution_days"])).isoformat()) if freshness["latest"] else (today - timedelta(days=policy["attribution_days"] + 1)).isoformat()
        mature_end = min(complete, cutoff)
        prior_end = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(ppc_fact_clean)")}
        extra = ",other_sku_sales" if "other_sku_sales" in cols else ",NULL AS other_sku_sales"
        facts = [dict(r) for r in conn.execute(f"SELECT report_date,brand,campaign_name,ad_group_name,target,match_type,impressions,clicks,spend,ad_orders,ad_sales{extra} FROM ppc_fact_clean WHERE {clause} AND report_date<=?", [*args, complete])]
        groups = {}
        for row in facts:
            if row["report_date"] >= start:
                key = (row["brand"], *(row[k] for k in IDENTITY))
                groups.setdefault(key, []).append(row)
        totals = total([r for r in facts if start <= r["report_date"] <= complete])
        targets = []
        for key, rows in groups.items():
            target = {"brand": key[0], **dict(zip(IDENTITY, key[1:])), "selected": total(rows)}
            mature = total([r for r in rows if r["report_date"] <= mature_end])
            target["mature"] = mature
            target["recent"] = total([r for r in rows if r["report_date"] > mature_end])
            # Earlier same-match-type peers, same brand; no future look-ahead.
            prior_start = (date.fromisoformat(min(prior_end, cutoff)) - timedelta(days=policy["prior_lookback_days"] - 1)).isoformat()
            peer = total([r for r in facts if r["report_date"] >= prior_start and r["brand"] == target["brand"] and r["match_type"] == target["match_type"] and r["report_date"] <= min(prior_end, cutoff) and tuple(r[k] for k in IDENTITY) != key[1:]])
            seed = int(hashlib.sha256(repr(key).encode()).hexdigest()[:12], 16)
            target["rate"] = rate_model(mature["clicks"], mature["ad_orders"], peer["clicks"], peer["ad_orders"], policy, seed)
            target["key"] = hashlib.sha256(json.dumps(key).encode()).hexdigest()
            target["click_share"] = target["selected"]["clicks"] / totals["clicks"] if totals["clicks"] else None
            target["impression_share"] = target["selected"]["impressions"] / totals["impressions"] if totals["impressions"] else None
            target["spend_share"] = target["selected"]["spend"] / totals["spend"] if totals["spend"] else None
            target["blockers"] = ["Current bid, budget, placements and bidding strategy are not verified for this analysis", "Purchased-SKU contribution and bid-response evidence are not connected"]
            if not mature["clicks"]:
                target["blockers"].append("No attribution-mature clicks in this selected period")
            target["guidance"] = "Review evidence; no calculated bid change"
            target["is_actionable"] = False
            targets.append(target)
        targets.sort(key=lambda r: (-r["selected"]["spend"], r["key"]))
        leader = max(targets, key=lambda r: r["selected"]["clicks"], default=None)
        if leader and leader["selected"]["clicks"]:
            leader["guidance"] = "Largest recorded paid-traffic source; assess visibility risk before testing"
        queries = [dict(r) for r in conn.execute(f"SELECT campaign_name,ad_group_name,target,match_type,search_term,SUM(clicks) clicks,SUM(spend) spend,SUM(ad_orders) orders,SUM(ad_sales) sales FROM ppc_fact_clean WHERE {clause} AND report_date BETWEEN ? AND ? GROUP BY campaign_name,ad_group_name,target,match_type,search_term ORDER BY SUM(spend) DESC LIMIT 40", [*args, start, complete])]
        interventions = []
        with sqlite3.connect(f"file:{state_path()}?mode=ro", uri=True) if Path(state_path()).exists() else sqlite3.connect(":memory:") as state:
            state.row_factory = sqlite3.Row
            if _table(state, "interventions"):
                ic, ia = ("1=1", []) if brand == "All" else ("brand=?", [brand])
                interventions = [dict(r) for r in state.execute(f"SELECT rowid AS audit_id,* FROM interventions WHERE {ic} ORDER BY created_at DESC,rowid DESC LIMIT 50", ia)]
        company = company_evidence(conn, brand, start, complete) if complete >= start else None
        recent_start = max(start, (date.fromisoformat(mature_end) + timedelta(days=1)).isoformat())
        recent_company = company_evidence(conn, brand, recent_start, complete) if recent_start <= complete else None
        recent_totals = total([r for r in facts if recent_start <= r["report_date"] <= complete])
        for target in targets:
            target["recent_click_share"] = target["recent"]["clicks"] / recent_totals["clicks"] if recent_totals["clicks"] else None
            target["past_changes"] = [i for i in interventions if i.get("brand") == target["brand"] and i.get("campaign_name") == target["campaign_name"] and i.get("ad_group_name") == target["ad_group_name"] and i.get("entity_name") == target["target"] and i.get("match_type") == target["match_type"]]
        market = {"captured_at": None, "keywords": {}}
        if _table(conn, "helium_snapshots"):
            snapshot = conn.execute("SELECT captured_at,payload_json FROM helium_snapshots ORDER BY captured_at DESC,id DESC LIMIT 1").fetchone()
            if snapshot:
                payload = json.loads(snapshot["payload_json"])
                market["captured_at"] = snapshot["captured_at"]
                market["keywords"] = {x.get("phrase", "").lower(): x for x in payload.get("brands", {}).get(brand, {}).get("keywords", [])}
        for target in targets:
            target["market"] = market["keywords"].get((target["target"] or "").lower())

        if company:
            for target in targets:
                daily_clicks = {}
                for row in groups[(target["brand"], *(target[k] for k in IDENTITY))]:
                    daily_clicks[row["report_date"]] = daily_clicks.get(row["report_date"], 0) + (row["clicks"] or 0)
                available_days = sorted({r["report_date"] for r in facts if start <= r["report_date"] <= complete})
                def correlation(days):
                    x = [daily_clicks.get(d, 0) for d in days]
                    y = [company["daily_sales"].get(d, 0) for d in days]
                    if len(x) < 2: return None
                    mx, my = sum(x)/len(x), sum(y)/len(y)
                    xx, yy = sum((a-mx)**2 for a in x), sum((b-my)**2 for b in y)
                    return sum((a-mx)*(b-my) for a,b in zip(x,y)) / math.sqrt(xx*yy) if xx and yy else None
                target["correlation"] = {"days": len(available_days), "coefficient": correlation(available_days)}
                if brand == "Litet":
                    from .analytics import PRICE_CHANGE_PROMOTION_DAYS
                    without_promos = [d for d in available_days if date.fromisoformat(d) not in PRICE_CHANGE_PROMOTION_DAYS]
                    target["correlation"]["promotion_excluded"] = correlation(without_promos)
                    target["correlation"]["promotion_excluded_days"] = len(without_promos)
        mature_days = {r["report_date"] for r in facts if start <= r["report_date"] <= mature_end}
        expected_days = (date.fromisoformat(mature_end) - date.fromisoformat(start)).days + 1 if mature_end >= start else 0
        signature = {"model": MODEL_VERSION, "brand": brand, "start": start, "end": end, "complete": complete, "policy_id": policy["id"], "source": freshness, "company": company, "recent_company": recent_company, "market": market, "queries": queries, "daily_target_facts": facts, "executed_changes": [{k: i.get(k) for k in ("brand", "campaign_name", "ad_group_name", "entity_name", "match_type", "new_value", "executed_at")} for i in interventions if i.get("executed_at")], "targets": [{"key": t["key"], "selected": t["selected"], "mature": t["mature"], "rate": t["rate"]} for t in targets]}
        fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    return {"model_version": MODEL_VERSION, "policy": policy, "fingerprint": fingerprint, "start": start, "end": end, "complete": complete, "mature_end": mature_end, "mature_start": start if expected_days else None, "attribution_cutoff": cutoff, "loaded_mature_days": len(mature_days), "expected_mature_days": expected_days, "totals": totals, "targets": targets, "queries": queries, "company": company, "recent_company": recent_company, "market": market, "recent_start": recent_start, "interventions": interventions, "freshness": freshness, "today": today.isoformat(), "halo_share": totals["other_sku_sales"] / totals["ad_sales"] if totals["ad_sales"] else None}


def evaluate_candidate(workspace, data):
    """Conditional experiment appraisal, never an assertion of optimal bid."""
    target = next((t for t in workspace["targets"] if t["key"] == data.get("target_key")), None)
    if not target:
        raise ValueError("The exact target is not in the selected analysis")
    if not target["rate"]["available"] or not target["mature"]["clicks"]:
        raise ValueError("Attribution-mature target and earlier peer evidence are required")
    p = workspace["policy"]
    if not p["confirmed"]:
        raise ValueError("Confirm modeling assumptions and business guardrails first")
    values = {}
    for field, label in (("current_bid", "Current base bid"), ("candidate_bid", "Candidate base bid"), ("current_clicks_low", "Current clicks low"), ("current_clicks_high", "Current clicks high"), ("candidate_clicks_low", "Candidate clicks low"), ("candidate_clicks_high", "Candidate clicks high"), ("current_cpc_low", "Current CPC low"), ("current_cpc_high", "Current CPC high"), ("candidate_cpc_low", "Candidate CPC low"), ("candidate_cpc_high", "Candidate CPC high"), ("margin_low", "Contribution per attributed order low"), ("margin_high", "Contribution per attributed order high")):
        values[field] = finite(data.get(field), label)
    if not values["current_bid"] or not values["candidate_bid"] or not values["current_clicks_low"]:
        raise ValueError("Bids and current expected traffic must be positive")
    if values["current_bid"] == values["candidate_bid"]:
        raise ValueError("The candidate bid must differ from holding")
    for stem in ["current_clicks", "candidate_clicks", "current_cpc", "candidate_cpc", "margin"]:
        if values[stem + "_low"] > values[stem + "_high"]:
            raise ValueError(f"{stem.replace('_', ' ')} low must not exceed high")
    for field in ["spillover_low", "spillover_high"]:
        values[field] = finite(data.get(field), "Other sales contribution change", -1e9, 1e9)
    if values["spillover_low"] > values["spillover_high"]:
        raise ValueError("Other-sales contribution low must not exceed high")
    for field in ["response_source", "margin_source", "settings_source", "hypothesis", "relevance_note", "spillover_source"]:
        value = str(data.get(field) or "").strip()
        if not value or len(value) > 4000:
            raise ValueError(f"Provide a concise {field.replace('_', ' ')}")
        values[field] = value
    for field in ["settings_date", "response_date", "margin_date"]:
        try:
            value = date.fromisoformat(data.get(field, ""))
        except (ValueError, TypeError):
            raise ValueError(f"Provide a valid {field.replace('_', ' ')}") from None
        if value > date.fromisoformat(workspace["today"]):
            raise ValueError("Evidence dates cannot be in the future")
        values[field] = value.isoformat()
    values["evidence_kind"] = data.get("evidence_kind")
    if values["evidence_kind"] not in {"documented_estimate", "controlled_test", "assumption"}:
        raise ValueError("Choose an evidence type")
    values["controls_confirmed"] = data.get("controls_confirmed") == "yes"
    values["quality_confirmed"] = data.get("quality_confirmed") == "yes"
    rng = random.Random(int(hashlib.sha256((workspace["fingerprint"] + target["key"] + json.dumps(values, sort_keys=True)).encode()).hexdigest()[:12], 16))
    differences, profits, ceilings = [], [], []
    for _ in range(4000):
        rate = rng.gammavariate(target["rate"]["alpha"], 1 / target["rate"]["beta"])
        margin = rng.uniform(values["margin_low"], values["margin_high"])
        current_clicks = rng.uniform(values["current_clicks_low"], values["current_clicks_high"])
        candidate_clicks = rng.uniform(values["candidate_clicks_low"], values["candidate_clicks_high"])
        current_cpc = rng.uniform(values["current_cpc_low"], values["current_cpc_high"])
        candidate_cpc = rng.uniform(values["candidate_cpc_low"], values["candidate_cpc_high"])
        differences.append(candidate_clicks * (rate * margin - candidate_cpc) - current_clicks * (rate * margin - current_cpc) + rng.uniform(values["spillover_low"], values["spillover_high"]))
        profits.append(candidate_clicks * (rate * (margin - p["profit_reserve_per_order"]) - candidate_cpc))
        ceilings.append(rate * max(margin - p["profit_reserve_per_order"], 0))
    loss = sum(x <= 0 for x in differences) / len(differences)
    reserve_risk = sum(x < 0 for x in profits) / len(profits)
    retention = values["candidate_clicks_low"] / values["current_clicks_high"]
    blockers = []
    if values["evidence_kind"] == "assumption": blockers.append("Response is an assumption, not documented evidence")
    if values["settings_date"] != workspace["today"]: blockers.append("Current bid/settings have not been reconfirmed today")
    if not values["controls_confirmed"]: blockers.append("Budget, placement, bidding strategy and product-price comparability are unconfirmed")
    if not values["quality_confirmed"]: blockers.append("Comparable query quality and purchased-product mix are unconfirmed")
    if workspace["complete"] != (date.fromisoformat(workspace["today"]) - timedelta(days=1)).isoformat(): blockers.append("This is a historical or stale reporting window, not a current operational proposal")
    if workspace["loaded_mature_days"] != workspace["expected_mature_days"]: blockers.append("Attribution-mature report-day coverage has gaps")
    if loss > p["max_loss_probability"]: blockers.append("Chance of failing to improve exceeds your declared tolerance")
    if reserve_risk > p["max_loss_probability"]: blockers.append("Profit-reserve risk exceeds your declared tolerance")
    if retention < p["min_traffic_retention"]: blockers.append("Low-traffic scenario breaches your visibility requirement")
    tail = (1 - p["interval_pct"] / 100) / 2
    return {"target_key": target["key"], "interval_pct": p["interval_pct"], "inputs": values, "mean_gain": sum(differences) / len(differences), "gain_low": quantile(differences, tail), "gain_high": quantile(differences, 1-tail), "loss_probability": loss, "reserve_risk": reserve_risk, "traffic_retention_low": retention, "cpc_ceiling_low": quantile(ceilings, tail), "cpc_ceiling_high": quantile(ceilings, 1-tail), "blockers": blockers, "eligible": not blockers, "label": "Meets declared guardrails; candidate for a human-reviewed test" if not blockers else "Not supported for a bid proposal", "model_version": MODEL_VERSION}


def save_evaluation(brand, workspace, data, result):
    with sqlite3.connect(state_path()) as conn:
        schema(conn)
        cur = conn.execute("INSERT INTO ppc_evidence_evaluations (brand,created_at,policy_id,fingerprint,model_version,payload_json,result_json) VALUES (?,?,?,?,?,?,?)", (brand, datetime.now(ZoneInfo("UTC")).isoformat(), workspace["policy"]["id"], workspace["fingerprint"], MODEL_VERSION, json.dumps({k: v for k, v in dict(data).items() if k != "csrf_token"}), json.dumps(result)))
        return cur.lastrowid


def get_evaluation(brand, evaluation_id):
    if not evaluation_id or not Path(state_path()).exists(): return None
    with sqlite3.connect(state_path()) as conn:
        conn.row_factory = sqlite3.Row
        if not _table(conn, "ppc_evidence_evaluations"): return None
        row = conn.execute("SELECT * FROM ppc_evidence_evaluations WHERE id=? AND brand=?", (evaluation_id, brand)).fetchone()
    if not row: return None
    row = dict(row)
    row["result"] = json.loads(row["result_json"])
    row["payload"] = json.loads(row["payload_json"])
    return row
