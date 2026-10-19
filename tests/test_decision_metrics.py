import sqlite3

from decision_dashboard_v2 import analytics


def test_break_even_tacos_uses_net_sales_denominator(tmp_path, monkeypatch):
    database = tmp_path / "metrics.db"
    with sqlite3.connect(database) as conn:
        conn.executescript(
            '''
            CREATE TABLE dim_product (asin TEXT, canonical_brand TEXT);
            CREATE TABLE cogs_ledger (asin TEXT, unit_cogs REAL, effective_start TEXT, effective_end TEXT);
            CREATE TABLE asin_economics (
                asin TEXT, period_start TEXT, period_end TEXT, net_sales REAL,
                fba_fulfillment_fees REAL, referral_fee REAL, referral_fee_refunds REAL,
                refund_administration_fee REAL, other_fee_total REAL,
                sponsored_products_charge REAL, net_units_sold REAL
            );
            CREATE TABLE business_traffic (
                child_asin TEXT, period_start TEXT, period_end TEXT,
                ordered_product_sales REAL
            );
            INSERT INTO dim_product VALUES ('A1', 'Litet');
            INSERT INTO cogs_ledger VALUES ('A1', 10, '2026-01-01', NULL);
            INSERT INTO asin_economics VALUES (
                'A1', '2026-10-01', '2026-10-31', 100, 10, 10, 0, 0, 0, 60, 1
            );
            INSERT INTO business_traffic VALUES ('A1', '2026-10-01', '2026-10-31', 200);
            '''
        )
    monkeypatch.setenv("LITET_DB_PATH", str(database))
    result = analytics.cost_diagnosis("2026-10-01", "2026-10-31", "Litet")
    assert result["break_even_ad_spend"] == 70
    assert result["break_even_tacos"] == 0.70
