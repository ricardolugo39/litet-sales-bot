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

TRANSACTIONS_FILE = "transactions.csv"


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


def load_transactions_csv(file_path):
    df = pd.read_csv(
        file_path,
        dtype=str
    )

    df.columns = df.columns.str.strip()

    return df


def add_metadata(df):
    imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    df["source_file"] = TRANSACTIONS_FILE
    df["imported_at"] = imported_at

    # =========================
    # Temporary dedupe key
    # =========================

    df["transaction_uid"] = (
        df.astype(str)
        .fillna("")
        .agg("|".join, axis=1)
    )

    return df


def ensure_schema(conn, df):
    cursor = conn.cursor()

    try:
        existing_columns = [
            row[1]
            for row in cursor.execute(
                "PRAGMA table_info(transactions)"
            ).fetchall()
        ]

    except Exception:
        existing_columns = []

    for column in df.columns:
        if column not in existing_columns:
            cursor.execute(
                f'ALTER TABLE transactions ADD COLUMN "{column}" TEXT'
            )

    conn.commit()


def get_existing_transaction_uids(conn):
    try:
        existing = pd.read_sql(
            "SELECT transaction_uid FROM transactions",
            conn
        )

        return set(existing["transaction_uid"].astype(str))

    except Exception:
        return set()


# =========================
# Main
# =========================

def update_transactions():

    ensure_folders()

    file_path = os.path.join(
        INCOMING_FOLDER,
        TRANSACTIONS_FILE
    )

    if not os.path.exists(file_path):
        print(f"No transactions file found: {file_path}")
        return

    conn = sqlite3.connect(DB_PATH)

    try:

        print("Loading transactions file...")

        df = load_transactions_csv(file_path)

        print(f"Rows in file: {len(df):,}")

        df = add_metadata(df)

        # =========================
        # Create table if needed
        # =========================

        try:
            pd.read_sql(
                "SELECT * FROM transactions LIMIT 1",
                conn
            )

        except Exception:
            print("Creating transactions table...")

            df.head(0).to_sql(
                "transactions",
                conn,
                if_exists="replace",
                index=False
            )

        # =========================
        # Ensure schema
        # =========================

        ensure_schema(conn, df)

        existing_uids = get_existing_transaction_uids(conn)

        before = len(df)

        df_new = df[
            ~df["transaction_uid"].isin(existing_uids)
        ].copy()

        new_rows = len(df_new)
        duplicates = before - new_rows

        print(f"New rows: {new_rows:,}")
        print(f"Duplicates skipped: {duplicates:,}")

        if new_rows > 0:

            df_new.to_sql(
                "transactions",
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

        print("Transactions update completed.")

    except Exception as e:

        conn.close()

        print(f"Error: {e}")

        move_file(
            file_path,
            FAILED_FOLDER,
            "failed"
        )


if __name__ == "__main__":
    update_transactions()
