import unittest

import pandas as pd

from stage3_ppc import build_clean_ppc_fact, build_negative_keyword_candidates


def ppc_row(**overrides):
    row = {
        "Date": "2026-01-01",
        "Campaign Name": "LITET Launch",
        "Ad Group Name": "Group",
        "Targeting": "cycling socks",
        "Match Type": "BROAD",
        "Customer Search Term": "aero cycling socks",
        "Impressions": "10",
        "Clicks": "1",
        "Spend": "2",
        "7 Day Total Sales": "0",
        "7 Day Total Orders (#)": "0",
        "7 Day Total Units (#)": "0",
        "7 Day Advertised SKU Units (#)": "0",
        "7 Day Other SKU Units (#)": "0",
        "7 Day Advertised SKU Sales": "0",
        "7 Day Other SKU Sales": "0",
        "ID": "1",
        "ID1": "",
        "source_file": None,
        "imported_at": "2026-01-02",
        "ppc_uid": None,
    }
    row.update(overrides)
    return row


class Stage3PpcTests(unittest.TestCase):
    def setUp(self):
        self.campaign_map = pd.DataFrame(
            [
                {"campaign_name": "LITET Launch", "brand": "Litet"},
                {"campaign_name": "Generic", "brand": "Has10"},
            ]
        )

    def test_dedup_prefers_most_complete_cumulative_snapshot(self):
        raw = pd.DataFrame(
            [
                ppc_row(ID="10", Impressions="10", Clicks="1", Spend="2"),
                ppc_row(ID="11", Impressions="20", Clicks="2", Spend="4"),
            ]
        )
        clean, findings = build_clean_ppc_fact(raw, self.campaign_map)
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean.iloc[0]["clicks"], 2)
        self.assertEqual(clean.iloc[0]["selected_source_id"], "11")
        self.assertEqual(
            clean.iloc[0]["dedup_rule"], "most_complete_cumulative_snapshot"
        )
        self.assertEqual(findings["blank_ppc_uid_rows"], 2)

    def test_exact_duplicate_uses_stable_source_id_tiebreaker(self):
        raw = pd.DataFrame([ppc_row(ID="10"), ppc_row(ID="12")])
        clean, _ = build_clean_ppc_fact(raw, self.campaign_map)
        self.assertEqual(clean.iloc[0]["selected_source_id"], "12")
        self.assertEqual(
            clean.iloc[0]["dedup_rule"], "exact_business_duplicate_collapsed"
        )

    def test_campaign_brand_map_is_reused_and_required(self):
        raw = pd.DataFrame([ppc_row(**{"Campaign Name": "Generic"})])
        clean, _ = build_clean_ppc_fact(raw, self.campaign_map)
        self.assertEqual(clean.iloc[0]["brand"], "Has10")
        with self.assertRaises(ValueError):
            build_clean_ppc_fact(raw, self.campaign_map.iloc[:1])

    def test_negative_candidate_uses_margin_allowance(self):
        raw = pd.DataFrame(
            [
                ppc_row(
                    Date=f"2026-01-{day:02d}",
                    Spend="3",
                    Clicks="2",
                    Impressions="20",
                )
                for day in range(1, 4)
            ]
        )
        fact, _ = build_clean_ppc_fact(raw, self.campaign_map)
        benchmarks = pd.DataFrame(
            [
                {
                    "brand": "Litet", "product_family": "Socks",
                    "break_even_acos": 0.2, "average_order_revenue": 30,
                },
                {
                    "brand": "Litet", "product_family": "All",
                    "break_even_acos": 0.2, "average_order_revenue": 30,
                },
            ]
        )
        candidates = build_negative_keyword_candidates(fact, benchmarks, lookback_days=30)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates.iloc[0]["recommendation"], "negative_exact")
        self.assertEqual(candidates.iloc[0]["break_even_spend_allowance"], 6)


if __name__ == "__main__":
    unittest.main()
