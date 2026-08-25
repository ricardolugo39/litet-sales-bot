"""Validate, upload, and refresh the offline cache for the canonical database."""

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import tempfile
import urllib.request
from pathlib import Path


REQUIRED_TABLES = {
    "orders", "business_traffic", "asin_economics", "inventory_snapshots",
    "dim_product", "cogs_ledger", "ppc_fact_clean",
}


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

