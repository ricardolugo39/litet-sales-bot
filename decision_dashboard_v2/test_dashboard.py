import unittest
import os
import tempfile

try:
    from .app import app
except ImportError:
    from app import app


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.log_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.log_file.close()
        os.unlink(self.log_file.name)
        os.environ["HASTEN_DECISION_DB"] = self.log_file.name
        self.client = app.test_client()

    def tearDown(self):
        if os.path.exists(self.log_file.name):
            os.unlink(self.log_file.name)

    def test_default_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"HASTEN", response.data)
        self.assertIn(b"TaCoS", response.data)
        self.assertIn(b"Growth and adoption", response.data)
        self.assertIn(b"Three priorities", response.data)
        self.assertIn(b"white cycling socks", response.data)
        self.assertIn(b"Do not change PPC because of this 3-pack decline", response.data)
        self.assertIn(b"Estimated P&amp;L", response.data)
        self.assertIn(b"08/26 MTD", response.data)
        self.assertIn(b"23.0%", response.data)
        self.assertIn(b"Monthly ordered sales ($) + TaCoS (%)", response.data)
        self.assertIn(b"$2.3k", response.data)

    def test_brand_and_period_filter(self):
        response = self.client.get(
            "/?brand=Has10&period=2026-08-01%7C2026-08-16"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Has10", response.data)
        self.assertIn(b"Seasonal scale and availability", response.data)
        self.assertIn(b"Three priorities", response.data)
        self.assertIn(b"orange cleat covers", response.data)
        self.assertIn(b"Keep the $13.99 base price", response.data)
        self.assertIn(b"Why Amazon costs are 45.1%", response.data)
        self.assertIn(b"Maximum ads to break even", response.data)
        self.assertIn(b"Bring TaCoS below 30%", response.data)
        self.assertNotIn(b"white cycling socks", response.data)

    def test_homepage_exposes_brand_specific_operating_modes(self):
        litet=self.client.get("/?brand=Litet")
        has10=self.client.get("/?brand=Has10")
        self.assertIn(b"Growth and adoption",litet.data)
        self.assertIn(b"10.0% operating floor",litet.data)
        self.assertIn(b"Seasonal scale and availability",has10.data)
        self.assertIn(b"5.0% operating floor",has10.data)
        for response in (litet,has10):
            self.assertIn(b"What not to change",response.data)
            self.assertIn(b"Medium confidence",response.data)

    def test_has10_latest_period_handles_queries_without_sales(self):
        response = self.client.get(
            "/?brand=Has10&period=2026-08-01%7C2026-08-23"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Has10", response.data)
        self.assertIn(b"orange cleat covers", response.data)

    def test_current_month_filter_is_consolidated(self):
        from decision_dashboard_v2.analytics import ppc_periods
        august = [p for p in ppc_periods() if p["period_start"].startswith("2026-08")]
        self.assertEqual(len(august), 1)
        self.assertEqual(august[0]["period_start"], "2026-08-01")
        self.assertEqual(august[0]["period_end"], "2026-08-23")

    def test_monthly_trend_contains_consolidated_current_mtd(self):
        from decision_dashboard_v2.analytics import monthly_trend
        august = [r for r in monthly_trend("Litet") if r["period_start"] == "2026-08-01"]
        self.assertEqual(len(august), 1)
        self.assertEqual(august[0]["period_end"], "2026-08-23")
        self.assertTrue(august[0]["is_partial"])
        self.assertGreater(august[0]["ordered_sales"], 0)

    def test_pnl_displays_cogs_and_reconciles_to_contribution(self):
        from decision_dashboard_v2.analytics import pnl_statement
        pnl = pnl_statement("2026-08-01", "2026-08-23", "Litet")
        reconciled = pnl["gross_sales"] - pnl["amazon_costs_ex_ads"] - pnl["ad_spend"] - pnl["cogs"]
        self.assertAlmostEqual(reconciled, pnl["contribution"], places=6)
        response = self.client.get("/?brand=Litet&period=2026-08-01%7C2026-08-23")
        self.assertIn(b"Estimated COGS", response.data)

    def test_has10_product_page_uses_has10_diagnosis(self):
        response = self.client.get(
            "/products?brand=Has10&period=2026-08-01%7C2026-08-16"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Price is not the first problem", response.data)
        self.assertNotIn(b"road cycling socks", response.data)
        self.assertIn(b"Brand seasonality", response.data)
        self.assertIn(b"2024 packages", response.data)
        self.assertNotIn(b"Physical pairs", response.data)

    def test_litet_seasonality_shows_packages_and_physical_pairs(self):
        response = self.client.get(
            "/products?brand=Litet&period=2026-08-01%7C2026-08-16"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"packages", response.data)
        self.assertIn(b"Physical pairs", response.data)
        self.assertIn(b"a 3-pack or 6-pack counts as one", response.data)

    def test_litet_product_portfolio_covers_every_pack_and_sku_layer(self):
        response = self.client.get(
            "/products?brand=Litet&period=2026-08-01%7C2026-08-23"
        )
        self.assertEqual(response.status_code, 200)
        for marker in (b"Complete Litet portfolio", b"Pack-family decisions",
                       b"3-pack", b"6-pack", b"single", b"By color", b"By size",
                       b"All ASIN and SKU evidence", b"Healthy\xe2\x80\x94no action"):
            self.assertIn(marker, response.data)

    def test_has10_product_portfolio_uses_same_complete_framework(self):
        from decision_dashboard_v2.analytics import product_portfolio
        portfolio = product_portfolio("2026-08-01", "2026-08-23", "Has10")
        self.assertEqual(portfolio["coverage"]["asins"],
                         sum(group["asins"] for group in portfolio["pack_groups"]))
        self.assertGreater(portfolio["coverage"]["skus"], portfolio["coverage"]["asins"])
        self.assertEqual(sum(portfolio["coverage"]["status_counts"].values()),
                         portfolio["coverage"]["asins"])
        response = self.client.get(
            "/products?brand=Has10&period=2026-08-01%7C2026-08-23"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Complete Has10 portfolio", response.data)
        self.assertIn(b"Seller SKUs mapped", response.data)

    def test_litet_product_actions_name_both_controllable_levers(self):
        response = self.client.get(
            "/products?brand=Litet&period=2026-08-01%7C2026-08-23"
        )
        self.assertIn(b"PPC portfolio strategy", response.data)
        self.assertIn(b"Secondary test candidate", response.data)
        self.assertIn(b"Black Large/X-Large", response.data)
        self.assertIn(b"10\xe2\x80\x9315% of the hero budget", response.data)
        for marker in (b"Pricing:", b"PPC:", b"Measure:", b"Limitation:"):
            self.assertIn(marker, response.data)

    def test_decisions_reuses_product_recommendations(self):
        response = self.client.get(
            "/decisions?brand=Litet&period=2026-08-01%7C2026-08-23"
        )
        self.assertEqual(response.status_code, 200)
        for marker in (b"Coordinated cases", b"PPC hero", b"Secondary test",
                       b"Evidence limitation"):
            self.assertIn(marker, response.data)

    def test_has10_ppc_playbook_shows_campaign_location(self):
        response = self.client.get(
            "/ppc?brand=Has10&period=2026-08-01%7C2026-08-16"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PPC actions", response.data)
        self.assertIn(b"Decision timeframe", response.data)
        self.assertIn(b"Customer search term", response.data)
        self.assertIn(b"Campaign", response.data)
        self.assertIn(b"Has10 | Blue | Historic Keywords", response.data)
        self.assertIn(b"Targeting keyword", response.data)
        self.assertIn(b"cleat covers", response.data)
        self.assertIn(b"Keyword opportunities", response.data)
        self.assertIn(b"youth cleat covers", response.data)
        self.assertIn(b"Harvest into EXACT", response.data)
        self.assertIn(b"Campaign", response.data)

    def test_litet_ppc_playbook_shows_campaign_and_organic_evidence(self):
        response = self.client.get(
            "/ppc?brand=Litet&period=2026-08-01%7C2026-08-16"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PPC actions", response.data)
        self.assertIn(b"LITET Ranking Campaign", response.data)
        self.assertIn(b"Organic #", response.data)
        self.assertIn(b"Targeting keyword", response.data)
        self.assertIn(b"Targeting decisions", response.data)
        self.assertIn(b"Customer search-term evidence", response.data)
        self.assertIn(b"$236.93", response.data)
        self.assertIn(b"Keyword opportunities", response.data)
        self.assertIn(b"aero cycling socks", response.data)
        self.assertIn(b"Where Litet can close the visibility gap", response.data)
        self.assertIn(b"Selected-period PPC evidence", response.data)
        self.assertIn(b"Matching query", response.data)
        self.assertIn(b"PPC spend vs total ordered units", response.data)
        self.assertIn(b"March 2026", response.data)
        self.assertIn(b"QTD", response.data)
        self.assertIn(b"YTD", response.data)
        self.assertIn(b"Blue portion", response.data)
        self.assertIn(b"Helium 10 30-day snapshot", response.data)
        self.assertLess(response.data.index(b"Targeting decisions"),
                        response.data.index(b"Keyword opportunities"))

    def test_ppc_targets_are_grouped_by_campaign(self):
        from decision_dashboard_v2.analytics import keyword_playbook
        playbook = keyword_playbook("2026-08-01", "2026-08-16", "Litet")
        campaigns = [row["campaign_name"].lower() for row in playbook["targets"]]
        self.assertEqual(campaigns, sorted(campaigns))
        self.assertTrue(playbook["campaigns"])
        self.assertTrue(any(c["open"] for c in playbook["campaigns"]))
        self.assertEqual(sum(len(c["targets"]) for c in playbook["campaigns"]),
                         len(playbook["targets"]))
        self.assertTrue(any(r["decision"].startswith("Increase")
                            for r in playbook["targets"]))
        self.assertTrue(all(r["confidence"] in {"Low","Medium","High"}
                            for r in playbook["targets"]))

    def test_all_v2_pages(self):
        query = "?brand=Litet&period=2026-08-01%7C2026-08-16"
        for path, marker in (("/products", b"Parent competitive context"),
                             ("/ppc", b"PPC + organic"),
                             ("/decisions", b"Coordinated cases"),
                             ("/decisions/pricing", b"Contribution-preservation scenarios")):
            response = self.client.get(path + query)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(marker, response.data, path)

    def test_global_qtd_and_ytd_filters_render_across_tabs(self):
        for period in ("2026-07-01%7C2026-08-16", "2026-01-01%7C2026-08-16"):
            for path in ("/", "/products", "/ppc", "/decisions"):
                response=self.client.get(f"{path}?brand=Litet&period={period}")
                self.assertEqual(response.status_code,200,(path,period))
                self.assertIn(b"Quick ranges",response.data)
                self.assertIn(b"Monthly periods",response.data)

    def test_ppc_all_brands_renders_without_missing_trend_fields(self):
        response=self.client.get("/ppc?brand=All")
        self.assertEqual(response.status_code,200)
        self.assertIn(b"Select Litet or Has10",response.data)

    def test_invalid_period_falls_back_to_default_period(self):
        response=self.client.get("/ppc?brand=Litet&period=2026-08-01")
        self.assertEqual(response.status_code,200)
        self.assertIn(b"PPC + organic",response.data)

    def test_price_test_is_logged_but_not_executed(self):
        response = self.client.post("/decisions/pricing/approve", data={
            "brand":"Litet", "asin":"B0DSCFMCQD", "old_value":"14.99",
            "new_value":"13.99", "period_start":"2026-08-01", "period_end":"2026-08-16",
            "required_lift":"0.25"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Intervention log", response.data)
        self.assertIn(b"B0DSCFMCQD", response.data)

    def test_pricing_case_uses_trailing_settled_history(self):
        response = self.client.get(
            "/decisions/pricing?brand=Litet&period=2026-08-01%7C2026-08-16&asin=B0DSCFMCQD"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Prior 6 settled months", response.data)
        self.assertIn(b"Historical price and conversion context", response.data)
        self.assertIn(b"placeholder seed", response.data)
        self.assertIn(b"2026-08 MTD", response.data)
        self.assertIn(b"Incomplete period", response.data)

    def test_high_volume_pricing_case_uses_historical_baseline(self):
        response = self.client.get(
            "/decisions/pricing?brand=Litet&period=2026-08-01%7C2026-08-16&asin=B0FFPT16G6"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Price decision supported", response.data)
        self.assertIn(b"Completed-month price bands", response.data)
        self.assertIn(b"Hold $39.99", response.data)
        self.assertNotIn(b"Use a longer settled economics window", response.data)
        self.assertIn(b"ASIN seasonality", response.data)
        self.assertIn(b"MTD pace", response.data)


if __name__ == "__main__":
    unittest.main()
