"""Validate, upload, and refresh the offline cache for the canonical database."""

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


load_dotenv()


REQUIRED_TABLES = {
    "orders", "business_traffic", "asin_economics", "inventory_snapshots",
    "dim_product", "cogs_ledger", "ppc_fact_clean", "ppc",
    "sales_profitability", "transactions", "transaction_mart",
}

PACIFIC = ZoneInfo("America/Los_Angeles")


def _pacific_date(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RuntimeError(f"Order timestamp has no UTC offset: {value}")
    return parsed.astimezone(PACIFIC).date().isoformat()


def _us_date(value):
    if not value:
        return None
    for pattern in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).split()[0], pattern).date().isoformat()
        except ValueError:
            continue
    raise RuntimeError(f"Unsupported report date: {value}")


def validate_analytics_freshness(conn):
    """Refuse to publish raw data newer than its dependent analytics marts."""
    latest_order = conn.execute(
        'SELECT MAX("purchase-date") FROM orders '
        'WHERE "sales-channel" = \'Amazon.com\' AND CAST(quantity AS REAL) > 0'
    ).fetchone()[0]
    latest_sales = conn.execute(
        "SELECT MAX(date(sale_date)) FROM sales_profitability"
    ).fetchone()[0]
    order_date = _pacific_date(latest_order)
    if order_date and (not latest_sales or latest_sales < order_date):
        raise RuntimeError(
            f"sales_profitability is stale ({latest_sales or 'empty'}; raw orders {order_date})"
        )

    raw_transaction_dates = [
        _us_date(row[0]) for row in conn.execute('SELECT DISTINCT "Date" FROM transactions')
        if row[0]
    ]
    transaction_date = max(raw_transaction_dates, default=None)
    latest_transaction_mart = conn.execute(
        "SELECT MAX(date(transaction_date)) FROM transaction_mart"
    ).fetchone()[0]
    if transaction_date and (
        not latest_transaction_mart or latest_transaction_mart < transaction_date
    ):
        raise RuntimeError(
            "transaction_mart is stale "
            f"({latest_transaction_mart or 'empty'}; raw transactions {transaction_date})"
        )

    raw_ppc_dates = [
        _us_date(row[0]) for row in conn.execute('SELECT DISTINCT "Date" FROM ppc')
        if row[0]
    ]
    ppc_date = max(raw_ppc_dates, default=None)
    latest_ppc_fact = conn.execute(
        "SELECT MAX(date(report_date)) FROM ppc_fact_clean"
    ).fetchone()[0]
    if ppc_date and (not latest_ppc_fact or latest_ppc_fact < ppc_date):
        raise RuntimeError(
            f"ppc_fact_clean is stale ({latest_ppc_fact or 'empty'}; raw PPC {ppc_date})"
        )


def validate(path):
    with sqlite3.connect(path) as conn:
        result = conn.execute("PRAGMA quick_check").fetchone()
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    if not result or result[0] != "ok":
        raise RuntimeError("Local SQLite integrity check failed")
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise RuntimeError(f"Local database is missing: {', '.join(missing)}")
    with sqlite3.connect(path) as conn:
        validate_analytics_freshness(conn)


def request(url, token, method="GET", data=None):
    req = urllib.request.Request(
        url.rstrip("/") + "/admin/database",
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/gzip"},
    )
    return urllib.request.urlopen(req, timeout=300)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=os.getenv("LITET_DB_PATH"))
    parser.add_argument("--url", default=os.getenv("DASHBOARD_URL"))
    parser.add_argument(
        "--inventory-url",
        default=os.getenv("INVENTORY_APP_URL"),
        help="Optional second app that consumes the same analytics snapshot",
    )
    parser.add_argument("--cache", default=os.getenv("LITET_OFFLINE_CACHE", "offline_cache/litet.db"))
    args = parser.parse_args()
    token = os.getenv("ADMIN_UPLOAD_TOKEN")
    if not args.database or not args.url or not token:
        raise SystemExit("LITET_DB_PATH, DASHBOARD_URL, and ADMIN_UPLOAD_TOKEN are required")

    database = Path(args.database).expanduser().resolve()
    validate(database)
    with tempfile.NamedTemporaryFile(suffix=".db.gz") as archive:
        with database.open("rb") as source, gzip.open(archive.name, "wb") as target:
            shutil.copyfileobj(source, target)
        payload = Path(archive.name).read_bytes()
    with request(args.url, token, method="PUT", data=payload) as response:
        print("Uploaded:", json.load(response))

    if args.inventory_url:
        with request(args.inventory_url, token, method="PUT", data=payload) as response:
            print("Inventory app uploaded:", json.load(response))

    cache = Path(args.cache).expanduser().resolve()
    cache.parent.mkdir(parents=True, exist_ok=True)
    with request(args.url, token) as response, tempfile.NamedTemporaryFile(dir=cache.parent, delete=False) as raw:
        temporary = Path(raw.name)
        with gzip.GzipFile(fileobj=response, mode="rb") as source:
            shutil.copyfileobj(source, raw)
    validate(temporary)
    os.replace(temporary, cache)
    print(f"Offline cache refreshed: {cache}")


if __name__ == "__main__":
    main()
