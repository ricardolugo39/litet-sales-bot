import copy
import sqlite3
import unittest
from .ppc_evidence import DEFAULTS, rate_model
from .ppc_history import assess_paid_economics, historical_model, product_margin_scenarios


class HistoryTests(unittest.TestCase):
    def row(self,day,clicks=100,orders=10):
        return dict(report_date=day,clicks=clicks,ad_orders=orders,ad_sales=orders*40,spend=clicks*2)

    def test_future_outcomes_cannot_change_model_or_window(self):
        rows=[self.row(f'2025-{m:02d}-15') for m in range(1,13)]+[self.row('2026-01-05',20,2)]
        peers=[self.row(f'2025-{m:02d}-15',200,20) for m in range(1,13)]
        initial=historical_model(rows,peers,'2026-01-01','2026-01-13',DEFAULTS,rate_model,1)
        changed=historical_model(rows+[self.row('2026-01-14',10000,9999)],peers+[self.row('2026-02-01',10000,9999)],'2026-01-01','2026-01-13',DEFAULTS,rate_model,1)
        self.assertEqual(initial,changed)
        self.assertEqual(initial['history']['clicks'],1200)
        self.assertEqual(initial['audit']['month'],'2025-12')
        altered=copy.deepcopy(rows);altered[11].update(ad_orders=100,ad_sales=4000)
        audit_change=historical_model(altered,peers,'2026-01-01','2026-01-13',DEFAULTS,rate_model,1)
        self.assertEqual(initial['selected_months'],audit_change['selected_months'])
        self.assertNotEqual(initial['audit']['actual_orders'],audit_change['audit']['actual_orders'])

    def test_thin_history_cannot_supply_more_prior_clicks_than_observed(self):
        rows=[self.row('2025-12-15',4,3),self.row('2026-01-05',5,0)]
        peers=[self.row('2025-12-15',200,20)]
        model=historical_model(rows,peers,'2026-01-01','2026-01-13',DEFAULTS,rate_model,1)
        self.assertEqual(model['rate']['prior_clicks'],4)
        self.assertLess(model['rate']['mean'],.5)

    def target(self,cpc):
        return dict(history_model={'available':True,'rate':{'mean':.1,'low':.08,'high':.12},
                    'long_history_rate':{'available':True,'low':.08,'high':.12},'aov':40,'all_mature':{'clicks':100}},
                    recent={'clicks':10,'spend':10*cpc},mature={'clicks':100,'spend':100*cpc})

    def economics(self):
        return {'available':True,'low':.4,'high':.5,'complete':True}

    def test_directions_do_not_require_any_base_bid(self):
        low=assess_paid_economics(self.target(.5),self.economics())
        high=assess_paid_economics(self.target(3),self.economics())
        mixed=assess_paid_economics(self.target(1.8),self.economics())
        self.assertEqual(low['action'],'Hold; test expansion')
        self.assertEqual(high['action'],'Reduce')
        self.assertEqual(mixed['action'],'Hold; review product mix')
        self.assertIn('not incremental company profit',high['scope'])
        self.assertNotIn('candidate_bid',high)
        inactive=self.target(3);inactive.update(recent_period_present=True,recent={'clicks':0,'spend':0})
        self.assertEqual(assess_paid_economics(inactive,self.economics())['action'],'Review delivery before changing bid')

    def test_long_history_sensitivity_and_uncovered_costs_prevent_false_certainty(self):
        target=self.target(.5);target['history_model']['long_history_rate']['low']=0
        result=assess_paid_economics(target,self.economics())
        self.assertNotIn('Yes',result['result'])
        target['history_model']['all_mature']['clicks']=0
        self.assertEqual(assess_paid_economics(target,self.economics())['result'],'No mature target results')
        self.assertEqual(assess_paid_economics(self.target(3),dict(self.economics(),complete=False))['result'],'Covered-SKU scenario leans unprofitable')

    def test_cost_scenarios_use_asof_exact_sku_economics_without_future_or_unknown_fees(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
        c.executescript('''CREATE TABLE dim_product(asin TEXT,canonical_brand TEXT,is_current INTEGER);
        CREATE TABLE sales_profitability(asin TEXT,sale_date TEXT,item_price_revenue REAL,contribution_profit_before_ads REAL,fee_status TEXT,cogs_amount REAL);
        INSERT INTO dim_product VALUES ('A','Litet',1),('B','Litet',1);
        INSERT INTO sales_profitability VALUES ('A','2026-01-03',100,40,'exact_order_fee_allocated',10),('A','2026-02-03',100,99,'exact_order_fee_allocated',10),('B','2026-01-03',100,90,'missing',10);''')
        result=product_margin_scenarios(c,'Litet','2026-01-13')
        self.assertEqual(result['low'],.4);self.assertEqual(result['high'],.4)
        self.assertFalse(result['complete']);self.assertEqual(result['covered_products'],1)
        c.close()

if __name__=='__main__':unittest.main()
