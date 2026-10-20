"""Rebuild fee-dependent analytics into a new database, preserving the source."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from litet.stage1_mart import (
        _sqlite_ready, build_transaction_mart, build_fee_ledger, build_reconciliation,
    )
    from litet.stage2_cogs import build_sales_profitability, materialize_sales_profitability
    from litet.stage3_ppc import build_stage3, materialize_stage3
except ModuleNotFoundError as error:
    if error.name not in {"litet", "litet.stage1_mart", "litet.stage2_cogs", "litet.stage3_ppc"}:
        raise
    from stage1_mart import (
        _sqlite_ready, build_transaction_mart, build_fee_ledger, build_reconciliation,
    )
    from stage2_cogs import build_sales_profitability, materialize_sales_profitability
    from stage3_ppc import build_stage3, materialize_stage3
from scripts.sync_database import validate


def rebuild(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise ValueError("Destination must be a new file; the source is preserved")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(destination) as conn:
            original.backup(conn)
            read = lambda table: pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
            orders, raw_transactions = read("orders"), read("transactions")
            products, cogs = read("dim_product"), read("cogs_ledger")
            campaigns, raw_ppc = read("campaign_brand_map"), read("ppc")
            previous_count = conn.execute("SELECT COUNT(*) FROM transaction_mart").fetchone()[0]
            previous_fees = conn.execute("SELECT SUM(amazon_fees) FROM transaction_mart").fetchone()[0]
            transactions = build_transaction_mart(raw_transactions, orders, products)
            fees = build_fee_ledger(transactions)
            reconciliation = build_reconciliation(raw_transactions, transactions, fees)
            if reconciliation["unexplained_fee_variance"].abs().max() > .005:
                raise ValueError("Fee reconciliation failed")
            profitability = build_sales_profitability(orders, products, cogs, transactions)
            outputs = build_stage3(raw_ppc, campaigns, profitability, products)
            with conn:
                for table, frame in (
                    ("transaction_mart", transactions), ("fee_ledger", fees),
                    ("fee_reconciliation", reconciliation),
                ):
                    conn.execute(f'DELETE FROM "{table}"')
                    _sqlite_ready(frame).to_sql(table, conn, if_exists="append", index=False)
            materialize_sales_profitability(conn, profitability)
            materialize_stage3(conn, outputs)
            report = {
                "transactions_before": previous_count,
                "transactions_after": len(transactions),
                "amazon_fees_before": previous_fees,
                "amazon_fees_after": float(transactions["amazon_fees"].sum()),
                "sales_rows": len(profitability),
                "fee_reconciliation": "passed",
            }
    validate(destination)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(rebuild(args.source, args.destination), indent=2))


if __name__ == "__main__":
    main()
