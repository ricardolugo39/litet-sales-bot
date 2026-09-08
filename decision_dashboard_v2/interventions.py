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
    # Review clocks start only after a real Amazon change is confirmed.
    conn.execute("""UPDATE interventions SET review_date=NULL,review_14_date=NULL
      WHERE intervention_type='ppc_action' AND status IN ('proposed','approved')""")
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
        rows=[dict(r) for r in conn.execute("SELECT rowid AS intervention_rowid,* FROM interventions ORDER BY created_at DESC,rowid DESC LIMIT ?",(limit,))]
    analytics_path=os.getenv("LITET_DB_PATH")
    if analytics_path and Path(analytics_path).exists():
        with sqlite3.connect(analytics_path) as facts:
            facts.row_factory=sqlite3.Row
            for row in rows:
                if row.get("intervention_type")!="ppc_action":
                    continue
                if not (row.get("ad_group_name") and row.get("match_type")):
                    match=facts.execute("""SELECT ad_group_name,match_type,SUM(spend) spend
                      FROM ppc_fact_clean WHERE brand=? AND campaign_name=? AND target=?
                      GROUP BY ad_group_name,match_type ORDER BY SUM(spend) DESC LIMIT 1""",
                      (row["brand"],row.get("campaign_name"),row.get("entity_name"))).fetchone()
                    if match:
                        row["ad_group_name"]=match["ad_group_name"]
                        row["match_type"]=match["match_type"]
                if row.get("executed_at"):
                    start=date.fromisoformat(row["executed_at"][:10])+timedelta(days=1)
                    end=min(date.today(),start+timedelta(days=13))
                    clauses=["brand=?","campaign_name=?","target=?","report_date BETWEEN ? AND ?"]
                    params=[row["brand"],row.get("campaign_name"),row.get("entity_name"),start.isoformat(),end.isoformat()]
                    if row.get("ad_group_name"):
                        clauses.append("ad_group_name=?"); params.append(row["ad_group_name"])
                    if row.get("match_type"):
                        clauses.append("match_type=?"); params.append(row["match_type"])
                    result=facts.execute(f"""SELECT COUNT(DISTINCT report_date) days,SUM(clicks) clicks,
                      SUM(spend) spend,SUM(ad_sales) ad_sales,SUM(ad_orders) orders
                      FROM ppc_fact_clean WHERE {' AND '.join(clauses)}""",params).fetchone()
                    post=dict(result) if result else {}
                    if post.get("days"):
                        post["acos"]=post["spend"]/post["ad_sales"] if post.get("ad_sales") else None
                        post["cpc"]=post["spend"]/post["clicks"] if post.get("clicks") else None
                        post["spend_per_day"]=post["spend"]/post["days"]
                        post["orders_per_day"]=post["orders"]/post["days"]
                    row["post"]=post
    for row in rows:
        # Some early Railway records inherited a nullable legacy id column.
        # The SQLite rowid is stable for the preserved table and drives controls.
        row["id"]=row["intervention_rowid"]
        try: row["baseline"]=json.loads(row.get("baseline_json") or "{}")
        except json.JSONDecodeError: row["baseline"]={}
        if row.get("period_start") and row.get("period_end"):
            baseline_days=(date.fromisoformat(row["period_end"])-date.fromisoformat(row["period_start"])).days+1
            row["baseline"]["days"]=baseline_days
            row["baseline"]["spend_per_day"]=(row["baseline"].get("spend") or 0)/baseline_days
            row["baseline"]["orders_per_day"]=(row["baseline"].get("orders") or 0)/baseline_days
        post=row.get("post") or {}
        if post.get("days"):
            base_acos=row["baseline"].get("acos")
            base_orders=row["baseline"].get("orders_per_day") or 0
            order_ratio=post["orders_per_day"]/base_orders if base_orders else None
            if post["days"]<7:
                row["result_signal"]="Early read — wait for 7 complete days"
                row["result_class"]="warn"
            elif post.get("acos") is not None and base_acos is not None and post["acos"]<base_acos and (order_ratio is None or order_ratio>=.8):
                row["result_signal"]="Improving — efficiency rose without material order-rate loss"
                row["result_class"]="good"
            elif post.get("acos") is not None and base_acos is not None and post["acos"]<base_acos:
                row["result_signal"]="Tradeoff — ACoS improved but order pace weakened"
                row["result_class"]="warn"
            else:
                row["result_signal"]="Not improving yet"
                row["result_class"]="bad"
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
        cur=conn.execute("""INSERT INTO interventions
          (created_at,brand,asin,intervention_type,old_value,new_value,period_start,period_end,
           objective,review_date,review_14_date,status,campaign_name,entity_type,
           entity_name,action_type,baseline_json,external_status,ad_group_name,match_type,
           amazon_suggested_low,amazon_suggested_high)
          VALUES (CURRENT_TIMESTAMP,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
            data["brand"], data.get("asin") or "—", "ppc_action",
            data.get("old_value"), data.get("new_value"), data["period_start"],
            data["period_end"], data["objective"],
            None, None, "proposed",
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
    elif status=="executed":
        executed=date.today()
        updates.update(executed_at=now,review_date=(executed+timedelta(days=7)).isoformat(),
                       review_14_date=(executed+timedelta(days=14)).isoformat(),
                       external_status="monitoring_amazon_results")
    elif status=="monitoring": updates.update(external_status="confirmed")
    elif status in {"dismissed","reverted","completed"}: updates.update(outcome=status)
    assignments=", ".join(f"{column}=?" for column in updates)
    with connect() as conn:
        conn.execute(f"UPDATE interventions SET {assignments} WHERE rowid=?",
                     (*updates.values(),intervention_id))
