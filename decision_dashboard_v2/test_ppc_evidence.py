import json
import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from .app import app, _preserve_railway_tables
from .ppc_evidence import build_workspace, evaluate_candidate, get_policy, get_evaluation, save_policy, save_evaluation, rate_model, DEFAULTS

class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026,10,20,12,tzinfo=tz or ZoneInfo('UTC'))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.facts = str(Path(self.temp.name)/'facts.db')
        self.state = str(Path(self.temp.name)/'state.db')
        self.env = patch.dict(os.environ, {'LITET_DB_PATH':self.facts, 'HASTEN_DECISION_DB':self.state})
        self.env.start(); self.addCleanup(self.env.stop); self.addCleanup(self.temp.cleanup)
        clock=patch('decision_dashboard_v2.ppc_evidence.datetime',FixedClock);clock.start();self.addCleanup(clock.stop)
        self.client=app.test_client()
        with sqlite3.connect(self.facts) as c:
            c.executescript('''
            CREATE TABLE ppc_fact_clean (report_date TEXT,brand TEXT,campaign_name TEXT,
             ad_group_name TEXT,target TEXT,match_type TEXT,impressions REAL,clicks REAL,
             spend REAL,ad_orders REAL,ad_sales REAL,other_sku_sales REAL,imported_at TEXT,search_term TEXT);
            CREATE TABLE orders ("amazon-order-id" TEXT,asin TEXT,"purchase-date" TEXT,
             quantity REAL,"item-price" REAL,"item-promotion-discount" REAL,
             "order-status" TEXT,"item-status" TEXT);
            CREATE TABLE dim_product (asin TEXT,canonical_brand TEXT,is_current INTEGER);
            INSERT INTO dim_product VALUES ('A','Litet',1),('B','Has10',1);
            ''')
            day=date(2026,9,1)
            while day<=date(2026,10,20):
                for ad_group,match,clicks,orders in [('group-A','PHRASE',20,3),('group-B','PHRASE',10,1),('group-A','BROAD',5,0)]:
                    c.execute('INSERT INTO ppc_fact_clean VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(day.isoformat(),'Litet','Campaign',ad_group,'cycling socks',match,100,clicks,clicks*.8,orders,orders*40,orders*10,'2026-10-20 09:00:00','cycling socks'))
                c.execute('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)',(day.isoformat(),'A',day.isoformat()+'T12:00:00Z',2,80,0,'Shipped','Shipped'))
                day+=timedelta(days=1)
        self.base={'brand':'Litet','start':'2026-10-01','end':'2026-10-19'}

    def review(self):
        return build_workspace(self.facts,self.base['start'],self.base['end'],'Litet',today=date(2026,10,20))

    def settings(self, **updates):
        x={'policy_id':get_policy('Litet')['id'] or '', 'attribution_days':'7','prior_lookback_days':'28','prior_clicks':'10','interval_pct':'80','max_loss_probability':'20','profit_reserve_per_order':'0','min_traffic_retention':'80'}
        x.update(updates);return x

    def candidate(self, review, **updates):
        x={'target_key':next(t['key'] for t in review['targets'] if t['ad_group_name']=='group-A' and t['match_type']=='PHRASE'),
           'current_bid':'2','candidate_bid':'1.9','current_clicks_low':'10','current_clicks_high':'10','candidate_clicks_low':'10','candidate_clicks_high':'10',
           'current_cpc_low':'1','current_cpc_high':'1','candidate_cpc_low':'.5','candidate_cpc_high':'.5','margin_low':'20','margin_high':'20',
           'spillover_low':'0','spillover_high':'0','spillover_source':'Controlled account holdout supports no displacement in this synthetic test',
           'response_source':'Documented synthetic response','margin_source':'Synthetic purchased mix','settings_source':'Synthetic current settings',
           'hypothesis':'Lower CPC with unchanged traffic; reverse if visibility falls','relevance_note':'Relevant product and query',
           'settings_date':'2026-10-20','response_date':'2026-10-20','margin_date':'2026-10-20','evidence_kind':'controlled_test','controls_confirmed':'yes','quality_confirmed':'yes'}
        x.update(updates);return x

    def csrf(self):
        self.client.get('/ppc?brand=Litet&start=2026-10-01&end=2026-10-19')
        with self.client.session_transaction() as s:return s['evidence_csrf']

    def test_maturity_identity_and_no_get_state_mutation(self):
        r=self.review();self.assertFalse(Path(self.state).exists())
        self.assertEqual(r['mature_end'],'2026-10-12');self.assertEqual(r['complete'],'2026-10-19')
        self.assertEqual(len(r['targets']),3)
        for t in r['targets']:
            self.assertEqual(t['mature']['clicks']+t['recent']['clicks'],t['selected']['clicks'])
            self.assertFalse(t['is_actionable'])
        original=r['targets'][0]['rate']
        with sqlite3.connect(self.facts) as c:c.execute("UPDATE ppc_fact_clean SET ad_orders=500 WHERE report_date>'2026-10-12'")
        self.assertEqual(original,self.review()['targets'][0]['rate'])
        self.assertNotEqual(r['fingerprint'],self.review()['fingerprint'])

    def test_order_rate_not_artificially_capped(self):
        self.assertGreater(rate_model(10,25,100,10,DEFAULTS,1)['mean'],1)
        self.assertFalse(rate_model(10,0,0,0,DEFAULTS,1)['available'])

    def test_missing_costs_and_unconfirmed_policy_block_advice(self):
        r=self.review();self.assertIsNone(r['company']['contribution'])
        with self.assertRaisesRegex(ValueError,'Confirm'):evaluate_candidate(r,self.candidate(r))
        response=self.client.get('/ppc?brand=Litet&start=2026-10-01&end=2026-10-19')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Partial contributions are not presented as totals',response.data)
        self.assertNotIn(b'Reduce bid 30%',response.data)
        self.assertNotIn(b'Increase bid 10%',response.data)

    def test_settings_versions_validation_and_stale_save(self):
        save_policy('Litet',self.settings());self.assertTrue(get_policy('Litet')['confirmed'])
        with self.assertRaisesRegex(ValueError,'another view'):save_policy('Litet',self.settings(policy_id=''))
        for field,value in [('prior_clicks','nan'),('attribution_days','1'),('max_loss_probability','101'),('profit_reserve_per_order','-1')]:
            with self.assertRaises(ValueError):save_policy('Litet',self.settings(**{field:value}))

    def test_documented_candidate_and_risk_visibility_guards(self):
        save_policy('Litet',self.settings());r=self.review()
        result=evaluate_candidate(r,self.candidate(r));self.assertTrue(result['eligible'])
        self.assertAlmostEqual(result['mean_gain'],5)
        assumed=evaluate_candidate(r,self.candidate(r,evidence_kind='assumption'))
        self.assertFalse(assumed['eligible'])
        self.assertTrue(any('assumption' in s for s in assumed['blockers']))
        thin=evaluate_candidate(r,self.candidate(r,candidate_clicks_low='2',candidate_clicks_high='2'))
        self.assertFalse(thin['eligible']);self.assertTrue(any('visibility' in s for s in thin['blockers']))
        stale=evaluate_candidate(r,self.candidate(r,settings_date='2026-10-19'))
        self.assertFalse(stale['eligible'])
        risk=evaluate_candidate(r,self.candidate(r,candidate_cpc_low='4',candidate_cpc_high='4'))
        self.assertFalse(risk['eligible'])
        with self.assertRaises(ValueError):evaluate_candidate(r,self.candidate(r,margin_low='inf'))

    def test_company_spillover_changes_the_proposal(self):
        save_policy('Litet',self.settings());r=self.review()
        good=evaluate_candidate(r,self.candidate(r))
        bad=evaluate_candidate(r,self.candidate(r,spillover_low='-10',spillover_high='-10'))
        self.assertAlmostEqual(good['mean_gain']-bad['mean_gain'],10)
        self.assertFalse(bad['eligible'])

    def test_zero_gaps_do_not_become_complete_data(self):
        with sqlite3.connect(self.facts) as c:c.execute("DELETE FROM ppc_fact_clean WHERE report_date='2026-10-05'")
        r=self.review();self.assertNotEqual(r['loaded_mature_days'],r['expected_mature_days'])
        self.assertIsNone(r['company']['tacos'])
        save_policy('Litet',self.settings());r=self.review()
        self.assertFalse(evaluate_candidate(r,self.candidate(r))['eligible'])

    def test_post_csrf_and_legacy_percentage_bypass_rejected(self):
        self.assertEqual(self.client.post('/ppc/evidence/settings',data=self.base).status_code,400)
        response=self.client.post('/decisions/proposals',data={'brand':'Litet','adjustment_pct':'-0.3'})
        self.assertEqual(response.status_code,302);self.assertIn('retired',response.location)
        self.assertFalse(Path(self.state).exists())

    def test_evaluate_propose_approval_and_execution_audit(self):
        token=self.csrf()
        response=self.client.post('/ppc/evidence/settings',data={**self.base,**self.settings(),'csrf_token':token})
        self.assertEqual(response.status_code,302)
        r=self.review();payload={**self.base,**self.candidate(r),'fingerprint':r['fingerprint'],'csrf_token':token}
        response=self.client.post('/ppc/evidence/evaluate',data=payload)
        self.assertEqual(response.status_code,302)
        record=get_evaluation('Litet',1);self.assertTrue(record['result']['eligible']);self.assertNotIn('csrf_token',record['payload'])
        response=self.client.post('/ppc/evidence/propose',data={**self.base,'evaluation_id':'1','csrf_token':token})
        self.assertEqual(response.status_code,302);self.assertIn('recorded',response.location)
        with sqlite3.connect(self.state) as c:
            c.row_factory=sqlite3.Row
            row=dict(c.execute('select rowid audit_id,* from interventions').fetchone())
        self.assertEqual(row['status'],'proposed');self.assertEqual(row['new_value'],1.9)
        url=f"/ppc/evidence/status/{row['audit_id']}"
        response=self.client.post(url,data={**self.base,'csrf_token':token,'status':'approved'})
        self.assertIn('recorded',response.location)
        rejected=self.client.post(url,data={**self.base,'csrf_token':token,'status':'executed'})
        self.assertIn('Confirm',rejected.location)
        response=self.client.post(url,data={**self.base,'csrf_token':token,'status':'executed','amazon_confirmed':'yes'})
        self.assertIn('recorded',response.location)
        with sqlite3.connect(self.state) as c:self.assertEqual(c.execute('select status from interventions').fetchone()[0],'executed')

    def test_evaluation_invalidates_when_data_or_policy_changes(self):
        save_policy('Litet',self.settings());r=self.review();d=self.candidate(r)
        eid=save_evaluation('Litet',r,d,evaluate_candidate(r,d))
        token=self.csrf()
        with sqlite3.connect(self.facts) as c:c.execute("UPDATE ppc_fact_clean SET spend=spend+1 WHERE report_date='2026-10-19'")
        response=self.client.post('/ppc/evidence/propose',data={**self.base,'csrf_token':token,'evaluation_id':eid})
        self.assertIn('stale',response.location)
        self.assertNotEqual(get_evaluation('Litet',eid)['fingerprint'],self.review()['fingerprint'])
        old=self.review()['fingerprint'];save_policy('Litet',self.settings(prior_clicks='20'));self.assertNotEqual(old,self.review()['fingerprint'])

    def test_snapshot_upload_preserves_policies_and_evaluations(self):
        save_policy('Litet',self.settings());r=self.review();d=self.candidate(r)
        save_evaluation('Litet',r,d,evaluate_candidate(r,d))
        candidate=Path(self.temp.name)/'incoming.db'
        with sqlite3.connect(candidate) as c:c.execute('create table unrelated (x)')
        _preserve_railway_tables(candidate,Path(self.state))
        with sqlite3.connect(candidate) as c:
            self.assertEqual(c.execute('select count(*) from ppc_evidence_policies').fetchone()[0],1)
            self.assertEqual(c.execute('select count(*) from ppc_evidence_evaluations').fetchone()[0],1)

    def test_company_costs_once_per_order_and_pacific_dates(self):
        from .ppc_evidence import company_evidence
        with sqlite3.connect(self.facts) as c:
            c.executescript("""
                CREATE TABLE sales_profitability(order_id TEXT,asin TEXT,amazon_fees REAL,fee_status TEXT);
                CREATE TABLE cogs_ledger(asin TEXT,unit_cogs REAL,effective_start TEXT,effective_end TEXT);
                INSERT INTO cogs_ledger VALUES ('A',5,'2026-01-01',NULL);
                DELETE FROM orders;
                INSERT INTO orders VALUES ('matched','A','2026-10-02T02:00:00Z',1,40,0,'Shipped','Shipped');
                INSERT INTO orders VALUES ('matched','A','2026-10-02T02:00:00Z',1,40,0,'Shipped','Shipped');
                INSERT INTO orders VALUES ('next-day','A','2026-10-02T08:00:00Z',1,40,0,'Shipped','Shipped');
                INSERT INTO sales_profitability VALUES ('matched','A',-12,'exact_order_fee_allocated');
            """)
            c.row_factory=sqlite3.Row
            result=company_evidence(c,'Litet','2026-10-01','2026-10-01')
        self.assertEqual(result['sales'],80)
        self.assertEqual(result['before_ads'],58)  # 80 revenue - 10 COGS - 12 fees, once.
        self.assertEqual(result['contribution'],30)  # 35 clicks * .8 = 28 advertising.
        self.assertEqual(result['exact_fee_share'],1)

    def test_policy_rejects_fractional_lookback(self):
        with self.assertRaises(ValueError):save_policy('Litet',self.settings(prior_lookback_days='28.5'))

    def test_both_tabs_share_evidence_all_brand_and_invalid_dates(self):
        for path in ['/ppc?brand=Litet','/decisions?brand=Litet','/ppc?brand=All','/ppc?brand=Has10']:
            response=self.client.get(path+'&start=2026-10-01&end=2026-10-19')
            self.assertEqual(response.status_code,200,path)
            self.assertIn(b'Company outcome across all packs',response.data)
            self.assertNotIn(b'Not working overall',response.data)
        response=self.client.get('/ppc?start=2026-10-19&end=2026-10-01')
        self.assertEqual(response.status_code,400)

if __name__=='__main__':unittest.main()
