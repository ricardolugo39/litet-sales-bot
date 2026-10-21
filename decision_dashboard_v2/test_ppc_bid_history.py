import unittest
from datetime import date,timedelta
from .ppc_bid_history import recorded_bid_assessment,execution_dates


class RecordedBidTests(unittest.TestCase):
    def target(self):
        return dict(brand='Litet',campaign_name='C',ad_group_name='G',target='cycling socks',match_type='BROAD',economics=dict(available=True,complete=True,low=.4,high=.5))

    def change(self,when,old,new,status='executed',**updates):
        r=dict(brand='Litet',campaign_name='C',ad_group_name='G',entity_name='cycling socks',match_type='BROAD',intervention_type='ppc_action',action_type='manual_bid_adjustment',old_value=old,new_value=new,executed_at=when,status=status,period_start='2026-08-25',period_end='2026-08-31')
        r.update(updates);return r

    def test_exact_scoping_matched_weekdays_no_future_and_recorded_amount(self):
        days=[(date(2026,9,1)+timedelta(days=i)).isoformat() for i in range(28)]
        rows=[dict(report_date=d,clicks=1 if d<'2026-09-15' else 10,impressions=20,spend=1 if d<'2026-09-15' else 10,ad_orders=1 if d<'2026-09-15' else 5,ad_sales=4 if d<'2026-09-15' else 100) for d in days]
        events=[self.change('2026-09-01 15:00:00',1.2,.84),self.change('2026-09-15 15:00:00',.84,1.2),self.change('2026-10-01 15:00:00',1.2,5),self.change('2026-09-20 15:00:00',1.2,.1,match_type='PHRASE')]
        r=recorded_bid_assessment(self.target(),rows,events,'2026-09-28',days,['2026-09-20'])
        self.assertEqual(r['recommended_bid'],1.2);self.assertEqual(r['last_recorded_bid'],1.2)
        self.assertEqual(len(r['candidates']),2)
        for run in r['candidates']:
            self.assertNotIn('2026-09-15',run['matched_dates']);self.assertNotIn('2026-09-20',run['matched_dates'])
        weekdays=[sorted(date.fromisoformat(d).weekday() for d in run['matched_dates']) for run in r['candidates']]
        self.assertEqual(weekdays[0],weekdays[1])
        future=rows+[dict(report_date='2026-10-01',clicks=1000,ad_orders=1000,ad_sales=100000,spend=0,impressions=1000)]
        self.assertEqual(r,recorded_bid_assessment(self.target(),future,events,'2026-09-28',days,['2026-09-20']))

    def test_dismissed_unexecuted_or_other_scope_cannot_create_setting(self):
        events=[self.change('',1,2,status='proposed'),self.change('2026-09-01 15:00:00',1,2,ad_group_name='Other')]
        self.assertFalse(recorded_bid_assessment(self.target(),[],events,'2026-09-20',[])['available'])
        self.assertEqual(execution_dates('2026-09-08 00:13:00'),{date(2026,9,7),date(2026,9,8)})

    def test_completed_run_remains_valid_before_a_future_successor(self):
        changes=[self.change('2026-09-01 15:00:00',1,1.2,status='completed'),self.change('2026-09-15 15:00:00',1.2,.8)]
        days=['2026-09-02','2026-09-09']
        rows=[dict(report_date=d,clicks=2,impressions=50,spend=2,ad_sales=20,ad_orders=1) for d in days]
        r=recorded_bid_assessment(self.target(),rows,changes,'2026-09-10',days)
        self.assertEqual(r['last_recorded_bid'],1.2)
        self.assertEqual(r['recommended_bid'],1.2)
        self.assertFalse(r['comparison_available'])

    def test_latest_unmature_change_is_not_mislabeled_as_the_older_live_bid(self):
        days=['2026-09-02','2026-09-09']
        rows=[dict(report_date=d,clicks=2,impressions=50,spend=2,ad_sales=20,ad_orders=1) for d in days]
        changes=[self.change('2026-09-01 15:00:00',1,1.2),self.change('2026-09-12 15:00:00',1.2,1.4)]
        r=recorded_bid_assessment(self.target(),rows,changes,'2026-09-10',days,asof='2026-09-13')
        self.assertEqual(r['recommended_bid'],1.4);self.assertEqual(r['last_recorded_bid'],1.4)
        self.assertEqual(r['historical_best_bid'],1.2);self.assertTrue(r['pending_latest'])
        self.assertEqual(r['pending_review_after'],'2026-09-21')

    def test_no_profitable_recorded_setting_is_not_recommended_as_optimal(self):
        days=['2026-09-02','2026-09-09']
        rows=[dict(report_date=d,clicks=5,ad_orders=0,ad_sales=0,spend=10,impressions=50) for d in days]
        r=recorded_bid_assessment(self.target(),rows,[self.change('2026-09-01 15:00:00',1,1.2)],'2026-09-10',days)
        self.assertTrue(r['available']);self.assertTrue(r['no_profitable_setting']);self.assertIsNone(r['recommended_bid'])
        self.assertFalse(r['comparison_available'])

if __name__=='__main__':unittest.main()
