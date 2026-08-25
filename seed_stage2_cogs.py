"""Seed placeholder COGS and refresh the as-of-sale profitability mart."""

import sqlite3
from pathlib import Path

import pandas as pd

from data import DB_PATH, load_orders
from stage2_cogs import (
    apply_stage2_schema,
    build_sales_profitability,
    materialize_sales_profitability,
    backdate_placeholder_seeds,
    seed_cogs_ledger,
)


def main():
    seed_path = Path(__file__).with_name("seeds") / "cogs_placeholder_seed.csv"
    with sqlite3.connect(DB_PATH) as conn:
        apply_stage2_schema(conn)
        earliest_sale = pd.read_sql(
            """
            SELECT MIN(date("purchase-date")) AS earliest
            FROM orders
            WHERE "sales-channel" = 'Amazon.com'
              AND CAST(quantity AS REAL) > 0
            """,
            conn,
        ).iloc[0]["earliest"]
        effective_start = pd.to_datetime(earliest_sale).date().isoformat()
        inserted = seed_cogs_ledger(conn, seed_path, effective_start)
        backdated = backdate_placeholder_seeds(conn, effective_start)
        dim = pd.read_sql("SELECT * FROM dim_product", conn)
        cogs = pd.read_sql("SELECT * FROM cogs_ledger", conn)
        transaction_mart = pd.read_sql("SELECT * FROM transaction_mart", conn)
        profitability = build_sales_profitability(
            load_orders(), dim, cogs, transaction_mart
        )
        materialize_sales_profitability(conn, profitability)
    print(
        f"Stage 2 seeded ({inserted} new rows; {backdated} backdated; "
        f"effective {effective_start}) "
        f"and profitability refreshed ({len(profitability)} rows)."
    )


if __name__ == "__main__":
    main()
