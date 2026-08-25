"""Local decision log. Recording a case never changes Amazon."""
import os
import sqlite3
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
    return conn


def record_pricing_case(data):
    with connect() as conn:
        cur = conn.execute("""INSERT INTO interventions
          (brand,asin,intervention_type,old_value,new_value,period_start,period_end,objective,required_lift,review_date)
          VALUES (?,?, 'price_test', ?,?,?,?,?,?,?)""",
          (data["brand"],data["asin"],data["old_value"],data["new_value"],data["period_start"],data["period_end"],data["objective"],data["required_lift"],data["review_date"]))
        return cur.lastrowid


def recent_interventions(limit=20):
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM interventions ORDER BY created_at DESC,id DESC LIMIT ?",(limit,))]
