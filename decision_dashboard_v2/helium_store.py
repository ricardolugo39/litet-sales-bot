"""Validated, historical Helium 10 snapshots stored in the canonical SQLite DB."""

import json
import sqlite3
from datetime import date
from pathlib import Path


BRANDS = {"Litet": "B0DSCFD253", "Has10": "B0CHMVPCC7"}


def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS helium_snapshots (
      id INTEGER PRIMARY KEY,
      captured_at TEXT NOT NULL,
      received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      marketplace TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'helium10_mcp',
      payload_json TEXT NOT NULL
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_helium_snapshots_captured "
        "ON helium_snapshots(captured_at DESC, id DESC)"
    )


def _number(value, label, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")


def validate_snapshot(payload):
    if not isinstance(payload, dict):
        raise ValueError("snapshot must be a JSON object")
    try:
        date.fromisoformat(payload["captured_at"][:10])
    except (KeyError, TypeError, ValueError):
        raise ValueError("captured_at must start with an ISO date") from None
    if payload.get("marketplace") != "US":
        raise ValueError("marketplace must be US")
    brands = payload.get("brands")
    if not isinstance(brands, dict) or set(brands) != set(BRANDS):
        raise ValueError("snapshot must contain exactly Litet and Has10")

    for brand, expected_parent in BRANDS.items():
        data = brands[brand]
        if data.get("parent_asin") != expected_parent:
            raise ValueError(f"{brand}.parent_asin must be {expected_parent}")
        own = data.get("own")
        if not isinstance(own, dict):
            raise ValueError(f"{brand}.own is required")
        for field in ("sales", "revenue", "price", "reviews", "rating", "top10_keywords"):
            _number(own.get(field), f"{brand}.own.{field}", nullable=True)
        _number(own.get("sales_change"), f"{brand}.own.sales_change", nullable=True)

        competitors = data.get("competitors")
        if not isinstance(competitors, list) or not competitors:
            raise ValueError(f"{brand}.competitors must not be empty")
        for index, competitor in enumerate(competitors):
            prefix = f"{brand}.competitors[{index}]"
            if not competitor.get("name") or not competitor.get("parent"):
                raise ValueError(f"{prefix} requires name and resolved parent")
            if competitor.get("segment") not in {"direct", "value", "premium", "multipack"}:
                raise ValueError(f"{prefix}.segment is invalid")
            for field in ("price", "sales", "reviews", "top10_keywords"):
                _number(competitor.get(field), f"{prefix}.{field}", nullable=True)
            _number(competitor.get("sales_change"), f"{prefix}.sales_change", nullable=True)

        keywords = data.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise ValueError(f"{brand}.keywords must not be empty")
        seen = set()
        for index, keyword in enumerate(keywords):
            prefix = f"{brand}.keywords[{index}]"
            phrase = keyword.get("phrase", "").strip().lower()
            if not phrase or phrase in seen:
                raise ValueError(f"{prefix}.phrase is missing or duplicated")
            seen.add(phrase)
            _number(keyword.get("search_volume"), f"{prefix}.search_volume")
            _number(keyword.get("rank"), f"{prefix}.rank", nullable=True)
            _number(keyword.get("peer_rank"), f"{prefix}.peer_rank", nullable=True)
    return payload


def save_snapshot(path, payload):
    validate_snapshot(payload)
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    with sqlite3.connect(database) as conn:
        ensure_schema(conn)
        cursor = conn.execute(
            "INSERT INTO helium_snapshots(captured_at, marketplace, payload_json) VALUES (?,?,?)",
            (payload["captured_at"], payload["marketplace"], encoded),
        )
    return cursor.lastrowid


def latest_snapshot(path):
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT payload_json FROM helium_snapshots ORDER BY captured_at DESC, id DESC LIMIT 1"
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None
    return json.loads(row[0]) if row else None
