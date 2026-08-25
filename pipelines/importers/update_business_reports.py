import argparse
import hashlib
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


CLOUD_BASE = Path(
    os.getenv(
        "LITET_REPORTS_DIR",
        "/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/Hasten/Reports",
    )
)
DB_PATH = Path(os.getenv("LITET_DB_PATH", CLOUD_BASE / "SQLite" / "litet.db"))
INCOMING_FOLDER = CLOUD_BASE / "Raw" / "incoming"
PROCESSED_FOLDER = CLOUD_BASE / "Raw" / "processed"
FAILED_FOLDER = CLOUD_BASE / "Raw" / "failed"

FILE_PATTERN = re.compile(
    r"^business_report_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$",
    re.IGNORECASE,
)

SOURCE_COLUMNS = {
    "(Parent) ASIN": "parent_asin",
    "(Child) ASIN": "child_asin",
    "Title": "title",
    "SKU": "sku",
    "Sessions - Total": "sessions_total",
    "Sessions - Total - B2B": "sessions_b2b",
    "Session Percentage - Total": "session_percentage_total",
    "Session Percentage - Total - B2B": "session_percentage_b2b",
    "Page Views - Total": "page_views_total",
    "Page Views - Total - B2B": "page_views_b2b",
    "Page Views Percentage - Total": "page_views_percentage_total",
    "Page Views Percentage - Total - B2B": "page_views_percentage_b2b",
    "Featured Offer (Buy Box) Percentage": "featured_offer_percentage",
    "Featured Offer (Buy Box) Percentage - B2B": "featured_offer_percentage_b2b",
    "Units Ordered": "units_ordered",
    "Units Ordered - B2B": "units_ordered_b2b",
    "Unit Session Percentage": "unit_session_percentage",
    "Unit Session Percentage - B2B": "unit_session_percentage_b2b",
    "Ordered Product Sales": "ordered_product_sales",
    "Ordered Product Sales - B2B": "ordered_product_sales_b2b",
    "Total Order Items": "total_order_items",
    "Total Order Items - B2B": "total_order_items_b2b",
}

INTEGER_COLUMNS = [
    "sessions_total",
    "sessions_b2b",
    "page_views_total",
    "page_views_b2b",
    "units_ordered",
    "units_ordered_b2b",
    "total_order_items",
    "total_order_items_b2b",
]

BOUNDED_PERCENT_COLUMNS = [
    "session_percentage_total",
    "session_percentage_b2b",
    "page_views_percentage_total",
    "page_views_percentage_b2b",
    "featured_offer_percentage",
    "featured_offer_percentage_b2b",
]

CONVERSION_PERCENT_COLUMNS = [
    "unit_session_percentage",
    "unit_session_percentage_b2b",
]

CURRENCY_COLUMNS = [
    "ordered_product_sales",
    "ordered_product_sales_b2b",
]


