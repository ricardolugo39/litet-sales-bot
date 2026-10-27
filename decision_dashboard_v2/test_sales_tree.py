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
        d = price_change_traffic_diagnostic()
        self.assertEqual(d['asin_count'], 10)
        self.assertEqual((d['before']['sessions'], d['before']['units']), (625,36))
        self.assertEqual((d['after']['sessions'], d['after']['units']), (486,20))
        self.assertEqual(len(d['excluded']),2)
        page = self.client.get('/sales-tree')
        self.assertIn(b'separate dates',page.data)
        self.assertIn(b'625',page.data)
        self.assertIn(b'486',page.data)
