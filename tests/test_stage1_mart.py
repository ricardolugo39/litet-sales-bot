import sqlite3
import unittest

import pandas as pd

from stage1_mart import build_stage1_marts, materialize_stage1


class Stage1MartTests(unittest.TestCase):
    def setUp(self):
        self.orders = pd.DataFrame(
            [
                {
                    "amazon-order-id": "L-1", "purchase-date": "2026-01-01",
                    "sales-channel": "Amazon.com", "quantity": "1",
                    "item-price": "20", "asin": "L-ASIN", "sku": "L-SKU",
                    "product-name": "LITET Socks",
                },
                {
                    "amazon-order-id": "H-1", "purchase-date": "2026-01-02",
                    "sales-channel": "Amazon.com", "quantity": "1",
                    "item-price": "15", "asin": "H-ASIN", "sku": "H-SKU",
                    "product-name": "Hasten Cleat Covers (Black, Youth)",
                },
                {
                    "amazon-order-id": "H-2", "purchase-date": "2026-02-02",
                    "sales-channel": "Amazon.com", "quantity": "1",
                    "item-price": "15", "asin": "H-ASIN", "sku": "H-SKU",
                    "product-name": "Unbranded Cleat Covers (Black, Youth)",
                },
            ]
        )
        self.asins = pd.DataFrame(
            [{"ASIN": "L-ASIN", "Item": "White, Small/Medium", "Type": "single"}]
        )
        self.ppc = pd.DataFrame(
            [
                {"Campaign Name": "LITET Launch", "Spend": "10"},
                {"Campaign Name": "Generic Black", "Spend": "20"},
            ]
        )
        base_transaction = {
            "Date": "1/3/2026",
            "Transaction type": "Order Payment",
            "Order ID": "L-1",
            "Product Details": "LITET Socks",
            "Total product charges": "20",
            "Total promotional rebates": "0",
            "Amazon fees": "-6",
            "Other": "0",
            "Total (USD)": "14",
            "source_file": "transactions.csv",
            "imported_at": "2026-01-04",
            "transaction_uid": "uid-1",
        }
        self.transactions = pd.DataFrame(
            [
                {**base_transaction, "Transaction Status": "Deferred"},
                {**base_transaction, "Transaction Status": "Released", "imported_at": "2026-01-05"},
                {
                    **base_transaction,
                    "Transaction Status": "Released",
                    "Date": "1/4/2026",
                    "Order ID": "---",
                    "Transaction type": "Service Fees",
                    "Product Details": "FBA Inventory Storage Fee",
                    "Total product charges": "0",
                    "Amazon fees": "-2",
                    "Other": "-1",
                    "Total (USD)": "-3",
                    "transaction_uid": "uid-2",
                },
            ]
        )

    def test_alias_resolution_and_campaign_rule(self):
        marts = build_stage1_marts(self.orders, self.asins, self.ppc, self.transactions)
        brands = marts.dim_product.set_index("asin")["canonical_brand"].to_dict()
        self.assertEqual(brands, {"L-ASIN": "Litet", "H-ASIN": "Has10"})
        aliases = marts.product_title_alias
        unbranded = aliases[aliases["title_alias"].str.startswith("Unbranded")].iloc[0]
        self.assertEqual(unbranded["canonical_brand"], "Has10")
        campaign_map = marts.campaign_brand_map.set_index("campaign_name")["brand"].to_dict()
        self.assertEqual(campaign_map["LITET Launch"], "Litet")
        self.assertEqual(campaign_map["Generic Black"], "Has10")

    def test_lifecycle_fee_ledger_and_reconciliation(self):
        marts = build_stage1_marts(self.orders, self.asins, self.ppc, self.transactions)
        order_payment = marts.transaction_mart[
            marts.transaction_mart["transaction_type"].eq("Order Payment")
        ]
        self.assertEqual(len(order_payment), 1)
        self.assertEqual(order_payment.iloc[0]["transaction_status"], "Released")
        self.assertEqual(order_payment.iloc[0]["brand"], "Litet")

        storage = marts.fee_ledger[
            marts.fee_ledger["fee_subcategory"].eq("FBA inventory storage")
        ]
        self.assertEqual(storage["fee_amount"].sum(), -3)
        self.assertTrue(storage["brand"].eq("Unassigned").all())

        all_row = marts.reconciliation.set_index("brand").loc["All"]
        self.assertEqual(all_row["resolved_transaction_rows"], 2)
        self.assertEqual(all_row["matched_rows"], 1)
        self.assertAlmostEqual(all_row["unexplained_fee_variance"], 0)
        self.assertAlmostEqual(all_row["transaction_identity_variance"], 0)

    def test_materialization_is_idempotent(self):
        marts = build_stage1_marts(self.orders, self.asins, self.ppc, self.transactions)
        conn = sqlite3.connect(":memory:")
        materialize_stage1(conn, marts)
        materialize_stage1(conn, marts)
        self.assertEqual(conn.execute("select count(*) from dim_product").fetchone()[0], 2)
        self.assertEqual(conn.execute("select count(*) from campaign_brand_map").fetchone()[0], 2)
        self.assertEqual(conn.execute("select count(*) from transaction_mart").fetchone()[0], 2)
        self.assertEqual(conn.execute("select count(*) from fee_ledger").fetchone()[0], 3)
        conn.close()


if __name__ == "__main__":
    unittest.main()
