import os
import shutil
import sqlite3
from datetime import datetime
import pandas as pd


# =========================
# Paths
# =========================

CLOUD_BASE = os.getenv(
    "LITET_REPORTS_DIR",
    "/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/Hasten/Reports",
)

DB_PATH = os.getenv("LITET_DB_PATH", f"{CLOUD_BASE}/SQLite/litet.db")

INCOMING_FOLDER = f"{CLOUD_BASE}/Raw/incoming"
PROCESSED_FOLDER = f"{CLOUD_BASE}/Raw/processed"
FAILED_FOLDER = f"{CLOUD_BASE}/Raw/failed"

PPC_FILE = "ppc.xlsx"


# =========================
# Config
# =========================

COLUMNS_TO_DROP = [
    "Retailer",
    "Country",
]


# =========================
# Helpers
# =========================

def ensure_folders():

    os.makedirs(INCOMING_FOLDER, exist_ok=True)
    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    os.makedirs(FAILED_FOLDER, exist_ok=True)


def move_file(file_path, destination_folder, status):

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    file_name = os.path.basename(file_path)

    destination_path = os.path.join(
        destination_folder,
        f"{timestamp}_{status}_{file_name}"
    )

    shutil.move(file_path, destination_path)

    print(f"Moved file to: {destination_path}")


def load_ppc_file(file_path):

    df = pd.read_excel(
        file_path,
        dtype=str
    )

    # =========================
    # Clean headers
    # =========================

    df.columns = df.columns.str.strip()

    # =========================
    # Drop unwanted columns
    # =========================

    cols_to_drop = [
        c for c in COLUMNS_TO_DROP
        if c in df.columns
    ]

    df = df.drop(columns=cols_to_drop)

    return df


def add_metadata(df):

    imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    df["source_file"] = PPC_FILE
    df["imported_at"] = imported_at

    # =========================
    # PPC dedupe key
    # =========================

    df["ppc_uid"] = (
        df["Date"].fillna("").astype(str)
        + "_"
        + df["Campaign Name"].fillna("").astype(str)
        + "_"
        + df["Ad Group Name"].fillna("").astype(str)
        + "_"
        + df["Targeting"].fillna("").astype(str)
        + "_"
        + df["Match Type"].fillna("").astype(str)
        + "_"
        + df["Customer Search Term"].fillna("").astype(str)
    )

    return df


def ensure_schema(conn, df):

    cursor = conn.cursor()

    try:

        existing_columns = [
            row[1]
            for row in cursor.execute(
                "PRAGMA table_info(ppc)"
            ).fetchall()
        ]

    except Exception:

        existing_columns = []

    for column in df.columns:

        if column not in existing_columns:

            cursor.execute(
                f'ALTER TABLE ppc ADD COLUMN "{column}" TEXT'
            )

    conn.commit()


def get_existing_ppc_uids(conn):

    try:

        existing = pd.read_sql(
            "SELECT ppc_uid FROM ppc",
            conn
        )

        return set(existing["ppc_uid"].astype(str))

    except Exception:

        return set()


# =========================
# Main
# =========================

def update_ppc():

    ensure_folders()

    file_path = os.path.join(
        INCOMING_FOLDER,
        PPC_FILE
    )

    if not os.path.exists(file_path):

        print(f"No PPC file found: {file_path}")
        return False

    conn = sqlite3.connect(DB_PATH)

    try:

        print("Loading PPC file...")

        df = load_ppc_file(file_path)

        print(f"Rows in file: {len(df):,}")

        df = add_metadata(df)

        # =========================
        # Ensure schema
        # =========================

        ensure_schema(conn, df)

        existing_uids = get_existing_ppc_uids(conn)

        before = len(df)

        df_new = df[
            ~df["ppc_uid"].isin(existing_uids)
        ].copy()

        new_rows = len(df_new)
        duplicates = before - new_rows

        print(f"New rows: {new_rows:,}")
        print(f"Duplicates skipped: {duplicates:,}")

        if new_rows > 0:

            df_new.to_sql(
                "ppc",
                conn,
                if_exists="append",
                index=False
            )

        conn.close()

        move_file(
            file_path,
            PROCESSED_FOLDER,
            "processed"
        )

        print("PPC update completed.")
        return True

    except Exception as e:

        conn.close()

        print(f"Error: {e}")

        move_file(
            file_path,
            FAILED_FOLDER,
            "failed"
        )
        return False


if __name__ == "__main__":
    update_ppc()
