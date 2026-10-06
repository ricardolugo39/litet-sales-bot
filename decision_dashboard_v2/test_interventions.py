import json
import os
import sqlite3
import tempfile
import unittest

from decision_dashboard_v2.interventions import connect, recent_interventions


class InterventionResultTest(unittest.TestCase):
    def setUp(self):
        self.log = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.facts = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.log.close()
        self.facts.close()
        os.unlink(self.log.name)
        os.environ["HASTEN_DECISION_DB"] = self.log.name
        os.environ["LITET_DB_PATH"] = self.facts.name

        with sqlite3.connect(self.facts.name) as conn:
            conn.execute("""CREATE TABLE ppc_fact_clean (
              report_date TEXT, brand TEXT, campaign_name TEXT, ad_group_name TEXT,
              target TEXT, match_type TEXT, impressions REAL, clicks REAL,
              spend REAL, ad_sales REAL, ad_orders REAL
            )""")
            for day in range(15, 21):
                conn.execute("INSERT INTO ppc_fact_clean VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                    f"2026-09-{day:02d}", "Has10", "Cleat_Covers_Orange",
                    "cleat_covers_orange", "cleats covers", "BROAD",
                    1000, 10, 12, 35, 2,
                ))

        with connect() as conn:
            conn.execute("""INSERT INTO interventions
              (brand,asin,intervention_type,old_value,new_value,period_start,period_end,
               status,campaign_name,entity_type,entity_name,action_type,baseline_json,
               executed_at,ad_group_name,match_type)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                "Has10", "—", "ppc_action", 1.15, .92, "2026-09-01", "2026-09-06",
                "executed", "Cleat_Covers_Orange", "keyword", "cleat covers",
                "reduce_bid", json.dumps({"spend":63.41,"orders":5,"acos":.783}),
                "2026-09-14 12:00:00", "cleat_covers_orange", "BROAD",
            ))

    def tearDown(self):
        os.environ.pop("HASTEN_DECISION_DB", None)
        os.environ.pop("LITET_DB_PATH", None)
        for path in (self.log.name, self.facts.name):
            if os.path.exists(path):
                os.unlink(path)

    def test_zero_exact_activity_is_not_reported_as_missing_data(self):
        row = recent_interventions()[0]
        self.assertEqual(row["post"]["days"], 6)
        self.assertFalse(row["post"]["has_activity"])
        self.assertEqual(row["post"]["impressions"], 0)
        self.assertEqual(row["related_post"]["impressions"], 6000)
        self.assertEqual(row["related_post"]["orders"], 12)
        self.assertIn("traffic appeared on a related keyword", row["result_signal"])

    def test_result_window_stops_at_next_change_to_same_target(self):
        with connect() as conn:
            conn.execute("""INSERT INTO interventions
              (brand,asin,intervention_type,old_value,new_value,period_start,period_end,
               status,campaign_name,entity_type,entity_name,action_type,baseline_json,
               executed_at,ad_group_name,match_type)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                "Has10", "—", "ppc_action", .92, .80, "2026-09-15", "2026-09-18",
                "executed", "Cleat_Covers_Orange", "keyword", "cleat covers",
                "reduce_bid", json.dumps({"spend":48,"orders":8,"acos":.4}),
                "2026-09-18 12:00:00", "cleat_covers_orange", "BROAD",
            ))

        old = next(row for row in recent_interventions() if row["old_value"] == 1.15)
        self.assertEqual(old["post_coverage"]["period_end"], "2026-09-18")
        self.assertEqual(old["post"]["days"], 4)
        self.assertEqual(old["superseded_by"]["new_value"], .80)


if __name__ == "__main__":
    unittest.main()
