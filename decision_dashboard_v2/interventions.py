"""Local decision log. Recording a case never changes Amazon."""
import os
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path


def _path():
    return Path(os.getenv("HASTEN_DECISION_DB", Path(__file__).with_name("decision_log.db")))


def connect():
    conn = sqlite3.connect(_path())
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS interventions (
      id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      brand TEXT NOT NULL, asin TEXT NOT NULL, intervention_type TEXT NOT NULL,
      old_value REAL, new_value REAL, period_start TEXT, period_end TEXT,
      objective TEXT, required_lift REAL, review_date TEXT, status TEXT DEFAULT 'planned'
    )""")
    existing = {row[1] for row in conn.execute("PRAGMA table_info(interventions)")}
    additions = {
        "campaign_name": "TEXT", "entity_type": "TEXT", "entity_name": "TEXT",
        "action_type": "TEXT", "baseline_json": "TEXT", "approved_at": "TEXT",
        "executed_at": "TEXT", "review_14_date": "TEXT", "outcome": "TEXT",
        "external_status": "TEXT",
        "ad_group_name": "TEXT", "match_type": "TEXT",
        "amazon_suggested_low": "REAL", "amazon_suggested_high": "REAL",
    }
    for column, kind in additions.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE interventions ADD COLUMN {column} {kind}")
    conn.execute("UPDATE interventions SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL")
    conn.commit()
    return conn


def record_pricing_case(data):
    with connect() as conn:
        cur = conn.execute("""INSERT INTO interventions
          (created_at,brand,asin,intervention_type,old_value,new_value,period_start,period_end,objective,required_lift,review_date)
          VALUES (CURRENT_TIMESTAMP,?,?, 'price_test', ?,?,?,?,?,?,?)""",
          (data["brand"],data["asin"],data["old_value"],data["new_value"],data["period_start"],data["period_end"],data["objective"],data["required_lift"],data["review_date"]))
        return cur.lastrowid


def recent_interventions(limit=20):
    with connect() as conn:
        rows=[dict(r) for r in conn.execute("SELECT * FROM interventions ORDER BY created_at DESC,id DESC LIMIT ?",(limit,))]
    analytics_path=os.getenv("LITET_DB_PATH")
    if analytics_path and Path(analytics_path).exists():
        with sqlite3.connect(analytics_path) as facts:
            facts.row_factory=sqlite3.Row
            for row in rows:
                if row.get("intervention_type")!="ppc_action" or (row.get("ad_group_name") and row.get("match_type")):
                    continue
                match=facts.execute("""SELECT ad_group_name,match_type,SUM(spend) spend
                  FROM ppc_fact_clean WHERE brand=? AND campaign_name=? AND target=?
                  GROUP BY ad_group_name,match_type ORDER BY SUM(spend) DESC LIMIT 1""",
                  (row["brand"],row.get("campaign_name"),row.get("entity_name"))).fetchone()
                if match:
                    row["ad_group_name"]=match["ad_group_name"]
                    row["match_type"]=match["match_type"]
    for row in rows:
        try: row["baseline"]=json.loads(row.get("baseline_json") or "{}")
        except json.JSONDecodeError: row["baseline"]={}
    return rows


def record_action_proposal(data):
    """Record a reviewable action; this never changes Amazon Ads."""
    with connect() as conn:
        duplicate = conn.execute("""SELECT id FROM interventions
          WHERE brand=? AND campaign_name=? AND entity_type=? AND entity_name=?
            AND action_type=? AND status IN ('proposed','approved','executed','monitoring')
          ORDER BY id DESC LIMIT 1""",(
            data["brand"], data["campaign_name"], data["entity_type"],
            data["entity_name"], data["action_type"],
        )).fetchone()
        if duplicate:
            return duplicate[0], False
        today=date.today()
        cur=conn.execute("""INSERT INTO interventions
          (created_at,brand,asin,intervention_type,old_value,new_value,period_start,period_end,
           objective,review_date,review_14_date,status,campaign_name,entity_type,
           entity_name,action_type,baseline_json,external_status,ad_group_name,match_type,
           amazon_suggested_low,amazon_suggested_high)
          VALUES (CURRENT_TIMESTAMP,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
            data["brand"], data.get("asin") or "—", "ppc_action",
            data.get("old_value"), data.get("new_value"), data["period_start"],
            data["period_end"], data["objective"],
            (today+timedelta(days=7)).isoformat(),
            (today+timedelta(days=14)).isoformat(), "proposed",
            data["campaign_name"], data["entity_type"], data["entity_name"],
            data["action_type"], json.dumps(data.get("baseline",{}),sort_keys=True),
            "awaiting_mcp_approval", data.get("ad_group_name"),data.get("match_type"),
            data.get("amazon_suggested_low"),data.get("amazon_suggested_high"),
        ))
        return cur.lastrowid, True


def update_intervention_status(intervention_id, status):
    allowed={"approved","executed","monitoring","dismissed","reverted","completed"}
    if status not in allowed:
        raise ValueError("Invalid intervention status")
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updates={"status":status}
    if status=="approved": updates.update(approved_at=now,external_status="ready_for_mcp")
    elif status=="executed": updates.update(executed_at=now,external_status="pending_confirmation")
    elif status=="monitoring": updates.update(external_status="confirmed")
    elif status in {"dismissed","reverted","completed"}: updates.update(outcome=status)
    assignments=", ".join(f"{column}=?" for column in updates)
    with connect() as conn:
        conn.execute(f"UPDATE interventions SET {assignments} WHERE id=?",
                     (*updates.values(),intervention_id))
