"""Build and materialize the clean PPC and profit-aware advertising marts."""

import sqlite3

import pandas as pd

from data import DB_PATH, load_ppc
from stage3_ppc import build_stage3, materialize_stage3


def main():
    with sqlite3.connect(DB_PATH) as conn:
        campaign_map = pd.read_sql("SELECT * FROM campaign_brand_map", conn)
        profitability = pd.read_sql("SELECT * FROM sales_profitability", conn)
        dim_product = pd.read_sql("SELECT * FROM dim_product", conn)
        outputs = build_stage3(load_ppc(), campaign_map, profitability, dim_product)
        materialize_stage3(conn, outputs)
    print(
        "Stage 3 materialized:",
        outputs["findings"],
        f"negative_candidates={len(outputs['ppc_negative_keyword_candidates'])}",
    )


if __name__ == "__main__":
    main()
