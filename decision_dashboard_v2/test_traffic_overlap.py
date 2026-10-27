import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from decision_dashboard_v2.analytics import (_select_nonoverlapping_traffic, overview,
    product_diagnostics, monthly_trend, cost_diagnosis, price_change_performance)

class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE business_traffic (period_start TEXT, period_end TEXT)')
        self.addCleanup(self.db.close)
    def choose(self,start,end):
        return _select_nonoverlapping_traffic(self.db,start,end)
    def test_full_period_wins_and_adjacent_periods_combine(self):
        self.db.executemany('INSERT INTO business_traffic VALUES (?,?)',[
            ('2026-10-01','2026-10-16'),('2026-10-01','2026-10-17'),
            ('2026-10-01','2026-10-26'),('2026-10-18','2026-10-26')])
        self.assertEqual(self.choose('2026-10-01','2026-10-26'),(('2026-10-01','2026-10-26'),))
        self.assertEqual(self.choose('2026-10-18','2026-10-26'),(('2026-10-18','2026-10-26'),))
        self.db.execute("DELETE FROM business_traffic WHERE period_end='2026-10-26' AND period_start='2026-10-01'")
        self.assertEqual(self.choose('2026-10-01','2026-10-26'),(('2026-10-01','2026-10-17'),('2026-10-18','2026-10-26')))
    def test_partial_overlap_never_double_counts_days(self):
        self.db.executemany('INSERT INTO business_traffic VALUES (?,?)',[
            ('2026-10-01','2026-10-10'),('2026-10-05','2026-10-20'),('2026-10-11','2026-10-26')])
        self.assertEqual(self.choose('2026-10-01','2026-10-26'),(('2026-10-01','2026-10-10'),('2026-10-11','2026-10-26')))

class DashboardOverlapTest(unittest.TestCase):
    def test_direct_export_does_not_inflate_existing_views(self):
        path=tempfile.NamedTemporaryFile(suffix='.db',delete=False).name
        try:
            with sqlite3.connect(os.environ['LITET_DB_PATH']) as source, sqlite3.connect(path) as copy:
                source.backup(copy)
            with patch.dict(os.environ,{'LITET_DB_PATH':path}):
                original=overview('2026-10-01','2026-10-26','Litet')
                products=product_diagnostics('2026-10-01','2026-10-26','Litet')
                trends=monthly_trend('Litet')
                cost=cost_diagnosis('2026-10-01','2026-10-26','Litet')
                with sqlite3.connect(path) as conn:
                    columns=[r[1] for r in conn.execute('PRAGMA table_info(business_traffic)')]
                    expr=["'2026-10-18'" if c=='period_start' else c for c in columns]
                    conn.execute('INSERT INTO business_traffic SELECT '+','.join('"'+c+'"' if e==c else e for c,e in zip(columns,expr))+" FROM business_traffic WHERE period_start='2026-10-01' AND period_end='2026-10-26'")
                updated=overview('2026-10-01','2026-10-26','Litet')
                after_products=product_diagnostics('2026-10-01','2026-10-26','Litet')
                after_trends=monthly_trend('Litet')
                after_cost=cost_diagnosis('2026-10-01','2026-10-26','Litet')
                for field in ('sessions','units','ordered_sales','conversion'):
                    self.assertEqual(original[field],updated[field],field)
                self.assertEqual([(p['asin'],p['sessions'],p['units']) for p in products],[(p['asin'],p['sessions'],p['units']) for p in after_products])
                self.assertEqual(trends,after_trends)
                self.assertEqual(cost['ordered_sales'],after_cost['ordered_sales'])
                from datetime import date
                result=price_change_performance(14, comparison=(date(2026,10,1),date(2026,10,16),date(2026,10,18),date(2026,10,26)))
                self.assertEqual(result['after']['traffic']['source'],'direct report')
                self.assertEqual(result['after']['traffic']['sessions'],original['sessions'])
        finally:
            os.unlink(path)

class ImportOverlapTest(unittest.TestCase):
    def test_both_reports_import_and_existing_month_is_unchanged(self):
        import pandas as pd
        from pathlib import Path
        from pipelines.importers.update_business_reports import import_file
        source_path = '/Users/ricardolugo/Library/CloudStorage/OneDrive-Personal/Hasten/Reports/Raw/processed/20261027_101445_processed_business_report_2026-10-01_2026-10-26.csv'
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, 'copy.db')
            with sqlite3.connect(os.environ['LITET_DB_PATH']) as source, sqlite3.connect(db_path) as target:
                source.backup(target)
            frame = pd.read_csv(source_path, dtype=str)
            with patch.dict(os.environ, {'LITET_DB_PATH':db_path}):
                before=overview('2026-10-01','2026-10-26','Litet')
                for n,period in enumerate((('2026-10-01','2026-10-17'),('2026-10-18','2026-10-26')), start=1):
                    name=Path(directory)/f'business_report_{period[0]}_{period[1]}.csv'
                    report=frame.copy()
                    report.loc[0,'Title']=str(report.loc[0,'Title'])+f' test {n}'
                    report.to_csv(name,index=False)
                    with sqlite3.connect(db_path) as conn:
                        self.assertGreater(import_file(name,conn,move_after=False),0)
                after=overview('2026-10-01','2026-10-26','Litet')
                for field in ('sessions','units','ordered_sales','conversion'):
                    self.assertEqual(before[field],after[field],field)
                with sqlite3.connect(db_path) as conn:
                    found=conn.execute("SELECT count(*) FROM business_report_imports WHERE (period_start='2026-10-01' AND period_end='2026-10-17') OR (period_start='2026-10-18' AND period_end='2026-10-26')").fetchone()[0]
                self.assertEqual(found,2)

    def test_failed_import_stops_update(self):
        from pathlib import Path
        from pipelines.importers import update_business_reports as importer
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            incoming=root/'incoming'; incoming.mkdir()
            broken=incoming/'business_report_2026-10-01_2026-10-17.csv'
            broken.write_text('not,a,valid,report\n1,2,3,4\n')
            with patch.object(importer,'DB_PATH',root/'copy.db'), patch.object(importer,'INCOMING_FOLDER',incoming), patch.object(importer,'PROCESSED_FOLDER',root/'processed'), patch.object(importer,'FAILED_FOLDER',root/'failed'):
                with self.assertRaisesRegex(RuntimeError,'Business report import failed'):
                    importer.update_business_reports()
                self.assertEqual(len(list((root/'failed').glob('*.csv'))),1)
