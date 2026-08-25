import os
import shutil
import sqlite3
from datetime import datetime
import pandas as pd


CLOUD_BASE = os.getenv(
    "LITET_REPORTS_DIR",
    "/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/Hasten/Reports",
)

DB_PATH = os.getenv("LITET_DB_PATH", f"{CLOUD_BASE}/SQLite/litet.db")

INCOMING_FOLDER = f"{CLOUD_BASE}/Raw/incoming"
PROCESSED_FOLDER = f"{CLOUD_BASE}/Raw/processed"
FAILED_FOLDER = f"{CLOUD_BASE}/Raw/failed"

ORDERS_FILE = "orders.txt"

COLUMNS_TO_DROP = [
    "cpf",
    "purchase-order-number",
    "buyer-identification-number",
    "buyer-identification-type",
]


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


def load_orders_txt(file_path):
    df = pd.read_csv(file_path, sep="\t", dtype=str)

    df.columns = df.columns.str.strip()

    cols_to_drop = [
        col for col in COLUMNS_TO_DROP
        if col in df.columns
    ]

    df = df.drop(columns=cols_to_drop)

    return df


def add_metadata(df):
    imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    df["source_file"] = ORDERS_FILE
    df["imported_at"] = imported_at

    df["order_uid"] = (
        df["amazon-order-id"].fillna("").astype(str)
        + "_"
        + df["asin"].fillna("").astype(str)
        + "_"
        + df["purchase-date"].fillna("").astype(str)
    )

    return df


def get_existing_order_uids(conn):
    try:
        existing = pd.read_sql(
            "SELECT order_uid FROM orders",
            conn
        )

        return set(existing["order_uid"].astype(str))

    except Exception:
        return set()


def update_orders():
    ensure_folders()

    file_path = os.path.join(INCOMING_FOLDER, ORDERS_FILE)

    if not os.path.exists(file_path):
        print(f"No orders file found: {file_path}")
        return

    conn = sqlite3.connect(DB_PATH)

    try:
        print("Loading orders file...")
        df = load_orders_txt(file_path)

        print(f"Rows in file: {len(df):,}")

        df = add_metadata(df)

        existing_uids = get_existing_order_uids(conn)

        before = len(df)

        df_new = df[
            ~df["order_uid"].isin(existing_uids)
        ].copy()

        new_rows = len(df_new)
        duplicates = before - new_rows

        print(f"New rows: {new_rows:,}")
        print(f"Duplicates skipped: {duplicates:,}")

        if new_rows > 0:
            df_new = align_df_to_table(
                df_new,
                conn,
                "orders",
            )

            df_new.to_sql(
                "orders",
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

        print("Orders update completed.")

    except Exception as e:
        conn.close()

        print(f"Error: {e}")

        move_file(
            file_path,
            FAILED_FOLDER,
            "failed"
        )

def align_df_to_table(df, conn, table_name):
    table_cols = pd.read_sql(
        f"PRAGMA table_info({table_name})",
        conn,
    )["name"].tolist()

    # Add missing DB columns to dataframe
    for col in table_cols:
        if col not in df.columns:
            df[col] = None

    # Drop extra file columns not in DB
    extra_cols = [col for col in df.columns if col not in table_cols]

    if extra_cols:
        print(f"Dropping extra columns not in DB: {extra_cols}")

    df = df[table_cols]

    return df


if __name__ == "__main__":
    update_orders()
