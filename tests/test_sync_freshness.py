import sqlite3

import pytest

from scripts import sync_database


def create_tables(conn):
    conn.executescript(
        '''
        CREATE TABLE orders ("purchase-date" TEXT, "sales-channel" TEXT, quantity TEXT);
        CREATE TABLE sales_profitability (sale_date TEXT);
        CREATE TABLE transactions ("Date" TEXT);
        CREATE TABLE transaction_mart (transaction_date TEXT);
        CREATE TABLE ppc ("Date" TEXT);
        CREATE TABLE ppc_fact_clean (report_date TEXT);
        '''
    )


def test_freshness_uses_pacific_and_accepts_two_digit_report_year(tmp_path):
    with sqlite3.connect(tmp_path / "fresh.db") as conn:
        create_tables(conn)
        conn.execute("INSERT INTO orders VALUES (?, 'Amazon.com', '1')", ("2026-10-17T02:44:16+00:00",))
        conn.execute("INSERT INTO sales_profitability VALUES ('2026-10-16')")
        conn.execute("INSERT INTO transactions VALUES ('10/16/26 00:00:00')")
        conn.execute("INSERT INTO transaction_mart VALUES ('2026-10-16')")
        conn.execute("INSERT INTO ppc VALUES ('10/16/26 00:00:00')")
        conn.execute("INSERT INTO ppc_fact_clean VALUES ('2026-10-16')")
        sync_database.validate_analytics_freshness(conn)


def test_freshness_rejects_stale_profitability(tmp_path):
    with sqlite3.connect(tmp_path / "stale.db") as conn:
        create_tables(conn)
        conn.execute("INSERT INTO orders VALUES (?, 'Amazon.com', '1')", ("2026-10-17T08:00:00+00:00",))
        conn.execute("INSERT INTO sales_profitability VALUES ('2026-10-16')")
        with pytest.raises(RuntimeError, match="sales_profitability is stale"):
            sync_database.validate_analytics_freshness(conn)
