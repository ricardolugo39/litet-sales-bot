import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from .period_overlap import retire_replaced_cross_month_reports


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

IDENTIFYING_COLUMNS = {
    "Start date",
    "End date",
    "Parent ASIN",
    "ASIN",
    "Units sold",
    "Net sales",
    "Net proceeds total",
}

REQUIRED_COLUMNS = IDENTIFYING_COLUMNS | {
    "Amazon store",
    "Currency code",
    "Average sales price",
    "Units returned",
    "Net units sold",
    "Sales",
}

CANONICAL_FEES = {
    "AWD Storage Fee total": "awd_storage_fee",
    "AWD Transportation Fee total": "awd_transportation_fee",
    "AWD inbound processing fee total": "awd_inbound_processing_fee",
    "AWD outbound processing fee total": "awd_outbound_processing_fee",
    "Aged inventory surcharge total": "aged_inventory_surcharge",
    "FBA fulfillment fees total": "fba_fulfillment_fees",
    "Monthly inventory storage fee total": "monthly_inventory_storage_fee",
    "Referral Fee Refunds total": "referral_fee_refunds",
    "Referral fee total": "referral_fee",
    "Refund administration fee total": "refund_administration_fee",
    "Returns processing fee for Apparel and Shoes total": "returns_processing_fee",
    "Storage utilization surcharge total": "storage_utilization_surcharge",
    "Sponsored Products charge total": "sponsored_products_charge",
}

INTEGER_SOURCE_COLUMNS = {
    "Units sold": "units_sold",
    "Units returned": "units_returned",
    "Net units sold": "net_units_sold",
}

MONEY_SOURCE_COLUMNS = {
    "Average sales price": "average_sales_price",
    "Sales": "sales",
    "Net sales": "net_sales",
    "Net proceeds total": "net_proceeds",
    "Net proceeds per net unit sold": "net_proceeds_per_net_unit_sold",
}


def ensure_folders():
    for folder in (INCOMING_FOLDER, PROCESSED_FOLDER, FAILED_FOLDER):
        folder.mkdir(parents=True, exist_ok=True)


def ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS economics_report_imports (
            file_hash TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            period_type TEXT NOT NULL CHECK (period_type IN ('monthly', 'weekly', 'custom')),
            row_count INTEGER NOT NULL,
            source_columns_json TEXT NOT NULL,
            fee_columns_used_json TEXT NOT NULL,
            reported_net_proceeds REAL NOT NULL,
            calculated_net_proceeds REAL NOT NULL,
            reconciliation_difference REAL NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS asin_economics (
            amazon_store TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            period_type TEXT NOT NULL CHECK (period_type IN ('monthly', 'weekly', 'custom')),
            parent_asin TEXT,
            asin TEXT NOT NULL,
            currency_code TEXT,
            average_sales_price REAL NOT NULL,
            units_sold INTEGER NOT NULL,
            units_returned INTEGER NOT NULL,
            net_units_sold INTEGER NOT NULL,
            sales REAL NOT NULL,
            net_sales REAL NOT NULL,
            awd_storage_fee REAL NOT NULL DEFAULT 0,
            awd_transportation_fee REAL NOT NULL DEFAULT 0,
            awd_inbound_processing_fee REAL NOT NULL DEFAULT 0,
            awd_outbound_processing_fee REAL NOT NULL DEFAULT 0,
            aged_inventory_surcharge REAL NOT NULL DEFAULT 0,
            fba_fulfillment_fees REAL NOT NULL DEFAULT 0,
            monthly_inventory_storage_fee REAL NOT NULL DEFAULT 0,
            referral_fee_refunds REAL NOT NULL DEFAULT 0,
            referral_fee REAL NOT NULL DEFAULT 0,
            refund_administration_fee REAL NOT NULL DEFAULT 0,
            returns_processing_fee REAL NOT NULL DEFAULT 0,
            storage_utilization_surcharge REAL NOT NULL DEFAULT 0,
            sponsored_products_charge REAL NOT NULL DEFAULT 0,
            other_fee_total REAL NOT NULL DEFAULT 0,
            net_proceeds REAL NOT NULL,
            net_proceeds_per_net_unit_sold REAL,
            calculated_net_proceeds REAL NOT NULL,
            reconciliation_difference REAL NOT NULL,
            fee_totals_json TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_hash TEXT NOT NULL REFERENCES economics_report_imports(file_hash),
            imported_at TEXT NOT NULL,
            PRIMARY KEY (amazon_store, period_start, period_end, asin)
        );

        CREATE INDEX IF NOT EXISTS idx_asin_economics_asin_period
            ON asin_economics(asin, period_start, period_end);
        CREATE INDEX IF NOT EXISTS idx_asin_economics_parent_period
            ON asin_economics(parent_asin, period_start, period_end);
        """
    )


def is_economics_report(file_path):
    try:
        columns = set(pd.read_csv(file_path, encoding="utf-8-sig", nrows=0).columns)
        return IDENTIFYING_COLUMNS.issubset(columns)
    except Exception:
        return False


def parse_date(value, column):
    parsed = pd.to_datetime(value, format="%m/%d/%Y", errors="raise")
    return parsed.dt.date.astype(str)


def classify_period(start_text, end_text):
    start = pd.Timestamp(start_text)
    end = pd.Timestamp(end_text)
    if end < start:
        raise ValueError("The report end date cannot precede its start date")
    days = (end - start).days + 1
    is_month = start.day == 1 and end == start + pd.offsets.MonthEnd(0)
    return "monthly" if is_month else "weekly" if days == 7 else "custom"


def file_hash(file_path):
    digest = hashlib.sha256()
    with open(file_path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_number(series, column, integer=False, allow_negative=True):
    cleaned = (
        series.fillna("0")
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    values = pd.to_numeric(cleaned, errors="raise")
    if not allow_negative and (values < 0).any():
        raise ValueError(f"{column} cannot contain negative values")
    if integer:
        if ((values % 1) != 0).any():
            raise ValueError(f"{column} must contain whole numbers")
        return values.astype("int64")
    return values.astype(float)


def selected_fee_columns(columns):
    fee_columns = {
        column for column in columns
        if column.endswith(" total") and column != "Net proceeds total"
    }

    # Amazon exposes both components and their already-summed parent fee.
    if "FBA fulfillment fees total" in fee_columns:
        fee_columns.discard("Base fulfillment fee total")
        fee_columns.discard("Fuel and Logistics-related surcharge total")
    if "Monthly inventory storage fee total" in fee_columns:
        fee_columns.discard("Base monthly storage fee total")
    return sorted(fee_columns)


def load_and_validate(file_path, digest):
    raw = pd.read_csv(file_path, dtype=str, encoding="utf-8-sig")
    raw.columns = raw.columns.str.strip()
    missing = sorted(REQUIRED_COLUMNS - set(raw.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    starts = parse_date(raw["Start date"], "Start date")
    ends = parse_date(raw["End date"], "End date")
    periods = pd.DataFrame({"start": starts, "end": ends}).drop_duplicates()
    if len(periods) != 1:
        raise ValueError("Each economics file must contain exactly one reporting period")
    period_start = periods.iloc[0]["start"]
    period_end = periods.iloc[0]["end"]
    period_type = classify_period(period_start, period_end)

    for column in ("Amazon store", "ASIN"):
        if raw[column].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError(f"Blank {column} values are not allowed")
    if raw.duplicated(["Amazon store", "ASIN"], keep=False).any():
        raise ValueError("Duplicate Amazon store/ASIN rows found in one period")

    result = pd.DataFrame()
    result["amazon_store"] = raw["Amazon store"].str.strip()
    result["period_start"] = period_start
    result["period_end"] = period_end
    result["period_type"] = period_type
    result["parent_asin"] = raw["Parent ASIN"].fillna("").str.strip()
    result["asin"] = raw["ASIN"].str.strip()
    result["currency_code"] = raw["Currency code"].fillna("").str.strip()

    for source, target in INTEGER_SOURCE_COLUMNS.items():
        result[target] = parse_number(raw[source], source, integer=True)
    for source, target in MONEY_SOURCE_COLUMNS.items():
        if source in raw.columns:
            result[target] = parse_number(raw[source], source)
        else:
            result[target] = float("nan")

    all_fee_columns = sorted(
        column for column in raw.columns
        if column.endswith(" total") and column != "Net proceeds total"
    )
    parsed_fees = {
        column: parse_number(raw[column], column)
        for column in all_fee_columns
    }
    for source, target in CANONICAL_FEES.items():
        result[target] = parsed_fees.get(source, pd.Series(0.0, index=raw.index))

    used_fee_columns = selected_fee_columns(raw.columns)
    canonical_source_columns = set(CANONICAL_FEES)
    other_used_columns = [
        column for column in used_fee_columns
        if column not in canonical_source_columns
    ]
    result["other_fee_total"] = sum(
        (parsed_fees[column] for column in other_used_columns),
        start=pd.Series(0.0, index=raw.index),
    )
    included_fee_total = sum(
        (parsed_fees[column] for column in used_fee_columns),
        start=pd.Series(0.0, index=raw.index),
    )
    result["calculated_net_proceeds"] = result["net_sales"] - included_fee_total
    result["reconciliation_difference"] = (
        result["calculated_net_proceeds"] - result["net_proceeds"]
    )
    result["fee_totals_json"] = [
        json.dumps(
            {column: float(parsed_fees[column].iloc[index]) for column in all_fee_columns},
            sort_keys=True,
        )
        for index in range(len(raw))
    ]

    report_difference = float(result["reconciliation_difference"].sum())
    if abs(report_difference) > 0.05:
        raise ValueError(
            "Net proceeds reconciliation failed: "
            f"difference is ${report_difference:,.2f}; no data was imported"
        )

    imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result["source_file"] = file_path.name
    result["source_hash"] = digest
    result["imported_at"] = imported_at
    return {
        "data": result,
        "period_start": period_start,
        "period_end": period_end,
        "period_type": period_type,
        "imported_at": imported_at,
        "source_columns": list(raw.columns),
        "fee_columns_used": used_fee_columns,
        "reported_net_proceeds": float(result["net_proceeds"].sum()),
        "calculated_net_proceeds": float(result["calculated_net_proceeds"].sum()),
        "reconciliation_difference": report_difference,
    }


def destination_path(file_path, folder, status, period_start=None, period_end=None):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    period = f"_{period_start}_{period_end}" if period_start and period_end else ""
    return folder / f"{timestamp}_{status}_asin_economics{period}_{file_path.name}"


def catalog_coverage(conn, asins):
    placeholders = ",".join("?" for _ in asins)
    if not placeholders:
        return 0, []
    known = {
        row[0] for row in conn.execute(
            f"SELECT asin FROM dim_product WHERE asin IN ({placeholders})", tuple(asins)
        )
    }
    return len(known), sorted(set(asins) - known)


def import_file(file_path, conn, move_after=True):
    digest = file_hash(file_path)
    if conn.execute(
        "SELECT 1 FROM economics_report_imports WHERE file_hash = ?", (digest,)
    ).fetchone():
        print(f"Already imported; skipping: {file_path.name}")
        if move_after:
            shutil.move(file_path, destination_path(file_path, PROCESSED_FOLDER, "duplicate"))
        return 0

    package = load_and_validate(file_path, digest)
    start = package["period_start"]
    end = package["period_end"]
    conflict = conn.execute(
        """
        SELECT source_file FROM economics_report_imports
        WHERE period_start = ? AND period_end = ? LIMIT 1
        """,
        (start, end),
    ).fetchone()
    if conflict:
        raise ValueError(
            f"Period {start} through {end} was already imported from {conflict[0]}"
        )

    df = package["data"]
    with conn:
        conn.execute(
            """
            INSERT INTO economics_report_imports (
                file_hash, source_file, period_start, period_end, period_type,
                row_count, source_columns_json, fee_columns_used_json,
                reported_net_proceeds, calculated_net_proceeds,
                reconciliation_difference, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest, file_path.name, start, end, package["period_type"], len(df),
                json.dumps(package["source_columns"]),
                json.dumps(package["fee_columns_used"]),
                package["reported_net_proceeds"], package["calculated_net_proceeds"],
                package["reconciliation_difference"], package["imported_at"],
            ),
        )
        df.to_sql("asin_economics", conn, if_exists="append", index=False)
        retired = retire_replaced_cross_month_reports(
            conn, "economics_report_imports", "asin_economics"
        )

    matched, unmatched = catalog_coverage(conn, df["asin"].tolist())
    print(
        f"Imported {len(df):,} ASIN rows for {start} through {end} "
        f"({package['period_type']}); catalog matches: {matched}/{len(df)}; "
        f"net proceeds: ${package['reported_net_proceeds']:,.2f}"
    )
    for source in retired:
        print(f"Retired replaced cross-month economics report: {source}")
    if unmatched:
        print(f"Warning: unmatched ASINs: {unmatched}")
    if move_after:
        target = destination_path(file_path, PROCESSED_FOLDER, "processed", start, end)
        shutil.move(file_path, target)
        print(f"Moved file to: {target}")
    return len(df)


def update_asin_economics(file_path=None, move_after=True):
    ensure_folders()
    if file_path:
        candidates = [Path(file_path)]
    else:
        candidates = [
            path for path in sorted(INCOMING_FOLDER.glob("*.csv"))
            if is_economics_report(path)
        ]
    if not candidates:
        print(f"No ASIN economics files found in: {INCOMING_FOLDER}")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_schema(conn)
        for candidate in candidates:
            try:
                if not is_economics_report(candidate):
                    raise ValueError("File is not an Amazon ASIN economics report")
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
    parser = argparse.ArgumentParser(description="Import Amazon ASIN economics reports")
    parser.add_argument("--file", help="Import one economics CSV")
    parser.add_argument("--keep-file", action="store_true", help="Do not move the source")
    args = parser.parse_args()
    update_asin_economics(args.file, move_after=not args.keep_file)
