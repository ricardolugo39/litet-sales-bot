import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from stage2_cogs import (
    apply_stage2_schema,
    backdate_placeholder_seeds,
    enrich_sales_with_asof_cogs,
    record_vendor_receipt,
    seed_cogs_ledger,
)


class Stage2CogsTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE inventory_snapshots (
                asin TEXT, snapshot_date TEXT, "Quantity Available" TEXT
            )
            """
        )
        apply_stage2_schema(self.conn)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.seed_path = Path(self.temp_dir.name) / "seed.csv"
        self.seed_path.write_text(
            "asin,product_name,product_category,type,sku,cogs\n"
            "A1,Product One,Test,single,0,2.0\n"
            "XXXXXXXXX,Excluded,Test,single,0,99.0\n"
        )

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_seed_is_idempotent_and_excludes_fake_asin(self):
        self.assertEqual(seed_cogs_ledger(self.conn, self.seed_path, "2026-01-01"), 1)
        self.assertEqual(seed_cogs_ledger(self.conn, self.seed_path, "2026-01-01"), 0)
        rows = self.conn.execute(
            "select asin, unit_cogs, source, is_current from cogs_ledger"
        ).fetchall()
        self.assertEqual(rows, [("A1", 2.0, "placeholder_seed", 1)])

    def test_receipt_recalculates_weighted_average_and_closes_prior_row(self):
        seed_cogs_ledger(self.conn, self.seed_path, "2026-01-01")
        self.conn.execute(
            "insert into inventory_snapshots values ('A1', '2026-02-01', '10')"
        )
        result = record_vendor_receipt(
            self.conn,
            asin="A1",
            received_date="2026-02-10",
            quantity_received=10,
            unit_cost=4,
            receipt_id="R-1",
        )
        self.assertAlmostEqual(result["new_avg_cost"], 3.0)
        ledger = self.conn.execute(
            """
            select unit_cogs, effective_start, effective_end, is_current, source
            from cogs_ledger where asin='A1' order by effective_start
            """
        ).fetchall()
        self.assertEqual(ledger[0], (2.0, "2026-01-01", "2026-02-10", 0, "placeholder_seed"))
        self.assertEqual(ledger[1], (3.0, "2026-02-10", None, 1, "vendor_receipt"))

    def test_backdate_extends_seed_but_does_not_change_receipt_boundary(self):
        seed_cogs_ledger(self.conn, self.seed_path, "2026-01-01")
        record_vendor_receipt(
            self.conn,
            asin="A1",
            received_date="2026-02-10",
            quantity_received=5,
            unit_cost=4,
            receipt_id="R-backdate",
        )
        self.assertEqual(backdate_placeholder_seeds(self.conn, "2023-01-01"), 1)
        rows = self.conn.execute(
            """
            SELECT source, effective_start, effective_end
            FROM cogs_ledger WHERE asin = 'A1' ORDER BY effective_start
            """
        ).fetchall()
        self.assertEqual(
            rows,
            [
                ("placeholder_seed", "2023-01-01", "2026-02-10"),
                ("vendor_receipt", "2026-02-10", None),
            ],
        )

    def test_missing_inventory_is_flagged_and_uses_batch_cost(self):
        seed_cogs_ledger(self.conn, self.seed_path, "2026-01-01")
        result = record_vendor_receipt(
            self.conn,
            asin="A1",
            received_date="2026-02-10",
            quantity_received=5,
            total_cost_paid=25,
            receipt_id="R-2",
        )
        self.assertEqual(result["prior_on_hand_qty"], 0)
        self.assertEqual(result["new_avg_cost"], 5)
        self.assertEqual(
            result["inventory_qty_status"], "missing_asin_snapshot_default_zero"
        )

    def test_asof_sale_cogs_keeps_missing_explicit(self):
        ledger = pd.DataFrame(
            [
                {
                    "cogs_ledger_key": "old", "asin": "A1", "unit_cogs": 2.0,
                    "effective_start": "2026-01-01", "effective_end": "2026-02-10",
                },
                {
                    "cogs_ledger_key": "new", "asin": "A1", "unit_cogs": 3.0,
                    "effective_start": "2026-02-10", "effective_end": None,
                },
            ]
        )
        sales = pd.DataFrame(
            [
                {"asin": "A1", "purchase-date": "2025-12-31", "quantity": "1", "item-price": "10"},
                {"asin": "A1", "purchase-date": "2026-01-15", "quantity": "2", "item-price": "20"},
                {"asin": "A1", "purchase-date": "2026-02-10", "quantity": "1", "item-price": "10"},
                {"asin": "MISSING", "purchase-date": "2026-02-11", "quantity": "1", "item-price": "10"},
            ]
        )
        result = enrich_sales_with_asof_cogs(sales, ledger)
        self.assertEqual(result["cogs_status"].tolist(), ["missing", "available", "available", "missing"])
        self.assertTrue(pd.isna(result.iloc[0]["cogs_amount"]))
        self.assertEqual(result.iloc[1]["cogs_amount"], 4)
        self.assertEqual(result.iloc[2]["unit_cogs"], 3)
        self.assertTrue(pd.isna(result.iloc[3]["cogs_amount"]))


if __name__ == "__main__":
    unittest.main()