def ensure_folders():
    for folder in (INCOMING_FOLDER, PROCESSED_FOLDER, FAILED_FOLDER):
        folder.mkdir(parents=True, exist_ok=True)


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS business_report_imports (
            file_hash TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            period_type TEXT NOT NULL CHECK (period_type IN ('monthly', 'weekly', 'custom')),
            row_count INTEGER NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS business_traffic (
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            period_type TEXT NOT NULL CHECK (period_type IN ('monthly', 'weekly', 'custom')),
            parent_asin TEXT NOT NULL,
            child_asin TEXT NOT NULL,
            sku TEXT NOT NULL,
            title TEXT,
            sessions_total INTEGER NOT NULL,
            sessions_b2b INTEGER NOT NULL,
            session_percentage_total REAL,
            session_percentage_b2b REAL,
            page_views_total INTEGER NOT NULL,
            page_views_b2b INTEGER NOT NULL,
            page_views_percentage_total REAL,
            page_views_percentage_b2b REAL,
            featured_offer_percentage REAL,
            featured_offer_percentage_b2b REAL,
            units_ordered INTEGER NOT NULL,
            units_ordered_b2b INTEGER NOT NULL,
            unit_session_percentage REAL,
            unit_session_percentage_b2b REAL,
            ordered_product_sales REAL NOT NULL,
            ordered_product_sales_b2b REAL NOT NULL,
            total_order_items INTEGER NOT NULL,
            total_order_items_b2b INTEGER NOT NULL,
            source_file TEXT NOT NULL,
            source_hash TEXT NOT NULL REFERENCES business_report_imports(file_hash),
            imported_at TEXT NOT NULL,
            PRIMARY KEY (period_start, period_end, child_asin, sku)
        );

        CREATE INDEX IF NOT EXISTS idx_business_traffic_child_period
            ON business_traffic(child_asin, period_start, period_end);
        CREATE INDEX IF NOT EXISTS idx_business_traffic_sku_period
            ON business_traffic(sku, period_start, period_end);
        CREATE INDEX IF NOT EXISTS idx_business_traffic_parent_period
            ON business_traffic(parent_asin, period_start, period_end);
        """
    )


def parse_period(file_name):
    match = FILE_PATTERN.fullmatch(file_name)
    if not match:
        raise ValueError(
            "Filename must be business_report_YYYY-MM-DD_YYYY-MM-DD.csv"
        )

    start = pd.Timestamp(match.group(1))
    end = pd.Timestamp(match.group(2))
    if end < start:
        raise ValueError("The report end date cannot precede its start date")

    days = (end - start).days + 1
    is_month = start.day == 1 and end == start + pd.offsets.MonthEnd(0)
    is_week = days == 7 and start.weekday() == 0 and end.weekday() == 6
    period_type = "monthly" if is_month else "weekly" if is_week else "custom"
    return start.date().isoformat(), end.date().isoformat(), period_type


def file_hash(file_path):
    digest = hashlib.sha256()
    with open(file_path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_integer(series, column):
    cleaned = series.fillna("0").astype(str).str.replace(",", "", regex=False).str.strip()
    values = pd.to_numeric(cleaned, errors="raise")
    if ((values % 1) != 0).any() or (values < 0).any():
        raise ValueError(f"{column} must contain non-negative whole numbers")
    return values.astype("int64")


def parse_percentage(series, capped=True):
    cleaned = series.fillna("").astype(str).str.strip()
    present = cleaned.ne("")
    values = pd.to_numeric(
        cleaned.str.replace("%", "", regex=False).where(present), errors="raise"
    ) / 100.0
    if (values.dropna() < 0).any():
        raise ValueError("Percentage values cannot be negative")
    if capped and (values.dropna() > 1).any():
        raise ValueError("This percentage must be between 0% and 100%")
    return values


def parse_currency(series, column):
    cleaned = (
        series.fillna("0")
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    values = pd.to_numeric(cleaned, errors="raise")
    if (values < 0).any():
        raise ValueError(f"{column} cannot contain negative values")
    return values.astype(float)


def load_and_validate(file_path, period_start, period_end, period_type, digest):
    df = pd.read_csv(file_path, dtype=str, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    missing = [column for column in SOURCE_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[list(SOURCE_COLUMNS)].rename(columns=SOURCE_COLUMNS)
    for column in ("parent_asin", "child_asin", "sku"):
        df[column] = df[column].fillna("").astype(str).str.strip()
        if df[column].eq("").any():
            raise ValueError(f"Blank {column} values are not allowed")

    duplicates = df.duplicated(subset=["child_asin", "sku"], keep=False)
    if duplicates.any():
        examples = df.loc[duplicates, ["child_asin", "sku"]].head(5).to_dict("records")
        raise ValueError(f"Duplicate child ASIN/SKU rows found: {examples}")

    for column in INTEGER_COLUMNS:
        df[column] = parse_integer(df[column], column)
    for column in BOUNDED_PERCENT_COLUMNS:
        df[column] = parse_percentage(df[column], capped=True)
    for column in CONVERSION_PERCENT_COLUMNS:
        df[column] = parse_percentage(df[column], capped=False)
    for column in CURRENCY_COLUMNS:
        df[column] = parse_currency(df[column], column)

    imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.insert(0, "period_start", period_start)
    df.insert(1, "period_end", period_end)
    df.insert(2, "period_type", period_type)
    df["source_file"] = file_path.name
    df["source_hash"] = digest
    df["imported_at"] = imported_at
    return df, imported_at


def destination_path(file_path, folder, status):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return folder / f"{timestamp}_{status}_{file_path.name}"


def import_file(file_path, conn, move_after=True):
    period_start, period_end, period_type = parse_period(file_path.name)
    digest = file_hash(file_path)

    already_imported = conn.execute(
        "SELECT 1 FROM business_report_imports WHERE file_hash = ?", (digest,)
    ).fetchone()
    if already_imported:
        print(f"Already imported; skipping: {file_path.name}")
        if move_after:
            shutil.move(file_path, destination_path(file_path, PROCESSED_FOLDER, "duplicate"))
        return 0

    df, imported_at = load_and_validate(
        file_path, period_start, period_end, period_type, digest
    )

    conflict = conn.execute(
        """
        SELECT source_file
        FROM business_report_imports
        WHERE period_start = ? AND period_end = ?
        LIMIT 1
        """,
        (period_start, period_end),
    ).fetchone()
    if conflict:
        raise ValueError(
            f"Period {period_start} through {period_end} was already imported "
            f"from {conflict[0]}; no data was changed"
        )

    with conn:
        conn.execute(
            """
            INSERT INTO business_report_imports
                (file_hash, source_file, period_start, period_end, period_type, row_count, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (digest, file_path.name, period_start, period_end, period_type, len(df), imported_at),
        )
        df.to_sql("business_traffic", conn, if_exists="append", index=False)

    print(
        f"Imported {len(df):,} rows for {period_start} through {period_end} "
        f"({period_type})"
    )
    if move_after:
        target = destination_path(file_path, PROCESSED_FOLDER, "processed")
        shutil.move(file_path, target)
        print(f"Moved file to: {target}")
    return len(df)


def update_business_reports(file_path=None, move_after=True):
    ensure_folders()
    candidates = (
        [Path(file_path)]
        if file_path
        else sorted(INCOMING_FOLDER.glob("business_report_*.csv"))
    )
    if not candidates:
        print(f"No business report files found in: {INCOMING_FOLDER}")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_schema(conn)
        for candidate in candidates:
            try:
                import_file(candidate, conn, move_after=move_after)
            except Exception as exc:
                print(f"Error in {candidate.name}: {exc}")
                if move_after and candidate.exists() and candidate.parent == INCOMING_FOLDER:
                    target = destination_path(candidate, FAILED_FOLDER, "failed")
                    shutil.move(candidate, target)
                    print(f"Moved file to: {target}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Amazon Business Reports")
    parser.add_argument("--file", help="Import one standardized report file")
    parser.add_argument(
        "--keep-file", action="store_true", help="Do not move the source after import"
    )
    args = parser.parse_args()
    update_business_reports(args.file, move_after=not args.keep_file)
