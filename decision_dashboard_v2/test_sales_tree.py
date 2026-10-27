import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
from decision_dashboard_v2.app import app
from decision_dashboard_v2.analytics import price_change_performance

class SalesTreeTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.clock = patch('decision_dashboard_v2.analytics.datetime', wraps=datetime)
        self.mock_clock = self.clock.start()
        self.mock_clock.now.return_value = datetime(2026, 10, 27, 12, tzinfo=ZoneInfo('America/Los_Angeles'))
        self.addCleanup(self.clock.stop)

    def test_default_reconciles_financial_bridge(self):
        data = price_change_performance(14)
        b, a = data['before'], data['after']
        self.assertAlmostEqual(a['contribution_after_ads_per_day'] - b['contribution_after_ads_per_day'],
                               (a['contribution_per_day'] - b['contribution_per_day']) -
                               (a['ad_spend']/a['days'] - b['ad_spend']/b['days']))
        page = self.client.get('/sales-tree')
        self.assertEqual(page.status_code, 200)
        for value in (b'$38.72', b'$21.01', b'weekday-matched', b'Largest unfavorable percentage', b'Unique customers'):
            self.assertIn(value, page.data)

    def test_custom_periods_and_validation(self):
        page = self.client.get('/sales-tree?before_start=2026-09-20&before_end=2026-09-28&after_start=2026-10-18&after_end=2026-10-26')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Custom comparison', page.data)
        self.assertIn(b'2026-09-20', page.data)
        bad = self.client.get('/sales-tree?before_start=2026-10-01&before_end=2026-10-20&after_start=2026-10-18&after_end=2026-10-26')
        self.assertEqual(bad.status_code, 400)
        self.assertIn(b'must end before', bad.data)

    def test_traffic_cohort_is_separate_and_aggregated(self):
        from decision_dashboard_v2.analytics import price_change_traffic_diagnostic
        d = price_change_performance(14).get('alternate_traffic') or price_change_traffic_diagnostic()
        self.assertGreater(d['asin_count'], 0)
        page = self.client.get('/sales-tree')
        self.assertIn(b'separate dates', page.data)
        self.assertIn(f"{d['before']['sessions']:,.0f}".encode(), page.data)
        self.assertIn(f"{d['after']['sessions']:,.0f}".encode(), page.data)

    def test_helium_snapshot_is_labeled_and_not_used_for_custom_dates(self):
        page = self.client.get('/sales-tree')
        self.assertEqual(page.status_code, 200)
        for label in (b'Market search demand', b'Organic search position',
                      b'15.4% ACoS', b'91.2% ACoS', b'fixed research findings'):
            self.assertIn(label, page.data)
        custom = self.client.get('/sales-tree?before_start=2026-09-20&before_end=2026-09-28&after_start=2026-10-18&after_end=2026-10-26')
        self.assertNotIn(b'Market search demand', custom.data)
