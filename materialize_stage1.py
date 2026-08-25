"""Materialize Stage 1 analytics tables into the configured SQLite database."""

import sqlite3

from data import DB_PATH, load_asins, load_orders, load_ppc, load_transactions
from stage1_mart import build_stage1_marts, materialize_stage1


def main():
    marts = build_stage1_marts(
        orders=load_orders(),
        governed_asins=load_asins(),
        ppc=load_ppc(),
        transactions=load_transactions(),
    )
    with sqlite3.connect(DB_PATH) as conn:
        materialize_stage1(conn, marts)
    print("Stage 1 tables materialized successfully.")


if __name__ == "__main__":
    main()
