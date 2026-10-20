import unittest
import os
import sqlite3
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

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
        if self._testMethodName.startswith("test_price_change_"):
            clock = patch("decision_dashboard_v2.analytics.datetime", wraps=datetime)
            mocked_clock = clock.start()
            mocked_clock.now.return_value = datetime(2026, 10, 19, 12, tzinfo=ZoneInfo("America/Los_Angeles"))
            self.addCleanup(clock.stop)

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
        self.assertIn(b"Stop PPC budget increases", response.data)
        self.assertIn(b"Do not change price from four days of demand", response.data)
        self.assertIn(b"Confirm replenishment", response.data)
        self.assertIn(b"Estimated P&amp;L", response.data)
        self.assertIn(b'data-label="08/26"', response.data)
        self.assertIn(b"10/26 MTD", response.data)
        self.assertIn(b"Monthly ordered sales ($) + TaCoS (%)", response.data)

    def test_prime_event_uses_all_litet_sales_and_applies_event_fees(self):
        from decision_dashboard_v2.analytics import prime_big_deals_performance

        database = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        database.close()
        try:
            with sqlite3.connect(database.name) as conn:
                conn.executescript("""
                    CREATE TABLE dim_product (
                      asin TEXT, canonical_brand TEXT, canonical_product_name TEXT,
                      color TEXT, size TEXT, pack_type TEXT
                    );
                    CREATE TABLE orders (
                      "amazon-order-id" TEXT, asin TEXT, "purchase-date" TEXT,
                      quantity REAL, "item-price" REAL,
                      "item-promotion-discount" REAL,
                      "order-status" TEXT, "item-status" TEXT
                    );
                    CREATE TABLE sales_profitability (
                      order_id TEXT, asin TEXT, sale_date TEXT, brand TEXT,
                      cogs_amount REAL, amazon_fees REAL,
                      cogs_status TEXT, fee_status TEXT
                    );
                    CREATE TABLE cogs_ledger (
                      asin TEXT, unit_cogs REAL, effective_start TEXT,
                      effective_end TEXT
                    );
                    CREATE TABLE asin_economics (
                      period_start TEXT, period_end TEXT, asin TEXT,
                      net_sales REAL, net_units_sold REAL,
                      fba_fulfillment_fees REAL, referral_fee REAL,
                      referral_fee_refunds REAL
                    );
                    CREATE TABLE ppc_fact_clean (
                      report_date TEXT, campaign_name TEXT, brand TEXT,
                      spend REAL, ad_sales REAL
                    );
                    INSERT INTO dim_product VALUES
                      ('L1','Litet','Litet one','White','M','single'),
                      ('L2','Litet','Litet two','Black','L','3-pack'),
                      ('H1','Has10','Has10 item','Orange',NULL,'single');
                    INSERT INTO orders VALUES
                      ('O1','L1','2026-10-06T08:30:00+00:00',2,100,10,'Shipped','Shipped'),
                      ('O2','L2','2026-10-06T19:00:00+00:00',1,60,0,'Shipped','Shipped'),
                      ('O3','H1','2026-10-06T10:00:00+00:00',1,500,0,'Shipped','Shipped'),
                      ('O4','L1','2026-10-08T08:01:00+00:00',1,999,0,'Shipped','Shipped'),
                      ('O6','L1','2026-10-06T03:00:00+00:00',1,777,0,'Shipped','Shipped'),
                      ('O5','L1','2026-10-06T09:00:00+00:00',1,50,0,'Cancelled','Cancelled');
                    INSERT INTO sales_profitability VALUES
                      ('O1','L1','2026-10-06','Litet',40,-20,'available','exact_order_fee_allocated'),
                      ('O2','L2','2026-10-07','Litet',15,-10,'available','exact_order_fee_allocated');
                    INSERT INTO cogs_ledger VALUES
                      ('L1',20,'2026-01-01',NULL),
                      ('L2',15,'2026-01-01',NULL);
                    INSERT INTO ppc_fact_clean VALUES
                      ('2026-10-06','LITET ranking','Litet',12,30),
                      ('2026-10-07','Litet discovery','Litet',8,20),
                      ('2026-10-06','Has10 exact','Has10',200,400),
                      ('2026-10-06','Has10 mislabeled','Litet',300,600);
                """)
            with patch.dict(os.environ, {"LITET_DB_PATH": database.name}):
                result = prime_big_deals_performance()
                response = self.client.get("/events/prime-big-deals-2026")
            self.assertEqual(result["sales"], 150)
            self.assertEqual(result["discounts"], 10)
            self.assertEqual(result["units"], 3)
            self.assertEqual(result["orders"], 2)
            self.assertEqual(result["ad_spend"], 20)
            self.assertAlmostEqual(result["variable_fee"], 2.25)
            self.assertAlmostEqual(result["deal_fee"], 102.25)
            self.assertAlmostEqual(result["profit"], -57.25)
            self.assertAlmostEqual(result["roi"], -57.25 / 102.25)
            self.assertAlmostEqual(
                sum(day["profit_after_ppc"] or 0 for day in result["daily"]),
                result["profit"],
            )
            self.assertEqual(result["daily"][1]["profit_after_ppc"], -8)
            self.assertTrue(result["complete"])
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Prime Big Deal Days", response.data)
            self.assertIn(b"5490b198-4bcc-49f7-add2-8099c6da5c3c", response.data)
            self.assertIn(b"-$57.25", response.data)
            self.assertIn(b"Profit after PPC", response.data)
        finally:
            os.unlink(database.name)

    def test_prime_event_withholds_profit_when_exact_fees_are_missing(self):
        from decision_dashboard_v2.analytics import prime_big_deals_performance

        database = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        database.close()
        try:
            with sqlite3.connect(database.name) as conn:
                conn.executescript("""
                    CREATE TABLE dim_product (
                      asin TEXT, canonical_brand TEXT, canonical_product_name TEXT,
                      color TEXT, size TEXT, pack_type TEXT
                    );
                    CREATE TABLE orders (
                      "amazon-order-id" TEXT, asin TEXT, "purchase-date" TEXT,
                      quantity REAL, "item-price" REAL,
                      "item-promotion-discount" REAL,
                      "order-status" TEXT, "item-status" TEXT
                    );
                    CREATE TABLE sales_profitability (
                      order_id TEXT, asin TEXT, sale_date TEXT, brand TEXT,
                      cogs_amount REAL, amazon_fees REAL,
                      cogs_status TEXT, fee_status TEXT
                    );
                    CREATE TABLE cogs_ledger (
                      asin TEXT, unit_cogs REAL, effective_start TEXT,
                      effective_end TEXT
                    );
                    CREATE TABLE asin_economics (
                      period_start TEXT, period_end TEXT, asin TEXT,
                      net_sales REAL, net_units_sold REAL,
                      fba_fulfillment_fees REAL, referral_fee REAL,
                      referral_fee_refunds REAL
                    );
                    CREATE TABLE ppc_fact_clean (
                      report_date TEXT, campaign_name TEXT, brand TEXT,
                      spend REAL, ad_sales REAL
                    );
                    INSERT INTO dim_product VALUES
                      ('L1','Litet','Litet one','White','M','single');
                    INSERT INTO orders VALUES
                      ('O1','L1','2026-10-06',1,100,10,'Shipped','Shipped');
                    INSERT INTO cogs_ledger VALUES
                      ('L1',5,'2026-01-01',NULL);
                    INSERT INTO asin_economics VALUES
                      ('2026-09-01','2026-09-30','L1',100,10,-20,-10,0);
                """)
            with patch.dict(os.environ, {"LITET_DB_PATH": database.name}):
                result = prime_big_deals_performance()
            self.assertFalse(result["complete"])
            self.assertIsNone(result["profit"])
            self.assertIsNone(result["roi"])
            self.assertEqual(result["deal_fee"], 101.35)
            self.assertEqual(result["cogs"], 5)
            self.assertEqual(result["normal_fixed_fees"], 2)
            self.assertAlmostEqual(result["normal_variable_fees"], 15.30)
            self.assertAlmostEqual(result["amazon_fees"], 17.30)
            self.assertAlmostEqual(result["profit_before_ppc"], -33.65)
            self.assertEqual(result["estimated_fee_coverage"], 1)
        finally:
            os.unlink(database.name)

    def test_clothing_referral_fee_uses_price_tiers_and_per_item_minimum(self):
        from decision_dashboard_v2.analytics import clothing_referral_fee

        self.assertEqual(clothing_referral_fee(10, 1), (.50, .05))
        self.assertEqual(clothing_referral_fee(18, 1), (1.80, .10))
        fee, rate = clothing_referral_fee(39.99, 1)
        self.assertAlmostEqual(fee, 6.7983)
        self.assertEqual(rate, .17)
        self.assertEqual(clothing_referral_fee(2, 1), (.30, .05))

    def test_amazon_us_business_date_converts_utc_to_pacific(self):
        from decision_dashboard_v2.analytics import amazon_us_date, midpoint_arc_elasticity

        self.assertEqual(amazon_us_date("2026-10-07T04:10:06+00:00"), "2026-10-06")
        self.assertEqual(amazon_us_date("2026-10-07T07:00:00+00:00"), "2026-10-07")
        self.assertEqual(amazon_us_date("2026-10-08T06:59:59+00:00"), "2026-10-07")
        self.assertEqual(amazon_us_date("2026-10-08T07:00:00+00:00"), "2026-10-08")
        # DST boundaries remain Pacific-date safe and elasticity suppresses
        # unchanged-price / zero-denominator cases.
        self.assertEqual(amazon_us_date("2026-11-01T08:30:00+00:00"), "2026-11-01")
        self.assertIsNone(midpoint_arc_elasticity(2, 3, 10, 10))
        self.assertIsNone(midpoint_arc_elasticity(0, 0, 10, 12))
        self.assertIsNone(midpoint_arc_elasticity(2, 0, 10, None))
        self.assertAlmostEqual(midpoint_arc_elasticity(2, 0, 10, 12), -11)
        self.assertAlmostEqual(midpoint_arc_elasticity(0, 2, 10, 12), 11)
        self.assertAlmostEqual(midpoint_arc_elasticity(10, 8, 10, 12), -1.2222222222)

    def test_price_change_page_uses_completed_matched_days_and_all_asins(self):
        from decision_dashboard_v2.analytics import price_change_performance

        result = price_change_performance(7, False)
        response = self.client.get("/price-change?window=7&transition=exclude")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result["before"]["days"], result["after"]["days"])
        self.assertEqual(len(result["asin_rows"]), 12)
        self.assertEqual(result["completed_through"], "2026-10-18")
        self.assertIn(b"Provisional\xe2\x80\x94not decision-ready", response.data)
        self.assertIn(b"Customer sentiment", response.data)
        self.assertIn(b"Not assessed", response.data)
        self.assertIn(b"B0FFQ5Z8CS", response.data)
        self.assertNotIn(b"Prime event</a>", response.data)

    def test_price_change_transition_control_and_sparse_views(self):
        from decision_dashboard_v2.analytics import price_change_performance

        excluded = price_change_performance(28, False)
        included = price_change_performance(14, True)
        self.assertNotIn("2026-10-17", excluded["after_dates"])
        self.assertIn("2026-10-17", included["after_dates"])
        self.assertEqual(included["before"]["days"], included["after"]["days"])
        self.assertTrue(any(row["after"]["packs"] == 0 for row in included["asin_rows"]))
        self.assertTrue(any(row["elasticity"] is None for row in included["asin_rows"]))
        response = self.client.get("/price-change?window=14&transition=include")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Include transition day", response.data)
        self.assertIn(b"No price change", response.data)
        self.assertIn(b"October 17 is included in this view", response.data)
        self.assertIn(b"Before: 8 matched dates", response.data)
        self.assertIn(b"2026-09-19", response.data)
        self.assertIn(b"2026-09-20", response.data)
        self.assertIn(b"selected observations, not a continuous date range", response.data)
        self.assertIn(b"No sales; realized price unavailable", response.data)
        self.assertNotIn(b">Zero demand in one window</span>", response.data)
        self.assertIn(b"Zero demand in one window alone does not make midpoint elasticity undefined", response.data)

    def test_price_change_four_week_weekday_weights_and_two_day_normalization(self):
        from decision_dashboard_v2.analytics import price_change_performance

        one_day = price_change_performance(7, False, "weekday4")
        self.assertEqual(one_day["before_dates"], [
            "2026-09-20", "2026-09-27", "2026-10-04", "2026-10-11",
        ])
        self.assertEqual([row["weight"] for row in one_day["before_date_weights"]],
                         [.25, .25, .25, .25])
        self.assertEqual(one_day["before"]["days"], 1)
        self.assertEqual(one_day["before"]["raw_days"], 4)
        self.assertNotEqual(one_day["before"]["raw_packs"],
                            one_day["before"]["weighted_packs"])

        two_day = price_change_performance(7, True, "weekday4")
        self.assertEqual(len(two_day["before_dates"]), 8)
        self.assertEqual(two_day["before"]["days"], 2)
        self.assertTrue(all(day < "2026-10-17" for day in two_day["before_dates"]))
        self.assertEqual(two_day["after"]["raw_packs"], 14)
        self.assertAlmostEqual(two_day["after"]["raw_revenue"], 528.86)
        self.assertEqual(two_day["after"]["packs_per_day"], 7)
        self.assertAlmostEqual(two_day["after"]["revenue_per_day"], 264.43)
        self.assertAlmostEqual(two_day["after"]["contribution_after_ads_per_day"],
                               two_day["after"]["contribution_after_ads"] / 2)
        self.assertEqual({row["label"]: row["after"]["raw_packs"]
                          for row in two_day["pack_rows"]},
                         {"single": 4, "3-pack": 9, "6-pack": 1})
        self.assertTrue(any(row["before"]["raw_packs"] == 0
                            for row in two_day["asin_rows"]))

    def test_price_change_default_excludes_transition_and_equal_length_alternative(self):
        from decision_dashboard_v2.analytics import price_change_performance

        default = price_change_performance()
        equal = price_change_performance(7, True, "equal")
        self.assertFalse(default["include_transition"])
        self.assertEqual(default["after_dates"], ["2026-10-18"])
        self.assertEqual(default["baseline_mode"], "weekday4")
        self.assertEqual(equal["before_dates"], ["2026-09-19", "2026-09-20"])
        response = self.client.get("/price-change")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"October 17 is excluded by default", response.data)
        self.assertIn(b'<option value="exclude" selected>', response.data)
        self.assertIn(b"Four-week weekday baseline", response.data)
        self.assertIn(b"Six-pack growth objective", response.data)
        self.assertIn(b"6 packs", response.data)
        self.assertIn(b"Contribution after ads/day", response.data)
        self.assertIn(b"ingestion completeness remains unverified", response.data)

    def test_prime_event_handles_asin_without_fee_history(self):
        from decision_dashboard_v2.analytics import prime_big_deals_performance

        database = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        database.close()
        try:
            with sqlite3.connect(database.name) as conn:
                conn.executescript("""
                    CREATE TABLE dim_product (
                      asin TEXT, canonical_brand TEXT, canonical_product_name TEXT,
                      color TEXT, size TEXT, pack_type TEXT
                    );
                    CREATE TABLE orders (
                      "amazon-order-id" TEXT, asin TEXT, "purchase-date" TEXT,
                      quantity REAL, "item-price" REAL,
                      "item-promotion-discount" REAL,
                      "order-status" TEXT, "item-status" TEXT
                    );
                    CREATE TABLE sales_profitability (
                      order_id TEXT, asin TEXT, sale_date TEXT, brand TEXT,
                      cogs_amount REAL, amazon_fees REAL,
                      cogs_status TEXT, fee_status TEXT
                    );
                    CREATE TABLE cogs_ledger (
                      asin TEXT, unit_cogs REAL, effective_start TEXT,
                      effective_end TEXT
                    );
                    CREATE TABLE asin_economics (
                      period_start TEXT, period_end TEXT, asin TEXT,
                      net_sales REAL, net_units_sold REAL,
                      fba_fulfillment_fees REAL, referral_fee REAL,
                      referral_fee_refunds REAL
                    );
                    CREATE TABLE ppc_fact_clean (
                      report_date TEXT, campaign_name TEXT, brand TEXT,
                      spend REAL, ad_sales REAL
                    );
                    INSERT INTO dim_product VALUES
                      ('NEW1','Litet','New Litet ASIN','White','M','single');
                    INSERT INTO orders VALUES
                      ('O1','NEW1','2026-10-06T18:00:00+00:00',1,12,0,
                       'Shipped','Shipped');
                    INSERT INTO cogs_ledger VALUES
                      ('NEW1',3,'2026-01-01',NULL);
                """)
            with patch.dict(os.environ, {"LITET_DB_PATH": database.name}):
                result = prime_big_deals_performance()
                response = self.client.get("/events/prime-big-deals-2026")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(result["sales"], 12)
            self.assertEqual(result["estimated_fee_coverage"], 0)
            self.assertIsNone(result["profit"])
        finally:
            os.unlink(database.name)

    def test_prime_event_uses_confirmed_provisional_fba_for_new_event_asin(self):
        from decision_dashboard_v2.analytics import prime_big_deals_performance

        database = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        database.close()
        try:
            with sqlite3.connect(database.name) as conn:
                conn.executescript("""
                    CREATE TABLE dim_product (asin TEXT, canonical_brand TEXT,
                      canonical_product_name TEXT, color TEXT, size TEXT, pack_type TEXT);
                    CREATE TABLE orders ("amazon-order-id" TEXT, asin TEXT,
                      "purchase-date" TEXT, quantity REAL, "item-price" REAL,
                      "item-promotion-discount" REAL, "order-status" TEXT,
                      "item-status" TEXT);
                    CREATE TABLE sales_profitability (order_id TEXT, asin TEXT,
                      sale_date TEXT, brand TEXT, cogs_amount REAL,
                      amazon_fees REAL, cogs_status TEXT, fee_status TEXT);
                    CREATE TABLE cogs_ledger (asin TEXT, unit_cogs REAL,
                      effective_start TEXT, effective_end TEXT);
                    CREATE TABLE asin_economics (period_start TEXT,
                      period_end TEXT, asin TEXT, net_sales REAL,
                      net_units_sold REAL, fba_fulfillment_fees REAL,
                      referral_fee REAL, referral_fee_refunds REAL);
                    CREATE TABLE ppc_fact_clean (report_date TEXT,
                      campaign_name TEXT, brand TEXT, spend REAL, ad_sales REAL);
                    INSERT INTO dim_product VALUES
                      ('B0GSXJY1HQ','Litet','6-pack','White','Small/Medium','6-pack');
                    INSERT INTO orders VALUES
                      ('O1','B0GSXJY1HQ','2026-10-06T18:00:00+00:00',1,55.99,0,
                       'Shipped','Shipped');
                    INSERT INTO cogs_ledger VALUES
                      ('B0GSXJY1HQ',12,'2026-01-01',NULL);
                    INSERT INTO ppc_fact_clean VALUES
                      ('2026-10-06','LITET event','Litet',0,0);
                """)
            with patch.dict(os.environ, {"LITET_DB_PATH": database.name}):
                result = prime_big_deals_performance()
            self.assertEqual(result["estimated_fee_coverage"], 1)
            self.assertEqual(result["provisional_fba_asins"], ["B0GSXJY1HQ"])
            self.assertAlmostEqual(result["normal_fixed_fees"], 3.90)
            self.assertAlmostEqual(result["normal_variable_fees"], 55.99 * .17)
            self.assertIsNotNone(result["profit"])
        finally:
            os.unlink(database.name)

    def test_current_mtd_uses_latest_available_settled_pnl(self):
        response = self.client.get(
            "/?brand=Litet&period=2026-09-01%7C2026-09-04"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Current operations \xc2\xb7 2026-10-01\xe2\x80\x932026-10-18", response.data)
        self.assertIn(b"Latest settled period \xc2\xb7 2026-09-01\xe2\x80\x932026-09-30", response.data)
        self.assertNotIn(b"Net sales</span><b>$0</b>", response.data)

    def test_old_august_cutoff_advances_to_completed_month(self):
        response = self.client.get(
            "/?brand=Litet&period=2026-08-01%7C2026-08-27"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Litet \xc2\xb7 2026-08-01\xe2\x80\x932026-08-31", response.data)
        self.assertIn(b"Latest settled period \xc2\xb7 2026-08-01\xe2\x80\x932026-08-31", response.data)

    def test_brand_and_period_filter(self):
        response = self.client.get(
            "/?brand=Has10&period=2026-08-01%7C2026-08-16"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Has10", response.data)
        self.assertIn(b"Seasonal scale and availability", response.data)
        self.assertIn(b"Three priorities", response.data)
        self.assertIn(b"orange cleat covers", response.data)
        self.assertIn(b"Do not answer the current profit pressure with a broad price change", response.data)
        self.assertNotIn(b"Keep the $13.99 base price", response.data)
        self.assertIn(b"Why Amazon costs are 41.5%", response.data)
        self.assertIn(b"Maximum ads to break even", response.data)
        self.assertIn(b"Bring TaCoS below 34%", response.data)
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
        from decision_dashboard_v2.analytics import periods, ppc_periods
        latest = max(p["period_end"] for p in periods())
        latest_month = latest[:7]
        current = [p for p in ppc_periods()
                   if p["group"] == "Monthly periods"
                   and p["period_start"].startswith(latest_month)]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["period_start"], f"{latest_month}-01")
        self.assertEqual(current[0]["period_end"], latest)

    def test_prior_month_filter_keeps_only_latest_cutoff(self):
        from decision_dashboard_v2.analytics import ppc_periods
        imported = [
            {"period_start": "2026-08-01", "period_end": f"2026-08-{day:02d}",
             "period_type": "custom", "has_economics": 1}
            for day in (4, 16, 23, 27)
        ] + [{
            "period_start": "2026-08-28", "period_end": "2026-09-04",
            "period_type": "custom", "has_economics": 1,
        }]
        with patch("decision_dashboard_v2.analytics.periods", return_value=imported):
            choices = ppc_periods()
        august = [p for p in choices if p["period_start"].startswith("2026-08")]
        self.assertEqual(len(august), 1)
        self.assertEqual(august[0]["period_end"], "2026-08-27")
        self.assertEqual(august[0]["label"], "August 2026")

    def test_monthly_trend_contains_consolidated_current_mtd(self):
        from decision_dashboard_v2.analytics import monthly_trend
        trend = monthly_trend("Litet")
        latest_year = trend[-1]["period_start"][:4]
        self.assertTrue(all(r["period_start"].startswith(latest_year) for r in trend))
        august = [r for r in trend if r["period_start"] == "2026-08-01"]
        september = [r for r in trend if r["period_start"] == "2026-09-01"]
        october = [r for r in trend if r["period_start"] == "2026-10-01"]
        self.assertEqual(len(august), 1)
        self.assertEqual(august[0]["period_end"], "2026-08-31")
        self.assertFalse(august[0]["is_partial"])
        self.assertGreater(august[0]["ordered_sales"], 0)
        self.assertEqual(len(september), 1)
        self.assertEqual(september[0]["period_end"], "2026-09-30")
        self.assertFalse(september[0]["is_partial"])
        self.assertGreater(september[0]["ordered_sales"], 0)
        self.assertEqual(len(october), 1)
        self.assertEqual(october[0]["period_end"], trend[-1]["period_end"])
        self.assertGreaterEqual(october[0]["period_end"], "2026-10-16")
        self.assertTrue(october[0]["is_partial"])

    def test_monthly_trend_includes_sessions_without_summing_cumulative_snapshots(self):
        from decision_dashboard_v2.analytics import monthly_trend

        database = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        database.close()
        try:
            with sqlite3.connect(database.name) as conn:
                conn.executescript("""
                    CREATE TABLE dim_product (asin TEXT, canonical_brand TEXT);
                    CREATE TABLE orders (
                      asin TEXT, "purchase-date" TEXT, quantity REAL,
                      "item-price" REAL, "item-promotion-discount" REAL,
                      "order-status" TEXT, "item-status" TEXT
                    );
                    CREATE TABLE ppc_fact_clean (
                      report_date TEXT, brand TEXT, spend REAL
                    );
                    CREATE TABLE business_traffic (
                      period_start TEXT, period_end TEXT, child_asin TEXT,
                      sessions_total REAL
                    );
                    INSERT INTO dim_product VALUES ('A1','Litet');
                    INSERT INTO orders VALUES
                      ('A1','2026-08-31',1,310,0,'Shipped','Shipped'),
                      ('A1','2026-09-16',1,150,0,'Shipped','Shipped');
                    INSERT INTO ppc_fact_clean VALUES
                      ('2026-08-31','Litet',31),
                      ('2026-09-16','Litet',15);
                    INSERT INTO business_traffic VALUES
                      ('2026-08-01','2026-08-16','A1',200),
                      ('2026-08-17','2026-08-31','A1',110),
                      ('2026-09-01','2026-09-04','A1',40),
                      ('2026-09-01','2026-09-16','A1',150);
                """)
            with patch.dict(os.environ, {"LITET_DB_PATH": database.name}):
                trend = monthly_trend("Litet")
            self.assertEqual(trend[-2]["sessions"], 310)
            self.assertEqual(trend[-1]["sessions"], 150)
        finally:
            os.unlink(database.name)

    def test_pnl_displays_cogs_and_reconciles_to_contribution(self):
        from decision_dashboard_v2.analytics import pnl_statement
        pnl = pnl_statement("2026-08-01", "2026-08-23", "Litet")
        reconciled = pnl["gross_sales"] - pnl["amazon_costs_ex_ads"] - pnl["ad_spend"] - pnl["cogs"]
        self.assertAlmostEqual(reconciled, pnl["contribution"], places=6)
        response = self.client.get("/?brand=Litet&period=2026-08-01%7C2026-08-23")
        self.assertIn(b"Estimated COGS", response.data)

    def test_pnl_uses_only_latest_cumulative_economics_snapshot(self):
        from decision_dashboard_v2.analytics import cost_diagnosis, pnl_statement

        database = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        database.close()
        try:
            with sqlite3.connect(database.name) as conn:
                conn.executescript("""
                    CREATE TABLE dim_product (
                      asin TEXT PRIMARY KEY, canonical_brand TEXT,
                      canonical_product_name TEXT, color TEXT, size TEXT,
                      pack_type TEXT, product_family TEXT, product_key TEXT,
                      is_current INTEGER
                    );
                    CREATE TABLE business_traffic (
                      period_start TEXT, period_end TEXT, child_asin TEXT,
                      sessions_total REAL, page_views_total REAL,
                      units_ordered REAL, ordered_product_sales REAL,
                      featured_offer_percentage REAL
                    );
                    CREATE TABLE asin_economics (
                      period_start TEXT, period_end TEXT, asin TEXT,
                      units_sold REAL, units_returned REAL, net_units_sold REAL,
                      net_sales REAL, sponsored_products_charge REAL,
                      net_proceeds REAL, fba_fulfillment_fees REAL,
                      referral_fee REAL, referral_fee_refunds REAL,
                      refund_administration_fee REAL, other_fee_total REAL
                    );
                    CREATE TABLE cogs_ledger (
                      asin TEXT, effective_start TEXT, effective_end TEXT,
                      unit_cogs REAL
                    );
                    CREATE TABLE inventory_snapshots (
                      asin TEXT, snapshot_date TEXT, "Quantity Available" REAL
                    );
                    CREATE TABLE bridge_product_sku (
                      product_key TEXT, sku TEXT, is_current INTEGER
                    );
                    INSERT INTO dim_product VALUES
                      ('A1','Litet','Test product','Blue','M','single','Test','P1',1);
                    INSERT INTO business_traffic VALUES
                      ('2026-09-01','2026-09-16','A1',100,120,10,250,100);
                    INSERT INTO cogs_ledger VALUES
                      ('A1','2026-01-01',NULL,5);
                    INSERT INTO asin_economics VALUES
                      ('2026-09-01','2026-09-04','A1',4,0,4,100,20,50,20,15,0,1,4),
                      ('2026-09-01','2026-09-16','A1',8,1,7,200,40,110,35,25,0,2,8);
                """)
            with patch.dict(os.environ, {"LITET_DB_PATH": database.name}):
                pnl = pnl_statement("2026-09-01", "2026-09-16", "Litet")
                costs = cost_diagnosis("2026-09-01", "2026-09-16", "Litet")
            self.assertEqual(pnl["gross_sales"], 200)
            self.assertEqual(pnl["ad_spend"], 40)
            self.assertEqual(pnl["net_proceeds"], 110)
            self.assertEqual(costs["net_sales"], 200)
            self.assertEqual(costs["ads"], 40)
        finally:
            os.unlink(database.name)

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
        self.assertIn(b"Target / ad group", response.data)
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
        self.assertIn(b"Target / ad group", response.data)
        self.assertIn(b"Targeting decisions", response.data)
        self.assertIn(b"Customer search-term evidence", response.data)
        self.assertIn(b"Selected-period performance", response.data)
        self.assertIn(b"Keyword opportunities", response.data)
        self.assertIn(b"aero cycling socks", response.data)
        self.assertIn(b"Where Litet can close the visibility gap", response.data)
        self.assertIn(b"Selected-period PPC evidence", response.data)
        self.assertIn(b"Matching query", response.data)
        self.assertIn(b"PPC spend vs total ordered units", response.data)
        self.assertIn(b"March 2026", response.data)
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

    def test_products_handles_missing_helium_sales_changes(self):
        market = {
            "own": {"sales": None, "sales_change": None, "reviews": 97,
                    "price": 14.99, "top10_keywords": 4},
            "competitors": [], "competitor_sales_median": None,
            "competitor_keyword_median": None, "comparison_share": None,
            "review_gap": None, "peer_median_change": None,
            "direct_price_median": None, "pack_benchmarks": [],
            "strategic_gaps": [], "captured_at": "2026-09-04T23:12:18Z",
        }
        with patch("decision_dashboard_v2.app.market_context", return_value=market):
            response = self.client.get(
                "/products?brand=Litet&period=2026-08-01%7C2026-08-27"
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Peer median recent change", response.data)

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

    def test_unverified_price_test_is_rejected(self):
        response = self.client.post("/decisions/pricing/approve", data={
            "brand":"Litet", "asin":"B0DSCFMCQD", "old_value":"14.99",
            "new_value":"13.99", "period_start":"2026-08-01", "period_end":"2026-08-16",
            "required_lift":"0.25"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"verified current Amazon price", response.data)

    def test_ppc_proposal_is_queued_once_and_can_be_approved(self):
        payload={"brand":"Litet","campaign_name":"LITET discovery",
                 "entity_type":"target","entity_name":"men cycling socks",
                 "ad_group_name":"discovery","match_type":"BROAD",
                 "action_type":"reduce_bid_15pct","actual_bid":"2.02",
                 "adjustment_pct":"-0.15","period_start":"2026-09-01",
                 "period_end":"2026-09-04","objective":"Reduce waste",
                 "spend":"97.10","clicks":"48","orders":"3","acos":"1.388"}
        for _ in range(2):
            response=self.client.post("/decisions/proposals",data=payload,follow_redirects=True)
            self.assertEqual(response.status_code,200)
        from decision_dashboard_v2.interventions import connect
        with connect() as conn:
            rows=conn.execute("SELECT * FROM interventions WHERE entity_name=?",
                              ("men cycling socks",)).fetchall()
        self.assertEqual(len(rows),1)
        self.assertIsNotNone(rows[0]["created_at"])
        intervention_id=rows[0]["id"]
        response=self.client.post(f"/decisions/interventions/{intervention_id}/status",
                                  data={"brand":"Litet","period":"2026-09-01|2026-09-04",
                                        "status":"approved"},follow_redirects=True)
        self.assertEqual(response.status_code,200)
        self.assertIn(b"Approved; not yet confirmed in Amazon",response.data)

    def test_executed_ppc_change_can_be_adjusted_and_superseded(self):
        from decision_dashboard_v2.interventions import (
            connect, record_action_proposal, update_intervention_status,
        )
        intervention_id, _ = record_action_proposal({
            "brand":"Litet", "asin":"—", "campaign_name":"LITET Ranking Campaign",
            "ad_group_name":"Rankings", "entity_type":"keyword",
            "entity_name":"cycling socks", "match_type":"BROAD",
            "action_type":"reduce_bid_30pct", "old_value":1.20, "new_value":.84,
            "period_start":"2026-09-01", "period_end":"2026-09-06",
            "objective":"Reduce waste", "baseline":{"spend":78.18,"clicks":54,
            "orders":2,"ad_sales":54.98,"acos":1.42},
        })
        update_intervention_status(intervention_id,"approved")
        update_intervention_status(intervention_id,"executed")
        response=self.client.post(
            f"/decisions/interventions/{intervention_id}/adjust",
            data={"brand":"Litet","period":"2026-09-01|2026-09-17",
                  "new_value":"1.00","objective":"Recover controlled traffic"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code,302)
        with connect() as conn:
            followup=conn.execute(
                "SELECT rowid AS intervention_rowid,* FROM interventions WHERE supersedes_intervention_id=?",
                (intervention_id,),
            ).fetchone()
        self.assertEqual(followup["status"],"proposed")
        update_intervention_status(followup["intervention_rowid"],"approved")
        update_intervention_status(followup["intervention_rowid"],"executed")
        with connect() as conn:
            prior=conn.execute("SELECT status,outcome FROM interventions WHERE rowid=?",
                               (intervention_id,)).fetchone()
        self.assertEqual(prior["status"],"completed")
        self.assertEqual(prior["outcome"],f"revised_by:{followup['intervention_rowid']}")

    def test_pricing_case_uses_trailing_settled_history(self):
        response = self.client.get(
            "/decisions/pricing?brand=Litet&period=2026-08-01%7C2026-08-16&asin=B0DSCFMCQD"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Prior 6 settled months", response.data)
        self.assertIn(b"Historical price and conversion context", response.data)
        self.assertIn(b"Owner-confirmed US landed cost", response.data)
        self.assertNotIn(b"placeholder seed", response.data)
        self.assertIn(b"2026-08-01 to 2026-08-31", response.data)
        self.assertIn(b"Incomplete period", response.data)

    def test_high_volume_pricing_case_uses_historical_baseline(self):
        response = self.client.get(
            "/decisions/pricing?brand=Litet&period=2026-08-01%7C2026-08-16&asin=B0FFPT16G6"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Price decision supported", response.data)
        self.assertIn(b"Completed-month price bands", response.data)
        self.assertIn(b"Do not infer a live price from the $39.99 selected-period average", response.data)
        self.assertNotIn(b"Use a longer settled economics window", response.data)
        self.assertIn(b"ASIN seasonality", response.data)
        self.assertIn(b"MTD pace", response.data)


if __name__ == "__main__":
    unittest.main()
