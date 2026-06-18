import sqlite3
import pandas as pd
from dotenv import load_dotenv

import os

load_dotenv()

DB_PATH = os.getenv("LITET_DB_PATH")
if not DB_PATH:
    raise RuntimeError("LITET_DB_PATH not configured")

#DB_PATH = "/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/Hasten/Reports/SQLite/litet.db"


def load_table(table_name: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(f'SELECT * FROM "{table_name}"', conn)
    conn.close()
    return df


def load_orders() -> pd.DataFrame:
    return load_table("orders")


def load_asins() -> pd.DataFrame:
    return load_table("asins")


def load_ppc() -> pd.DataFrame:
    return load_table("ppc")


def load_transactions() -> pd.DataFrame:
    return load_table("transactions")


def load_inventory_snapshots() -> pd.DataFrame:
    return load_table("inventory_snapshots")


def load_latest_inventory_snapshot() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)

    query = """
        SELECT *
        FROM inventory_snapshots
        WHERE snapshot_date = (
            SELECT MAX(snapshot_date)
            FROM inventory_snapshots
        )
    """

    df = pd.read_sql(query, conn)
    conn.close()
    return df


# Backward compatibility
def load_inv() -> pd.DataFrame:
    return load_latest_inventory_snapshot()


# import subprocess
# import csv
# from io import StringIO
# import pandas as pd


# ACCESS_FILE_ORDERS = "/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/Hasten/Reports/Access Reports/Database1.accdb"
# ACCESS_FILE_INV = "/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/Hasten/Reports/Access Reports/Inventory.accdb"
# ACCESS_FILE_ASINS = "/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/Hasten/Reports/Access Reports/litet_data.accdb"
# ACCESS_FILE_PPC = "/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/Hasten/Reports/Access Reports/ppc_report.accdb"


# def list_tables(access_file: str) -> list[str]:
#     command = ["mdb-tables", "-1", access_file]
#     result = subprocess.run(command, capture_output=True, text=True)

#     if result.returncode != 0:
#         raise RuntimeError(f"Error listing tables: {result.stderr}")

#     return result.stdout.splitlines()


# def get_table_data(access_file: str, table_name: str) -> pd.DataFrame:
#     command = ["mdb-export", "-d", "\t", access_file, table_name]
#     result = subprocess.run(command, capture_output=True, text=True)

#     if result.returncode != 0:
#         raise RuntimeError(f"Error exporting table '{table_name}': {result.stderr}")

#     raw_data = result.stdout
#     reader = csv.reader(StringIO(raw_data), delimiter="\t")
#     rows = list(reader)

#     if not rows:
#         return pd.DataFrame()

#     columns = rows[0]
#     data_rows = rows[1:]

#     clean_rows = [
#         row[:len(columns)] if len(row) > len(columns) else row + [""] * (len(columns) - len(row))
#         for row in data_rows
#     ]

#     return pd.DataFrame(clean_rows, columns=columns)


# def load_orders() -> pd.DataFrame:
#     return get_table_data(ACCESS_FILE_ORDERS, "order_report")


# def load_asins() -> pd.DataFrame:
#     return get_table_data(ACCESS_FILE_ASINS, "ASINs")


# def load_ppc() -> pd.DataFrame:
#     return get_table_data(ACCESS_FILE_PPC, "ppc_report_search")