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

INVENTORY_FILE = "inventory.txt"


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


def load_inventory_txt(file_path):

    df = pd.read_csv(
        file_path,
        sep="\t",
        dtype=str
    )

    df.columns = df.columns.str.strip()

    return df


def add_metadata(df):

    imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    snapshot_date = datetime.now().strftime("%Y-%m-%d")

    df["snapshot_date"] = snapshot_date
    df["imported_at"] = imported_at
    df["source_file"] = INVENTORY_FILE

    # =========================
    # Inventory snapshot UID
    # =========================

    df["snapshot_uid"] = (
        snapshot_date
        + "_"
        + df["asin"].fillna("").astype(str)
        + "_"
        + df["seller-sku"].fillna("").astype(str)
    )

    return df


def ensure_schema(conn, df):

    cursor = conn.cursor()

    try:
        existing_columns = [
            row[1]
            for row in cursor.execute(
                "PRAGMA table_info(inventory_snapshots)"
            ).fetchall()
        ]

    except Exception:
        existing_columns = []

    for column in df.columns:

        if column not in existing_columns:

            cursor.execute(
                f'ALTER TABLE inventory_snapshots ADD COLUMN "{column}" TEXT'
            )

    conn.commit()


def get_existing_snapshot_uids(conn):

    try:
        existing = pd.read_sql(
            "SELECT snapshot_uid FROM inventory_snapshots",
            conn
        )

        return set(existing["snapshot_uid"].astype(str))

    except Exception:
        return set()


# =========================
# Main
# =========================

def update_inventory():

    ensure_folders()

    file_path = os.path.join(
        INCOMING_FOLDER,
        INVENTORY_FILE
    )

    if not os.path.exists(file_path):
        print(f"No inventory file found: {file_path}")
        return

    conn = sqlite3.connect(DB_PATH)

    try:

        print("Loading inventory file...")

        df = load_inventory_txt(file_path)

        print(f"Rows in file: {len(df):,}")

        df = add_metadata(df)

        # =========================
        # Create table if needed
        # =========================

        try:
            pd.read_sql(
                "SELECT * FROM inventory_snapshots LIMIT 1",
                conn
            )

        except Exception:

            print("Creating inventory_snapshots table...")

            df.head(0).to_sql(
                "inventory_snapshots",
                conn,
                if_exists="replace",
                index=False
            )

        # =========================
        # Ensure schema
        # =========================

        ensure_schema(conn, df)

        existing_uids = get_existing_snapshot_uids(conn)

        before = len(df)

        df_new = df[
            ~df["snapshot_uid"].isin(existing_uids)
        ].copy()

        new_rows = len(df_new)
        duplicates = before - new_rows

        print(f"New rows: {new_rows:,}")
        print(f"Duplicates skipped: {duplicates:,}")

        if new_rows > 0:

            df_new.to_sql(
                "inventory_snapshots",
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

        print("Inventory update completed.")

    except Exception as e:

        conn.close()

        print(f"Error: {e}")

        move_file(
            file_path,
            FAILED_FOLDER,
            "failed"
        )


if __name__ == "__main__":
    update_inventory()
