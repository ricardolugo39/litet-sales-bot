import os
import sqlite3
from datetime import date
from statistics import median
from pathlib import Path

from dotenv import load_dotenv

if __package__:
    from .competitor_data import CAPTURED_AT, HAS10_KEYWORDS_CAPTURED_AT, HAS10_KEYWORD_OPPORTUNITIES, LITET_KEYWORDS_CAPTURED_AT, LITET_KEYWORD_HISTORY, LITET_PARENT_KEYWORD_OPPORTUNITIES, MARKET_SNAPSHOTS
    from .helium_store import latest_snapshot
else:  # Supports `python app.py` from this directory.
    from competitor_data import CAPTURED_AT, HAS10_KEYWORDS_CAPTURED_AT, HAS10_KEYWORD_OPPORTUNITIES, LITET_KEYWORDS_CAPTURED_AT, LITET_KEYWORD_HISTORY, LITET_PARENT_KEYWORD_OPPORTUNITIES, MARKET_SNAPSHOTS
    from helium_store import latest_snapshot


load_dotenv()


def database_path():
    """Resolve at connection time so tests and offline fallback can switch DBs."""
    return os.getenv(
        "LITET_DB_PATH",
        str(Path(__file__).with_name("data") / "litet.db"),
    )


def connect():
    conn = sqlite3.connect(database_path())
    conn.row_factory = sqlite3.Row
    return conn


def helium_data():
    """Return the latest complete DB snapshot, with the curated file as fallback."""
    live = latest_snapshot(database_path())
    if not live:
        return {
            "captured_at": CAPTURED_AT,
            "markets": MARKET_SNAPSHOTS,
            "keywords": {
                "Litet": LITET_PARENT_KEYWORD_OPPORTUNITIES,
                "Has10": HAS10_KEYWORD_OPPORTUNITIES,
            },
            "keyword_dates": {
                "Litet": LITET_KEYWORDS_CAPTURED_AT,
                "Has10": HAS10_KEYWORDS_CAPTURED_AT,
            },
            "history": {"Litet": LITET_KEYWORD_HISTORY, "Has10": []},
            "source": "curated_fallback",
        }
    markets = {}
    keywords = {}
    history = {}
    keyword_dates = {}
    for brand, brand_data in live["brands"].items():
        fallback = MARKET_SNAPSHOTS.get(brand, {})
        markets[brand] = {
            "own_parent": brand_data["parent_asin"],
            "own": brand_data["own"],
            "competitors": brand_data["competitors"],
            "sales_benchmark": brand_data.get("sales_benchmark"),
            "pack_benchmarks": brand_data.get(
                "pack_benchmarks", fallback.get("pack_benchmarks", [])
            ),
        }
        keywords[brand] = brand_data["keywords"]
        history[brand] = brand_data.get("keyword_history", [])
        keyword_dates[brand] = brand_data.get("keywords_captured_at", live["captured_at"])
    return {
        "captured_at": live["captured_at"],
        "markets": markets,
        "keywords": keywords,
        "keyword_dates": keyword_dates,
        "history": history,
        "source": "helium10_mcp",
    }


def _keyword_history(brand):
    helium = helium_data()
    history = helium["history"].get(brand, [])
    if history:
        return history
    return [
        {
            "phrase": row["phrase"],
            "jul_rank": None,
            "aug_rank": row.get("rank"),
            "jul_volume": None,
            "aug_volume": row.get("search_volume"),
            "aug_sponsored_rank": row.get("sponsored_rank"),
        }
        for row in helium["keywords"].get(brand, [])
    ]


def periods():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.period_start, t.period_end, t.period_type,
                   CASE WHEN e.period_start IS NULL THEN 0 ELSE 1 END AS has_economics
            FROM (SELECT DISTINCT period_start, period_end, period_type FROM business_traffic) t
            LEFT JOIN (SELECT DISTINCT period_start, period_end FROM asin_economics) e
              USING (period_start, period_end)
            ORDER BY t.period_start DESC, t.period_end DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def ppc_periods():
    """PPC date presets; daily PPC facts support ranges beyond imported report periods."""
    import calendar
    from datetime import date
    base = periods()
    if not base:
        return []
    latest = date.fromisoformat(max(row["period_end"] for row in base))
    quarter_month = ((latest.month - 1) // 3) * 3 + 1
    current_start = latest.replace(day=1).isoformat()
    current_has_economics = int(any(
        row.get("has_economics")
        and row["period_start"] >= current_start
        and row["period_end"] <= latest.isoformat()
        for row in base
    ))
    presets = [
        {"period_start": latest.replace(month=quarter_month, day=1).isoformat(),
         "period_end": latest.isoformat(), "period_type": "qtd", "has_economics": 1,
         "label": f"QTD · Q{((latest.month - 1)//3)+1} {latest.year}", "group":"Quick ranges"},
        {"period_start": latest.replace(month=1, day=1).isoformat(),
         "period_end": latest.isoformat(), "period_type": "ytd", "has_economics": 1,
         "label": f"YTD · {latest.year}", "group":"Quick ranges"},
    ]
    monthly = {}
    for row in base:
        item=dict(row)
        start=date.fromisoformat(item["period_start"]); end=date.fromisoformat(item["period_end"])
        # A report that crosses a month boundary cannot represent either calendar
        # month by itself. The synthetic current-MTD choice below covers the latest
        # month, while completed/partial single-month uploads supply history.
        if (start.year, start.month) != (end.year, end.month):
            continue
        if (end.year, end.month) == (latest.year, latest.month):
            continue
        key = (start.year, start.month)
        existing = monthly.get(key)
        if existing is None or end > date.fromisoformat(existing["period_end"]):
            monthly[key] = item

    choices=[]
    for (year, month), item in sorted(monthly.items(), reverse=True):
        end=date.fromisoformat(item["period_end"])
        item["period_start"] = date(year, month, 1).isoformat()
        # Only the latest calendar month is MTD. Once a newer month is loaded,
        # prior months become one closed, month-level choice in the filter.
        item["label"] = f"{calendar.month_name[month]} {year}"
        item["group"]="Monthly periods"
        choices.append(item)
    choices.insert(0, {
        "period_start": current_start, "period_end": latest.isoformat(),
        "period_type": "mtd", "has_economics": current_has_economics,
        "label": f"{calendar.month_name[latest.month]} {latest.year} MTD · through {latest.day}",
        "group": "Monthly periods",
    })
    seen={(r["period_start"],r["period_end"]) for r in choices}
    return [p for p in presets if (p["period_start"],p["period_end"]) not in seen] + choices


def _brand_clause(alias, brand):
    if brand == "All":
        return "1=1", []
    return f"{alias}.canonical_brand = ?", [brand]


def overview(period_start, period_end, brand):
    where, params = _brand_clause("p", brand)
    with connect() as conn:
        traffic = conn.execute(
            f"""
            WITH period_asin_traffic AS (
              SELECT period_start, period_end, child_asin AS asin,
                     MAX(sessions_total) AS sessions,
                     MAX(page_views_total) AS page_views,
                     SUM(units_ordered) AS units,
                     SUM(ordered_product_sales) AS ordered_sales,
                     MAX(featured_offer_percentage) AS buy_box
              FROM business_traffic
              WHERE period_start>=? AND period_end<=?
              GROUP BY period_start, period_end, child_asin
            ), asin_traffic AS (
              SELECT asin, SUM(sessions) sessions, SUM(page_views) page_views,
                     SUM(units) units, SUM(ordered_sales) ordered_sales, AVG(buy_box) buy_box
              FROM period_asin_traffic GROUP BY asin
            )
            SELECT COALESCE(SUM(a.sessions),0) sessions,
                   COALESCE(SUM(a.page_views),0) page_views,
                   COALESCE(SUM(a.units),0) units,
                   COALESCE(SUM(a.ordered_sales),0) ordered_sales,
                   CASE WHEN SUM(a.sessions)>0 THEN 1.0*SUM(a.units)/SUM(a.sessions) END conversion,
                   AVG(a.buy_box) buy_box
            FROM asin_traffic a JOIN dim_product p ON p.asin=a.asin
            WHERE {where}
            """,
            [period_start, period_end, *params],
        ).fetchone()
        economics = conn.execute(
            f"""
            SELECT COALESCE(SUM(e.units_sold),0) units_sold,
                   COALESCE(SUM(e.units_returned),0) returns,
                   COALESCE(SUM(e.net_sales),0) net_sales,
                   COALESCE(SUM(e.sponsored_products_charge),0) ad_spend,
                   COALESCE(SUM(e.net_proceeds),0) net_proceeds,
                   COALESCE(SUM(e.fba_fulfillment_fees),0) fulfillment_fees,
                   COALESCE(SUM(e.referral_fee + e.referral_fee_refunds),0) referral_net,
                   COALESCE(SUM(e.net_units_sold * COALESCE((
                     SELECT c.unit_cogs FROM cogs_ledger c
                     WHERE c.asin=e.asin AND c.effective_start<=e.period_end
                       AND (c.effective_end IS NULL OR c.effective_end>=e.period_start)
                     ORDER BY c.effective_start DESC LIMIT 1
                   ),0)),0) estimated_cogs,
                   CASE WHEN SUM(e.units_sold)>0 THEN 1.0*SUM(e.units_returned)/SUM(e.units_sold) END return_rate
            FROM asin_economics e JOIN dim_product p ON p.asin=e.asin
            WHERE e.period_start>=? AND e.period_end<=? AND {where}
            """,
            [period_start, period_end, *params],
        ).fetchone()
    result = {**dict(traffic), **dict(economics)}
    result["tacos"] = result["ad_spend"] / result["ordered_sales"] if result["ordered_sales"] else None
    result["contribution_after_cogs"] = result["net_proceeds"] - result["estimated_cogs"]
    result["contribution_margin"] = result["contribution_after_cogs"] / result["net_sales"] if result["net_sales"] else None
    result["amazon_costs_ex_ads"] = result["net_sales"] - result["net_proceeds"] - result["ad_spend"]
    diagnostics = product_diagnostics(period_start, period_end, brand)
    result["inventory_at_risk"] = sum(
        row["inventory"] for row in diagnostics
        if row["inventory"] > 0 and (row["sessions"] == 0 or row["diagnosis"] == "Conversion weakness")
    )
    return result


def pnl_statement(period_start, period_end, brand):
    metrics = overview(period_start, period_end, brand)
    gross_sales = metrics["net_sales"]
    result = {
        "gross_sales": gross_sales,
        "amazon_costs_ex_ads": metrics["amazon_costs_ex_ads"],
        "ad_spend": metrics["ad_spend"],
        "net_proceeds": metrics["net_proceeds"],
        "cogs": metrics["estimated_cogs"],
        "contribution": metrics["contribution_after_cogs"],
        "margin": metrics["contribution_margin"],
    }
    for key in ("gross_sales", "amazon_costs_ex_ads", "ad_spend", "net_proceeds", "cogs", "contribution"):
        result[f"{key}_pct"] = result[key] / gross_sales if gross_sales else None
    return result


def cost_diagnosis(period_start, period_end, brand):
    where, params = _brand_clause("p", brand)
    with connect() as conn:
        row = conn.execute(
            f"""SELECT COALESCE(SUM(e.net_sales),0) net_sales,
                       COALESCE(SUM(e.fba_fulfillment_fees),0) fulfillment,
                       COALESCE(SUM(e.referral_fee + e.referral_fee_refunds),0) referral,
                       COALESCE(SUM(e.refund_administration_fee),0) refund_admin,
                       COALESCE(SUM(e.other_fee_total),0) other,
                       COALESCE(SUM(e.sponsored_products_charge),0) ads,
                       COALESCE(SUM(e.net_units_sold),0) net_units,
                       COALESCE(SUM(e.net_units_sold * COALESCE((
                         SELECT c.unit_cogs FROM cogs_ledger c
                         WHERE c.asin=e.asin AND c.effective_start<=e.period_end
                           AND (c.effective_end IS NULL OR c.effective_end>=e.period_start)
                         ORDER BY c.effective_start DESC LIMIT 1
                       ),0)),0) cogs
                FROM asin_economics e JOIN dim_product p ON p.asin=e.asin
                WHERE e.period_start>=? AND e.period_end<=? AND {where}""",
            [period_start, period_end, *params],
        ).fetchone()
        traffic_where, traffic_params = _brand_clause("tp", brand)
        ordered = conn.execute(
            f"""WITH asin_sales AS (
                  SELECT child_asin asin, SUM(ordered_product_sales) ordered_sales
                  FROM business_traffic WHERE period_start>=? AND period_end<=? GROUP BY child_asin
                )
                SELECT COALESCE(SUM(a.ordered_sales),0) ordered_sales
                FROM asin_sales a JOIN dim_product tp ON tp.asin=a.asin
                WHERE {traffic_where}""",
            [period_start, period_end, *traffic_params],
        ).fetchone()["ordered_sales"]
    data=dict(row); sales=data["net_sales"]; data["ordered_sales"]=ordered
    data["amazon_ex_ads"]=data["fulfillment"]+data["referral"]+data["refund_admin"]+data["other"]
    data["pre_ad_contribution"]=sales-data["amazon_ex_ads"]-data["cogs"]
    data["break_even_ad_spend"]=max(data["pre_ad_contribution"],0)
    data["break_even_tacos"]=data["break_even_ad_spend"]/ordered if ordered else None
    data["ad_reduction_to_break_even"]=max(data["ads"]-data["break_even_ad_spend"],0)
    data["ad_reduction_pct"]=data["ad_reduction_to_break_even"]/data["ads"] if data["ads"] else None
    data["ten_pct_margin_ad_spend"]=max(data["pre_ad_contribution"]-sales*.10,0)
    for key in ("fulfillment","referral","refund_admin","other","amazon_ex_ads","cogs","pre_ad_contribution"):
        data[f"{key}_pct"]=data[key]/sales if sales else None
    data["fulfillment_per_unit"]=data["fulfillment"]/data["net_units"] if data["net_units"] else None
    data["other_label"]="Inbound placement and other Amazon fees"
    return data


def advertising_detail(period_start, period_end, brand):
    where = "1=1" if brand == "All" else "brand=?"
    params = [] if brand == "All" else [brand]
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT campaign_name, SUM(impressions) impressions, SUM(clicks) clicks,
                       SUM(spend) spend, SUM(ad_sales) ad_sales, SUM(ad_orders) ad_orders,
                       CASE WHEN SUM(ad_sales)>0 THEN SUM(spend)/SUM(ad_sales) END acos,
                       CASE WHEN SUM(clicks)>0 THEN SUM(spend)/SUM(clicks) END cpc,
                       CASE WHEN SUM(clicks)>0 THEN SUM(ad_orders)/SUM(clicks) END cvr
                FROM ppc_fact_clean
                WHERE report_date BETWEEN ? AND ? AND {where}
                GROUP BY campaign_name ORDER BY spend DESC LIMIT 8""",
            [period_start, period_end, *params],
        ).fetchall()
    return [dict(row) for row in rows]


def brand_split(period_start, period_end):
    output = []
    for brand in ("Litet", "Has10"):
        output.append({"brand": brand, **overview(period_start, period_end, brand)})
    return output


def monthly_trend(brand):
    order_where, order_params = _brand_clause("p", brand)
    ppc_where = "1=1" if brand == "All" else "brand=?"
    ppc_params = [] if brand == "All" else [brand]
    with connect() as conn:
        rows = conn.execute(
            f"""
            WITH latest AS (
              SELECT MIN(
                (SELECT MAX(date(substr("purchase-date",1,10))) FROM orders),
                (SELECT MAX(date(report_date)) FROM ppc_fact_clean)
              ) max_date
            ), sales AS (
              SELECT substr(o."purchase-date",1,7) month,
                     SUM(CAST(o.quantity AS REAL)) units,
                     SUM(CAST(o."item-price" AS REAL)
                         - COALESCE(CAST(o."item-promotion-discount" AS REAL),0)) ordered_sales
              FROM orders o JOIN dim_product p ON p.asin=o.asin, latest
              WHERE date(substr(o."purchase-date",1,10)) <= latest.max_date
                AND substr(o."purchase-date",1,4) = substr(latest.max_date,1,4)
                AND COALESCE(o."order-status",'') NOT IN ('Cancelled','Canceled')
                AND COALESCE(o."item-status",'') NOT IN ('Cancelled','Canceled')
                AND {order_where}
              GROUP BY substr(o."purchase-date",1,7)
            ), ads AS (
              SELECT substr(report_date,1,7) month, SUM(spend) ad_spend
              FROM ppc_fact_clean, latest
              WHERE date(report_date) <= latest.max_date
                AND substr(report_date,1,4) = substr(latest.max_date,1,4)
                AND {ppc_where}
              GROUP BY substr(report_date,1,7)
            )
            SELECT s.month || '-01' period_start,
                   CASE WHEN s.month=(SELECT substr(max_date,1,7) FROM latest)
                        THEN (SELECT max_date FROM latest)
                        ELSE date(s.month || '-01','+1 month','-1 day') END period_end,
                   CASE WHEN s.month=(SELECT substr(max_date,1,7) FROM latest) THEN 'mtd' ELSE 'monthly' END period_type,
                   NULL sessions, s.units, s.ordered_sales, NULL conversion,
                   COALESCE(a.ad_spend,0) ad_spend,
                   CASE WHEN s.ordered_sales>0 THEN COALESCE(a.ad_spend,0)/s.ordered_sales END tacos
            FROM sales s LEFT JOIN ads a ON a.month=s.month
            ORDER BY s.month
            """,
            [*order_params, *ppc_params],
        ).fetchall()
    result=[dict(row) for row in rows]
    for row in result:
        row["is_partial"]=row["period_type"] != "monthly"
    return result


def seasonality_matrix(brand, asin=None):
    import calendar
    where, params = _brand_clause("p", brand)
    asin_filter="AND o.asin=?" if asin else ""
    asin_params=[asin] if asin else []
    with connect() as conn:
        rows=conn.execute(f"""SELECT substr(o."purchase-date",1,4) year,
                  substr(o."purchase-date",6,2) month,
                  SUM(CAST(o.quantity AS REAL)) units,
                  SUM(CAST(o.quantity AS REAL) * COALESCE(p.units_per_sellable_unit,1)) physical_units
          FROM orders o JOIN dim_product p ON p.asin=o.asin AND p.is_current=1
          WHERE {where} {asin_filter} AND o."order-status" NOT IN ('Cancelled','Pending')
          GROUP BY 1,2 ORDER BY 1,2""",[*params,*asin_params]).fetchall()
        latest=conn.execute(f"""SELECT MAX(substr(o."purchase-date",1,10)) latest_date
          FROM orders o JOIN dim_product p ON p.asin=o.asin AND p.is_current=1
          WHERE {where} {asin_filter} AND o."order-status" NOT IN ('Cancelled','Pending')""",
          [*params,*asin_params]).fetchone()["latest_date"]
    years=sorted({r["year"] for r in rows})[-3:]
    lookup={(r["year"],int(r["month"])):r["units"] or 0 for r in rows}
    physical_lookup={(r["year"],int(r["month"])):r["physical_units"] or 0 for r in rows}
    latest_year=latest[:4] if latest else None; latest_month=int(latest[5:7]) if latest else None; latest_day=int(latest[8:10]) if latest else None
    matrix=[]
    for month in range(1,13):
        values={year:lookup.get((year,month)) for year in years}
        physical_values={year:physical_lookup.get((year,month)) for year in years}
        current=values.get(latest_year) if latest_year in values else None
        physical_current=physical_values.get(latest_year) if latest_year in physical_values else None
        is_mtd=bool(latest and month==latest_month and latest_year in years)
        projection=(current/latest_day*calendar.monthrange(int(latest_year),month)[1]
                    if is_mtd and current is not None and latest_day else None)
        physical_projection=(physical_current/latest_day*calendar.monthrange(int(latest_year),month)[1]
                    if is_mtd and physical_current is not None and latest_day else None)
        matrix.append({"month":month,"month_name":calendar.month_abbr[month],"values":values,
                       "physical_values":physical_values,"is_mtd":is_mtd,"projection":projection,
                       "physical_projection":physical_projection})
    complete_years=[y for y in years if y!=latest_year]
    prior_year=complete_years[-1] if complete_years else None
    peak=[]
    if prior_year:
        ranked=sorted(((lookup.get((prior_year,m),0),m) for m in range(1,13)),reverse=True)[:3]
        peak=[calendar.month_abbr[m] for units,m in ranked if units>0]
    history_start=min((r["year"] for r in rows),default=None)
    return {"years":years,"rows":matrix,"latest_date":latest,"latest_year":latest_year,
            "prior_year":prior_year,"peak_months":peak,"history_start":history_start,
            "show_physical_pairs":brand == "Litet",
            "maturity":"Established" if history_start and latest_year and int(latest_year)-int(history_start)>=2 else "Emerging"}


def ppc_coverage(period_start, period_end, brand):
    where = "1=1" if brand == "All" else "brand=?"
    params = [] if brand == "All" else [brand]
    with connect() as conn:
        row = conn.execute(
            f"""SELECT COUNT(DISTINCT report_date) loaded_days, MIN(report_date) first_date,
                       MAX(report_date) last_date, COALESCE(SUM(spend),0) detailed_spend
                FROM ppc_fact_clean WHERE report_date BETWEEN ? AND ? AND {where}""",
            [period_start, period_end, *params],
        ).fetchone()
    from datetime import date
    result = dict(row)
    result["expected_days"] = (date.fromisoformat(period_end)-date.fromisoformat(period_start)).days+1
    result["complete"] = result["loaded_days"] == result["expected_days"]
    return result


def product_diagnostics(period_start, period_end, brand):
    where, params = _brand_clause("p", brand)
    with connect() as conn:
        rows = conn.execute(
            f"""
            WITH period_traffic AS (
              SELECT period_start,period_end,child_asin asin, MAX(sessions_total) sessions,
                     SUM(units_ordered) units, SUM(ordered_product_sales) ordered_sales,
                     MAX(featured_offer_percentage) buy_box
              FROM business_traffic WHERE period_start>=? AND period_end<=?
              GROUP BY period_start,period_end,child_asin
            ), traffic AS (
              SELECT asin,SUM(sessions) sessions,SUM(units) units,SUM(ordered_sales) ordered_sales,AVG(buy_box) buy_box
              FROM period_traffic GROUP BY asin
            ), econ AS (
              SELECT asin,SUM(net_sales) net_sales,SUM(net_proceeds) net_proceeds,
                     SUM(sponsored_products_charge) sponsored_products_charge,SUM(units_returned) units_returned
              FROM asin_economics WHERE period_start>=? AND period_end<=? GROUP BY asin
            ), inv AS (
              SELECT asin, SUM(CAST("Quantity Available" AS REAL)) inventory
              FROM inventory_snapshots
              WHERE snapshot_date=(SELECT MAX(snapshot_date) FROM inventory_snapshots)
              GROUP BY asin
            ), sku_map AS (
              SELECT product_key, GROUP_CONCAT(DISTINCT sku) skus, COUNT(DISTINCT sku) sku_count
              FROM bridge_product_sku WHERE is_current=1 GROUP BY product_key
            )
            SELECT p.asin, p.canonical_brand brand, p.canonical_product_name product,
                   p.color, p.size, p.pack_type, p.product_family,
                   COALESCE(s.skus,'') skus, COALESCE(s.sku_count,0) sku_count,
                   COALESCE(t.sessions,0) sessions, COALESCE(t.units,0) units,
                   COALESCE(t.ordered_sales,0) ordered_sales, t.buy_box,
                   CASE WHEN t.sessions>0 THEN 1.0*t.units/t.sessions END conversion,
                   COALESCE(e.net_sales,0) net_sales, COALESCE(e.net_proceeds,0) net_proceeds,
                   COALESCE(e.sponsored_products_charge,0) ad_spend,
                   COALESCE(e.units_returned,0) returns, COALESCE(inv.inventory,0) inventory
            FROM dim_product p
            LEFT JOIN traffic t ON t.asin=p.asin
            LEFT JOIN econ e ON e.asin=p.asin
            LEFT JOIN inv ON inv.asin=p.asin
            LEFT JOIN sku_map s ON s.product_key=p.product_key
            WHERE p.is_current=1 AND {where}
            ORDER BY t.units DESC, t.sessions DESC
            """,
            [period_start, period_end, period_start, period_end, *params],
        ).fetchall()
    data = [dict(row) for row in rows]
    conversions = sorted(row["conversion"] for row in data if row["conversion"] is not None)
    median = conversions[len(conversions)//2] if conversions else 0
    for row in data:
        if row["inventory"] > 0 and row["sessions"] == 0:
            row["diagnosis"] = "No traffic"
        elif row["sessions"] >= 20 and row["units"] == 0:
            row["diagnosis"] = "Traffic, no orders"
        elif row["conversion"] is not None and row["conversion"] < median * 0.6:
            row["diagnosis"] = "Conversion weakness"
        elif row["inventory"] == 0 and row["units"] > 0:
            row["diagnosis"] = "Inventory risk"
        else:
            row["diagnosis"] = "Healthy / monitor"
    return data


def product_portfolio(period_start, period_end, brand):
    """Analyze the complete current catalog, including products with no activity."""
    from datetime import date

    rows = product_diagnostics(period_start, period_end, brand)
    prior_period = previous_period(period_start)
    old_rows = (product_diagnostics(prior_period["period_start"], prior_period["period_end"], brand)
                if prior_period else [])
    old_by_asin = {row["asin"]: row for row in old_rows}
    days = (date.fromisoformat(period_end) - date.fromisoformat(period_start)).days + 1
    old_days = ((date.fromisoformat(prior_period["period_end"])
                 - date.fromisoformat(prior_period["period_start"])).days + 1
                if prior_period else 1)

    status_order = {"Act now": 0, "Watch": 1, "Growth opportunity": 2,
                    "Insufficient evidence": 3, "Healthy—no action": 4}
    for row in rows:
        old = old_by_asin.get(row["asin"], {})
        sales_rate = (row["ordered_sales"] or 0) / days
        old_sales_rate = (old.get("ordered_sales") or 0) / old_days
        traffic_rate = (row["sessions"] or 0) / days
        old_traffic_rate = (old.get("sessions") or 0) / old_days
        row["sales_pace_change"] = sales_rate / old_sales_rate - 1 if old_sales_rate else None
        row["traffic_pace_change"] = traffic_rate / old_traffic_rate - 1 if old_traffic_rate else None
        daily_units = (row["units"] or 0) / days
        row["days_cover"] = row["inventory"] / daily_units if daily_units else None
        row["sku_list"] = [sku for sku in (row.get("skus") or "").split(",") if sku]

        if row["inventory"] <= 0 and row["units"] > 0:
            status, reason = "Act now", "Sales occurred but no FBA inventory is currently available."
        elif row["inventory"] > 0 and row["sessions"] == 0:
            status, reason = "Act now", "Available inventory recorded no traffic in the selected period."
        elif row["sessions"] >= 20 and row["units"] == 0:
            status, reason = "Act now", "Material traffic produced no orders; inspect the offer and variation placement."
        elif row["net_proceeds"] < 0 and row["ad_spend"] > 0:
            status, reason = "Watch", "Settlement review is required; this accounting signal is not permission to cut PPC."
        elif row["sessions"] < 10 and row["units"] < 2:
            status, reason = "Insufficient evidence", "Too little selected-period demand to support a product change."
        elif row["diagnosis"] == "Conversion weakness" or (row["sales_pace_change"] is not None and row["sales_pace_change"] < -.15):
            status, reason = "Watch", "Demand pace or conversion is weak enough to require diagnosis before intervention."
        elif row["sales_pace_change"] is not None and row["sales_pace_change"] > .10:
            status, reason = "Growth opportunity", "Daily sales pace is up; validate inventory and scalable traffic."
        else:
            status, reason = "Healthy—no action", "No material product-level exception is supported by current evidence."
        row.update(status=status, status_rank=status_order[status], status_reason=reason)

    with connect() as conn:
        proven = conn.execute(
            """SELECT search_term, SUM(ad_orders) orders, SUM(spend) spend, SUM(ad_sales) sales,
                      CASE WHEN SUM(ad_sales)>0 THEN SUM(spend)/SUM(ad_sales) END acos
               FROM ppc_fact_clean
               WHERE brand=? AND report_date BETWEEN ? AND ? AND TRIM(COALESCE(search_term,''))<>''
               GROUP BY LOWER(TRIM(search_term))
               HAVING SUM(ad_orders)>=2 AND SUM(ad_sales)>0 AND SUM(spend)/SUM(ad_sales)<=0.50
               ORDER BY SUM(ad_orders) DESC, SUM(ad_sales) DESC LIMIT 3""",
            (brand, period_start, period_end),
        ).fetchall() if brand in {"Litet", "Has10"} else []
    proven_terms = [dict(term) for term in proven]
    hero = max(rows, key=lambda row: row["ad_spend"] or 0, default=None)
    candidates = [row for row in rows if hero and row["asin"] != hero["asin"]
                  and row["pack_type"] == hero["pack_type"] and row["sessions"] >= 25
                  and row["units"] >= 3 and (row["days_cover"] or 0) >= 30]
    candidate = max(candidates, key=lambda row: (row["conversion"] or 0, row["units"]), default=None)
    term_names = ", ".join(f"‘{term['search_term']}’" for term in proven_terms) or "the proven queries on the PPC page"

    for row in rows:
        row["is_ppc_hero"] = bool(hero and row["asin"] == hero["asin"])
        row["is_ppc_test_candidate"] = bool(candidate and row["asin"] == candidate["asin"])
        row["average_order_value"] = row["ordered_sales"] / row["units"] if row["units"] else None
        price_label = f"${row['average_order_value']:.2f}" if row["average_order_value"] else "the current price"
        if row["inventory"] <= 0 and row["units"] > 0:
            row["pricing_action"] = "Hold price; a price test is invalid while inventory is unavailable."
            row["ppc_action"] = "Do not send additional paid traffic until FBA availability is restored."
            row["measurement_plan"] = "After restock, require 7 complete days of sessions, units and conversion before changing either lever."
        elif row["is_ppc_hero"]:
            row["status_reason"] = (f"This ASIN carries the largest allocated ad charge and {row['units']:.0f} selected-period orders, so it remains the control for PPC changes.")
            row["pricing_action"] = f"Hold approximately {price_label}; selected-period settlement does not support a price cut."
            row["ppc_action"] = "Keep this ASIN as the primary PPC destination. Change only the campaign targets identified on the PPC page—not the entire campaign."
            row["measurement_plan"] = "For each target change, compare 7 complete days of total units, sessions, CVR, organic rank and contribution; confirm at 14 days."
        elif row["is_ppc_test_candidate"]:
            row["status_reason"] = (f"It converted {(row['conversion'] or 0):.1%} from {row['sessions']:.0f} sessions and has approximately {row['days_cover']:.0f} days of cover—the strongest same-pack candidate outside the hero.")
            row["pricing_action"] = f"Hold approximately {price_label} so the PPC test has one changing variable."
            row["ppc_action"] = f"Test as a secondary advertised ASIN with 10–15% of the hero budget using EXACT {term_names}."
            row["measurement_plan"] = "Run 7 complete days. Expand only if incremental sessions convert without reducing hero-ASIN units or total contribution."
        elif row["sessions"] >= 40 and (row["conversion"] or 0) < .03:
            row["pricing_action"] = "Do not cut price yet; first isolate whether traffic is relevant and the variation is visible."
            row["ppc_action"] = "Do not add child-specific PPC until query relevance and variation placement are verified."
            row["measurement_plan"] = "Reassess after 7 days; consider a price test only if qualified traffic remains high and CVR remains below 3%."
        elif row["status"] == "Growth opportunity":
            row["pricing_action"] = "Hold price; rising daily sales does not justify introducing a second variable."
            row["ppc_action"] = "No separate campaign yet; this product was not the strongest controlled-test candidate."
            row["measurement_plan"] = "Monitor 7-day sales pace, conversion and inventory while the single secondary-ASIN test runs."
        else:
            row["pricing_action"] = "Hold price; no product-level price intervention is supported."
            row["ppc_action"] = "No child-specific PPC change. Keep learning concentrated in the hero and selected test ASIN."
            row["measurement_plan"] = "Review weekly; intervene only after a material traffic, conversion or inventory exception."
        row["evidence_limit"] = ("Amazon advertising charges are allocated to ASIN economics, but search-term history does not prove which child variation caused the order."
                                 if row["ad_spend"] else
                                 "No child-level PPC attribution is available; this recommendation uses product traffic, sales and inventory evidence.")

    strategy = {
        "hero": hero, "candidate": candidate, "proven_terms": proven_terms,
        "headline": (f"Keep {hero['color']} {hero['size']} {hero['pack_type']} as the PPC hero"
                     if hero else "No PPC hero resolved"),
        "recommendation": (f"Run one controlled secondary-ASIN test on {candidate['color']} {candidate['size']} {candidate['pack_type']}; keep all other child PPC unchanged."
                           if candidate else "Keep PPC concentrated in the current hero until another child has enough conversion and inventory evidence."),
    }

    def rollup(field, label):
        grouped = {}
        for row in rows:
            name = row.get(field) or "Unspecified"
            group = grouped.setdefault(name, {"name": name, "label": label, "rows": [],
                "sessions": 0, "units": 0, "sales": 0, "inventory": 0, "net_proceeds": 0,
                "sku_count": 0, "asins": 0})
            group["rows"].append(row)
            group["asins"] += 1
            group["sku_count"] += row["sku_count"]
            for source, target in (("sessions","sessions"),("units","units"),
                                   ("ordered_sales","sales"),("inventory","inventory"),
                                   ("net_proceeds","net_proceeds")):
                group[target] += row[source] or 0
        for group in grouped.values():
            group["conversion"] = group["units"] / group["sessions"] if group["sessions"] else None
            group["rows"].sort(key=lambda row: (row["status_rank"], -(row["ordered_sales"] or 0)))
            group["status"] = group["rows"][0]["status"]
            group["open"] = group["status"] in {"Act now", "Watch"}
            group["status_counts"] = {status: sum(r["status"] == status for r in group["rows"])
                                      for status in status_order}
        return sorted(grouped.values(), key=lambda g: (status_order[g["status"]], -g["sales"]))

    rows.sort(key=lambda row: (row["status_rank"], -(row["ordered_sales"] or 0)))
    coverage = {
        "asins": len(rows), "skus": sum(row["sku_count"] for row in rows),
        "packs": len({row["pack_type"] for row in rows}),
        "colors": len({row["color"] for row in rows if row["color"]}),
        "sizes": len({row["size"] for row in rows if row["size"]}),
        "status_counts": {status: sum(row["status"] == status for row in rows)
                          for status in status_order},
    }
    return {"coverage": coverage, "pack_groups": rollup("pack_type", "Pack family"),
            "color_groups": rollup("color", "Color"), "size_groups": rollup("size", "Size"),
            "products": rows, "prior_period": prior_period, "strategy": strategy}


def previous_period(period_start):
    with connect() as conn:
        row = conn.execute(
            "SELECT period_start, period_end FROM business_traffic WHERE period_end < ? GROUP BY period_start, period_end ORDER BY period_end DESC LIMIT 1",
            (period_start,),
        ).fetchone()
    return dict(row) if row else None


def action_queue(period_start, period_end, brand):
    from datetime import date
    current = product_diagnostics(period_start, period_end, brand)
    previous = previous_period(period_start)
    prior_rows = product_diagnostics(previous["period_start"], previous["period_end"], brand) if previous else []
    prior = {row["asin"]: row for row in prior_rows}
    days = (date.fromisoformat(period_end) - date.fromisoformat(period_start)).days + 1
    old_days = (date.fromisoformat(previous["period_end"]) - date.fromisoformat(previous["period_start"])).days + 1 if previous else 1
    actions = []
    for row in current:
        old = prior.get(row["asin"], {})
        current_rate = row["ordered_sales"] / days
        old_rate = old.get("ordered_sales", 0) / old_days
        lost_revenue_30d = max(old_rate - current_rate, 0) * 30
        sales_change = current_rate / old_rate - 1 if old_rate else None
        current_traffic = row["sessions"] / days
        old_traffic = old.get("sessions", 0) / old_days
        traffic_change = current_traffic / old_traffic - 1 if old_traffic else None
        cvr_change = (row.get("conversion") or 0) - (old.get("conversion") or 0)
        item = None
        if row["inventory"] >= 10 and row["sessions"] == 0:
            item = (row["inventory"] * 2, "Inventory has no traffic", f"{row['inventory']:.0f} currently available FBA units recorded no sessions.", "Verify listing status, indexing, Buy Box, and advertising coverage.")
        elif row["net_proceeds"] < 0 and row["ad_spend"] > 0:
            item = (abs(row["net_proceeds"]) + row["ad_spend"], "Advertising allocation exceeds proceeds", f"Amazon allocated ${row['ad_spend']:,.0f} of Sponsored Products charges; net proceeds are -${abs(row['net_proceeds']):,.0f} before COGS.", "Inspect the campaign and search-term drivers before increasing traffic.")
        elif sales_change is not None and sales_change < -0.2:
            if traffic_change is not None and traffic_change < -0.15:
                reason = f"Daily sales fell {abs(sales_change):.0%}, alongside a {abs(traffic_change):.0%} traffic decline; conversion changed {cvr_change:+.1%}."
                next_step = "Recover qualified traffic, then validate conversion before changing price."
            else:
                reason = f"Daily sales fell {abs(sales_change):.0%}; traffic changed {(traffic_change or 0):+.0%} and conversion changed {cvr_change:+.1%}."
                next_step = "Review price, offer quality, reviews, and search-term fit."
            item = (lost_revenue_30d, "Sales run rate is down", reason, next_step)
        elif row["diagnosis"] == "Conversion weakness" and row["sessions"] >= 40:
            item = (row["ordered_sales"] * .25, "Traffic is not converting efficiently", f"The ASIN attracted {row['sessions']:.0f} sessions but converted only {(row['conversion'] or 0):.1%}.", "Evaluate price, promotion, reviews, variation placement, and search-term relevance.")
        if item:
            severity, headline, reason, next_step = item
            actions.append({**row, "severity": severity, "estimated_30d_impact": lost_revenue_30d,
                            "headline": headline, "reason": reason, "next_step": next_step})
    return sorted(actions, key=lambda row: row["severity"], reverse=True)[:6], previous


def market_context(brand):
    helium = helium_data()
    if brand == "All" or brand not in helium["markets"]:
        return None
    snapshot = helium["markets"][brand]
    peers = snapshot["competitors"]
    direct = [p for p in peers if p["segment"] in {"direct", "value"}]
    own = snapshot["own"]
    comparison_sales = (own.get("sales") or 0) + sum((p.get("sales") or 0) for p in peers)
    peer_changes = [p["sales_change"] for p in peers if p["sales_change"] is not None]
    keyword_history = _keyword_history(brand)
    current_keywords = helium["keywords"].get(brand, [])
    strategic_gaps = sorted(
        [k for k in current_keywords
         if k.get("search_volume") and (k.get("rank") is None or k["rank"] > 10)],
        key=lambda k: k["search_volume"], reverse=True)[:6]
    captured_date = date.fromisoformat(helium["captured_at"][:10])
    return {**snapshot, "captured_at": helium["captured_at"], "source": helium["source"],
            "is_stale": (date.today() - captured_date).days > 2,
            "direct_price_median": median([p["price"] for p in direct if p.get("price") is not None]) if any(p.get("price") is not None for p in direct) else None,
            "competitor_sales_median": (median([p["sales"] for p in peers if p.get("sales") is not None])
                                        if any(p.get("sales") is not None for p in peers)
                                        else (snapshot.get("sales_benchmark") or {}).get("monthly_sales")),
            "competitor_keyword_median": median([p["top10_keywords"] for p in peers if p.get("top10_keywords") is not None]) if any(p.get("top10_keywords") is not None for p in peers) else None,
            "review_gap": (median([p["reviews"] for p in peers if p.get("reviews") is not None]) - own["reviews"] if own.get("reviews") is not None and any(p.get("reviews") is not None for p in peers) else None),
            "comparison_share": own["sales"] / comparison_sales if own.get("sales") is not None and comparison_sales else None,
            "peer_median_change": median(peer_changes) if peer_changes else None,
            "keyword_history": keyword_history, "strategic_gaps": strategic_gaps}


def family_diagnostics(period_start, period_end, brand):
    rows = product_diagnostics(period_start, period_end, brand)
    previous = previous_period(period_start)
    old_rows = product_diagnostics(previous["period_start"], previous["period_end"], brand) if previous else []
    def aggregate(source):
        result = {}
        for row in source:
            b = result.setdefault(row["pack_type"], {"sales":0,"sessions":0,"units":0,"inventory":0,"net_proceeds":0,"ad_spend":0,"weakest":None,"weakest_conversion":None,"asins":[]})
            b["asins"].append(row["asin"])
            for key in ("sessions","units","inventory","net_proceeds","ad_spend"): b[key] += row[key] or 0
            b["sales"] += row["ordered_sales"] or 0
            if row["conversion"] is not None and (b["weakest_conversion"] is None or row["conversion"] < b["weakest_conversion"]):
                b["weakest_conversion"], b["weakest"] = row["conversion"], f"{row['color'] or ''} {row['size'] or ''}".strip()
        return result
    current, old = aggregate(rows), aggregate(old_rows)
    output=[]
    for pack,row in current.items():
        row["pack_type"]=pack; row["conversion"]=row["units"]/row["sessions"] if row["sessions"] else None
        before=old.get(pack,{})
        row["sales_change"]=row["sales"]/before["sales"]-1 if before.get("sales") else None
        row["traffic_change"]=row["sessions"]/before["sessions"]-1 if before.get("sessions") else None
        old_cvr=before.get("units",0)/before["sessions"] if before.get("sessions") else None
        row["conversion_change"]=row["conversion"]-old_cvr if row["conversion"] is not None and old_cvr is not None else None
        if row["sales_change"] is not None and row["sales_change"]<-.15:
            row["diagnosis"]="Investigate"; row["decision_detail"]="Open the pack to isolate traffic vs conversion loss."
        elif row["sales_change"] is not None and row["sales_change"]>.10:
            row["diagnosis"]="Expand"; row["decision_detail"]="Validate inventory coverage and scalable PPC terms."
        else:
            row["diagnosis"]="Protect"; row["decision_detail"]="Maintain price and monitor mix."
        output.append(row)
    return sorted(output,key=lambda r:r["sales"],reverse=True)


def ppc_decisions(period_start, period_end, brand):
    where="1=1" if brand=="All" else "brand=?"; params=[] if brand=="All" else [brand]
    with connect() as conn:
        rows=conn.execute(f"""SELECT campaign_name,target,match_type,search_term,SUM(impressions) impressions,SUM(clicks) clicks,SUM(spend) spend,SUM(ad_sales) ad_sales,SUM(ad_orders) orders,
          CASE WHEN SUM(ad_sales)>0 THEN SUM(spend)/SUM(ad_sales) END acos,CASE WHEN SUM(clicks)>0 THEN SUM(spend)/SUM(clicks) END cpc,CASE WHEN SUM(clicks)>0 THEN SUM(ad_orders)/SUM(clicks) END cvr
          FROM ppc_fact_clean WHERE report_date BETWEEN ? AND ? AND {where} GROUP BY campaign_name,target,match_type,search_term HAVING SUM(spend)>0 ORDER BY SUM(spend) DESC LIMIT 30""",[period_start,period_end,*params]).fetchall()
    rank_lookup = {k["phrase"].lower(): k for k in _keyword_history(brand)}
    data=[]
    for raw in rows:
        row=dict(raw)
        keyword = rank_lookup.get((row["search_term"] or "").strip().lower()) or rank_lookup.get((row["target"] or "").strip().lower())
        rank_change = (keyword["aug_rank"] - keyword["jul_rank"]) if keyword and keyword["jul_rank"] and keyword["aug_rank"] else None
        if row["orders"]==0 and row["clicks"]>=8: action,confidence,reason="Review / negative","High","Enough clicks without an attributed order; confirm query relevance before negating."
        elif row["acos"] is not None and row["acos"]>.55 and keyword and keyword["aug_rank"]<=10 and (rank_change is None or rank_change<=1): action,confidence,reason="Reduce cautiously","Medium","Organic rank is already strong and stable; lower in small steps while monitoring total sales."
        elif row["acos"] is not None and row["acos"]>.55 and keyword and rank_change and rank_change>5: action,confidence,reason="Defend / restructure","High","Organic rank deteriorated while demand remained material; isolate converting queries instead of cutting broadly."
        elif row["acos"] is not None and row["acos"]<=.30 and row["orders"]>=2: action,confidence,reason="Protect","Medium","Paid conversion is efficient; maintain while monitoring organic rank and total sales."
        elif row["acos"] is not None and row["acos"]>.55: action,confidence,reason="Hold for evidence","Low","No exact Helium 10 rank match exists for this term, so a bid reduction is not yet supported."
        else: action,confidence,reason="Monitor","Low","Insufficient evidence for a bid change."
        organic_signal = (f"Organic #{keyword['aug_rank']} ({rank_change:+d} vs Jul)" if keyword and rank_change is not None
                          else (f"Organic #{keyword['aug_rank']}" if keyword and keyword['aug_rank'] else "No exact rank match"))
        row.update(action=action,confidence=confidence,reason=reason,organic_signal=organic_signal,keyword=keyword); data.append(row)
    return data


def keyword_playbook(period_start, period_end, brand):
    """Convert PPC facts into a repeatable, campaign-addressable operating plan."""
    if brand not in {"Has10","Litet"}:
        return None
    cost=cost_diagnosis(period_start,period_end,brand)
    contribution_per_order=(cost["pre_ad_contribution"]/cost["net_units"]
                            if cost["net_units"] else 0)
    target_profit_per_order=(cost["net_sales"]/cost["net_units"]*.05
                             if cost["net_units"] else 0)
    allowable_ad_per_order=max(contribution_per_order-target_profit_per_order,0)
    with connect() as conn:
        rows=conn.execute("""SELECT campaign_name,target,match_type,search_term,
                 SUM(impressions) impressions,SUM(clicks) clicks,SUM(spend) spend,
                 SUM(ad_sales) ad_sales,SUM(ad_orders) orders,
                 CASE WHEN SUM(ad_sales)>0 THEN SUM(spend)/SUM(ad_sales) END acos,
                 CASE WHEN SUM(clicks)>0 THEN SUM(spend)/SUM(clicks) END cpc
          FROM ppc_fact_clean
          WHERE brand=? AND report_date BETWEEN ? AND ?
          GROUP BY campaign_name,target,match_type,search_term
          HAVING SUM(clicks)>0
          ORDER BY SUM(ad_orders) DESC,SUM(spend) DESC""",
          (brand,period_start,period_end)).fetchall()
        target_rows=conn.execute("""SELECT campaign_name,target,match_type,
                 SUM(clicks) clicks,SUM(spend) spend,SUM(ad_sales) ad_sales,SUM(ad_orders) orders,
                 CASE WHEN SUM(ad_sales)>0 THEN SUM(spend)/SUM(ad_sales) END acos
          FROM ppc_fact_clean
          WHERE brand=? AND report_date BETWEEN ? AND ?
          GROUP BY campaign_name,target,match_type""",
          (brand,period_start,period_end)).fetchall()
        freshness=conn.execute("""SELECT MIN(report_date) first_loaded_date,MAX(report_date) last_loaded_date,
                 COUNT(DISTINCT report_date) loaded_days
          FROM ppc_fact_clean WHERE brand=?""",(brand,)).fetchone()
    target_lookup={(r["campaign_name"],r["target"],r["match_type"]):dict(r) for r in target_rows}
    rank_lookup={k["phrase"].lower():k for k in _keyword_history(brand)}
    target_plan=[]
    for raw in target_rows:
        target=dict(raw)
        target["cpc"]=target["spend"]/target["clicks"] if target["clicks"] else None
        target["cvr"]=min(target["orders"]/target["clicks"],1) if target["clicks"] else None
        target["modeled_max_cpc"]=(allowable_ad_per_order*target["cvr"]
                                   if target["clicks"]>=5 and target["cvr"] is not None else None)
        rank=rank_lookup.get((target["target"] or "").strip().lower())
        if rank:
            change=(rank["aug_rank"]-rank["jul_rank"] if rank.get("aug_rank") and rank.get("jul_rank") else None)
            target["organic_evidence"]=(f"Organic #{rank['aug_rank']} ({change:+d} vs Jul)" if change is not None
                                         else f"Organic #{rank['aug_rank']}" if rank.get("aug_rank") else "Not ranked")
        else:
            target["organic_evidence"]="No exact H10 rank match" if brand=="Litet" else "H10 keyword history not captured"
        strong_organic=bool(rank and rank.get("aug_rank") and rank["aug_rank"]<=10)
        if target["clicks"]>=8 and target["orders"]==0:
            target["decision"]="Reduce bid 30%"; target["reason"]="Enough target-level clicks without an attributed order."
        elif target["acos"] is not None and target["acos"]>1:
            target["decision"]="Reduce bid 30%"; target["reason"]="Target-level spend exceeds attributed sales."
        elif target["acos"] is not None and target["acos"]>.75:
            cut=15 if strong_organic else 20
            target["decision"]=f"Reduce bid {cut}%"; target["reason"]="Target-level ACoS is above the sustainable range; use a measured cut where organic rank is valuable."
        elif target["acos"] is not None and target["acos"]>.50:
            target["decision"]="Reduce bid 10%"; target["reason"]="The target converts, but the full target total is above the desired economics."
        elif (target["acos"] is not None and target["acos"]<=.30 and
              target["orders"]>=3 and target["clicks"]>=12 and
              target["modeled_max_cpc"] is not None and
              target["modeled_max_cpc"]>=target["cpc"]*1.15 and not strong_organic):
            target["decision"]="Increase bid 10%"
            target["reason"]="Conversion is efficient with sufficient volume, and modeled CPC headroom is at least 15%; increase cautiously and review after 7 days."
        elif target["acos"] is not None and target["acos"]<=.30 and target["orders"]>=2:
            target["decision"]="Hold bid"; target["reason"]="Conversion is efficient, but the evidence or strategic need does not support paying more yet."
        else:
            target["decision"]="Monitor"; target["reason"]="No target-level bid change is supported yet."
        target["confidence"]=("High" if target["clicks"]>=20 and target["orders"]>=5
                              else "Medium" if target["clicks"]>=8 else "Low")
        target_plan.append(target)
    target_plan.sort(key=lambda r:(r["campaign_name"].lower(),-r["spend"],r["target"].lower()))
    campaign_map={}
    for target in target_plan:
        campaign=campaign_map.setdefault(target["campaign_name"],{
            "campaign_name":target["campaign_name"],"targets":[],"spend":0,
            "orders":0,"ad_sales":0,"action_count":0})
        campaign["targets"].append(target)
        campaign["spend"]+=target["spend"] or 0
        campaign["orders"]+=target["orders"] or 0
        campaign["ad_sales"]+=target["ad_sales"] or 0
        if target["decision"].startswith(("Reduce","Increase")):
            campaign["action_count"]+=1
    campaign_groups=[]
    for campaign in campaign_map.values():
        campaign["acos"]=(campaign["spend"]/campaign["ad_sales"]
                           if campaign["ad_sales"] else None)
        campaign["open"]=campaign["action_count"]>0
        campaign["recommendation"]=(f"{campaign['action_count']} bid change{'s' if campaign['action_count']!=1 else ''}"
                                      if campaign["action_count"] else "No immediate bid changes")
        campaign_groups.append(campaign)
    campaign_groups.sort(key=lambda r:(not r["open"],-r["spend"],r["campaign_name"].lower()))
    focus=[]; reduce=[]; watch=[]
    for raw in rows:
        row=dict(raw)
        row["target_total"]=target_lookup.get((row["campaign_name"],row["target"],row["match_type"]),{})
        # Amazon attribution can place more orders than same-period clicks. Cap the
        # observed rate for planning and suppress bid guidance on tiny samples.
        observed_cvr=min(row["orders"]/row["clicks"],1) if row["clicks"] else 0
        row["modeled_max_cpc"]=allowable_ad_per_order*observed_cvr if row["clicks"]>=5 else None
        row["location"]=f"{row['campaign_name']} → {row['target']} ({row['match_type']})"
        rank=rank_lookup.get((row["search_term"] or "").strip().lower()) or rank_lookup.get((row["target"] or "").strip().lower())
        if rank:
            change=(rank["aug_rank"]-rank["jul_rank"] if rank.get("aug_rank") and rank.get("jul_rank") else None)
            row["organic_evidence"]=(f"Organic #{rank['aug_rank']} ({change:+d} vs Jul)" if change is not None
                                     else f"Organic #{rank['aug_rank']}" if rank.get("aug_rank") else "Not ranked")
        else:
            row["organic_evidence"]="No exact H10 rank match" if brand=="Litet" else "H10 keyword history not captured"
        discovered=(row["search_term"] or "").strip().lower() != (row["target"] or "").strip().lower()
        if row["clicks"] < 5 or row["orders"] > row["clicks"]:
            row["decision"]="Watch attribution"
            row["instruction"]="The sample is too small—or attributed orders exceed same-period clicks—so do not create a dedicated target yet."
            watch.append(row)
        elif row["orders"]>=2 and row["acos"] is not None and row["acos"]<=.30:
            row["decision"]="Harvest into EXACT" if discovered or row["match_type"]!="EXACT" else "Protect"
            row["instruction"]=("Create this customer search term as EXACT in the matching color campaign; keep the source active at a controlled bid."
                                if row["decision"]=="Harvest into EXACT" else "Hold the exact target and monitor total sales, not ACoS alone.")
            focus.append(row)
        elif row["orders"]>=2 and row["acos"] is not None and row["acos"]<=.50:
            row["decision"]="Keep, lower CPC"
            row["instruction"]="Keep because it converts, but move it to EXACT and lower the source bid 10–15% until CPC approaches the modeled ceiling."
            focus.append(row)
        elif row["clicks"]>=8 and (row["orders"]==0 or row["acos"] is None or row["acos"]>.65):
            row["decision"]="Reduce source bid"
            cut="30%" if row["orders"]==0 or (row["acos"] or 0)>1 else "20%"
            row["instruction"]=f"Reduce this target in this campaign by {cut}; do not negate the customer term if it converts elsewhere."
            reduce.append(row)
        else:
            row["decision"]="Watch"
            row["instruction"]="Not enough reliable evidence for a dedicated target or negative yet."
            watch.append(row)
    focus.sort(key=lambda r:(r["campaign_name"].lower(),-r["spend"],r["search_term"].lower()))
    reduce.sort(key=lambda r:(r["campaign_name"].lower(),-r["spend"],r["search_term"].lower()))
    watch.sort(key=lambda r:(r["campaign_name"].lower(),-r["spend"],r["search_term"].lower()))
    objective=(f"Preserve the Has10 listing through the season while moving TaCoS toward {cost['break_even_tacos']:.0%} or lower."
               if brand=="Has10" else
               f"Protect Litet's proven traffic while moving TaCoS toward {cost['break_even_tacos']:.0%} or lower and checking organic rank before every material cut.")
    return {"targets":target_plan,"campaigns":campaign_groups,"focus":focus[:15],"reduce":reduce[:12],"watch":watch[:12],
            "contribution_per_order":contribution_per_order,
            "allowable_ad_per_order":allowable_ad_per_order,
            "objective":objective,
            "freshness":dict(freshness),"selected_start":period_start,"selected_end":period_end,
            "method":"Customer search terms show what shoppers typed. Campaign, target, and match type show exactly where the traffic was purchased."}


def ppc_organic_trend(brand):
    if brand == "All":
        return {"months":[],"correlation":None,"total_correlation":None,
                "change_correlation":None,"lagged_correlation":None,
                "sample_months":0,"analysis_start":None,"analysis_end":None,
                "definition":"Select Litet or Has10 to calculate brand-level PPC and non-ad-unit relationships."}
    with connect() as conn:
        orders = conn.execute("""SELECT substr(o."purchase-date",1,7) month,SUM(CAST(o.quantity AS REAL)) total_units
          FROM orders o JOIN dim_product p ON p.asin=o.asin AND p.is_current=1
          WHERE p.canonical_brand=? AND o."order-status" NOT IN ('Cancelled','Pending')
          GROUP BY 1 ORDER BY 1""",(brand,)).fetchall()
        ads = conn.execute("""SELECT substr(report_date,1,7) month,SUM(ad_units) ad_units,SUM(spend) spend,SUM(ad_sales) ad_sales
          FROM ppc_fact_clean WHERE brand=? GROUP BY 1 ORDER BY 1""",(brand,)).fetchall()
        freshness = conn.execute("""SELECT
          (SELECT MAX(substr(o."purchase-date",1,10)) FROM orders o JOIN dim_product p ON p.asin=o.asin AND p.is_current=1 WHERE p.canonical_brand=?) latest_order,
          (SELECT MAX(report_date) FROM ppc_fact_clean WHERE brand=?) latest_ppc""",(brand,brand)).fetchone()
    merged={r["month"]:{"month":r["month"],"total_units":r["total_units"] or 0,"ad_units":0,"spend":0,"ad_sales":0} for r in orders}
    for r in ads:
        b=merged.setdefault(r["month"],{"month":r["month"],"total_units":0,"ad_units":0,"spend":0,"ad_sales":0})
        b.update(ad_units=r["ad_units"] or 0,spend=r["spend"] or 0,ad_sales=r["ad_sales"] or 0)
    months=[]
    latest_incomplete=min(freshness["latest_order"] or "9999-12-31",freshness["latest_ppc"] or "9999-12-31")[:7]
    for b in sorted(merged.values(),key=lambda x:x["month"]):
        b["non_ad_units_proxy"]=max(b["total_units"]-b["ad_units"],0)
        b["is_partial"]=b["month"]>=latest_incomplete
        months.append(b)
    complete=[m for m in months if m["total_units"] and m["spend"] and not m["is_partial"]]
    def correlation(xs,ys):
        if len(xs)<6: return None
        xm=sum(xs)/len(xs); ym=sum(ys)/len(ys)
        den=(sum((x-xm)**2 for x in xs)*sum((y-ym)**2 for y in ys))**.5
        return sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/den if den else None
    spend=[m["spend"] for m in complete]
    total=[m["total_units"] for m in complete]
    non_ad=[m["non_ad_units_proxy"] for m in complete]
    spend_changes=[spend[i]-spend[i-1] for i in range(1,len(spend))]
    non_ad_changes=[non_ad[i]-non_ad[i-1] for i in range(1,len(non_ad))]
    same_period=correlation(spend,non_ad)
    return {"months":months[-12:],"correlation":same_period,
            "total_correlation":correlation(spend,total),
            "change_correlation":correlation(spend_changes,non_ad_changes),
            "lagged_correlation":correlation(spend[:-1],non_ad[1:]),
            "sample_months":len(complete),
            "analysis_start":complete[0]["month"] if complete else None,
            "analysis_end":complete[-1]["month"] if complete else None,
            "definition":"Non-ad proxy = total ordered units minus PPC-attributed units. Amazon attribution windows and seasonality can create timing noise."}


def keyword_opportunities(period_start, period_end, brand):
    helium = helium_data()
    source=helium["keywords"].get(brand, [])
    if not source: return []
    phrases=[row["phrase"] for row in source]
    marks=",".join("?" for _ in phrases)
    with connect() as conn:
        rows=conn.execute(f"""SELECT lower(search_term) phrase,campaign_name,target,match_type,
          SUM(clicks) clicks,SUM(spend) spend,SUM(ad_orders) orders,SUM(ad_sales) ad_sales,
          CASE WHEN SUM(ad_sales)>0 THEN SUM(spend)/SUM(ad_sales) END acos
          FROM ppc_fact_clean WHERE brand=? AND report_date BETWEEN ? AND ?
            AND lower(search_term) IN ({marks})
          GROUP BY lower(search_term),campaign_name,target,match_type
          ORDER BY lower(search_term),SUM(ad_orders) DESC,SUM(spend) DESC""",
          [brand,period_start,period_end,*phrases]).fetchall()
        target_rows=conn.execute("""SELECT campaign_name,target,match_type,SUM(clicks) clicks,
          SUM(spend) spend,SUM(ad_orders) orders,SUM(ad_sales) ad_sales,
          CASE WHEN SUM(ad_sales)>0 THEN SUM(spend)/SUM(ad_sales) END acos
          FROM ppc_fact_clean WHERE brand=? AND report_date BETWEEN ? AND ?
          GROUP BY campaign_name,target,match_type""",(brand,period_start,period_end)).fetchall()
    target_lookup={(r["campaign_name"],r["target"],r["match_type"]):dict(r) for r in target_rows}
    by_phrase={}
    for raw in rows:
        row=dict(raw); by_phrase.setdefault(row["phrase"],[]).append(row)
    output=[]
    for source_row in source:
        item=dict(source_row); evidence=by_phrase.get(item["phrase"],[])
        item["metrics_captured_at"]=helium["keyword_dates"].get(brand, helium["captured_at"])
        item["clicks"]=sum(r["clicks"] or 0 for r in evidence)
        item["orders"]=sum(r["orders"] or 0 for r in evidence)
        item["spend"]=sum(r["spend"] or 0 for r in evidence)
        item["ad_sales"]=sum(r["ad_sales"] or 0 for r in evidence)
        item["acos"]=item["spend"]/item["ad_sales"] if item["ad_sales"] else None
        best=next((r for r in evidence if (r["orders"] or 0)>0),evidence[0] if evidence else None)
        item["campaign_name"]=best["campaign_name"] if best else None
        item["target"]=best["target"] if best else None
        item["match_type"]=best["match_type"] if best else None
        target_total=target_lookup.get((item["campaign_name"],item["target"],item["match_type"]),{}) if best else {}
        item["primary_clicks"]=target_total.get("clicks",0)
        item["primary_orders"]=target_total.get("orders",0)
        item["primary_spend"]=target_total.get("spend",0)
        item["primary_ad_sales"]=target_total.get("ad_sales",0)
        item["primary_acos"]=target_total.get("acos")
        item["query_orders"]=best["orders"] if best else 0
        item["query_spend"]=best["spend"] if best else 0
        item["query_acos"]=best["acos"] if best else None
        item["campaign_paths"]=len(evidence)
        phrase=item["phrase"].strip().lower()
        target=(item["target"] or "").strip().lower()
        discovered=bool(best and phrase!=target)
        query_efficient=(item["query_orders"]>=2 and item["query_acos"] is not None
                         and item["query_acos"]<=.50)
        campaign=item["campaign_name"] or "the converting campaign"
        target_label=item["target"] or item["phrase"]
        match=(item["match_type"] or "target").upper()
        if discovered and query_efficient:
            item["action"]="Harvest into EXACT"
            item["instruction"]=(f"Add ‘{item['phrase']}’ as EXACT in {campaign}; keep the source "
                                 f"‘{target_label}’ {match} active and review organic rank after 7 days.")
            item["priority"]=11000+item["search_volume"]+item["query_orders"]*100
        elif discovered:
            item["action"]="Do not harvest"
            item["instruction"]=(f"Do not add ‘{item['phrase']}’ as EXACT yet. Its matching query has not "
                                 f"proven efficient conversion; manage ‘{target_label}’ {match} separately in the targeting table.")
            item["priority"]=2500+item["search_volume"]
        elif item["primary_acos"] is not None and item["primary_acos"]>.75:
            cut=20 if item["rank"]>20 else 15
            item["action"]=f"Reduce target bid {cut}%"
            item["instruction"]=(f"In {campaign}, reduce ‘{target_label}’ {match} by {cut}%; keep it active "
                                 "and review total sales plus organic rank after 7 days.")
            item["priority"]=9500+item["search_volume"]
        elif item["primary_acos"] is not None and item["primary_acos"]>.55:
            item["action"]="Reduce target bid 10%"
            item["instruction"]=(f"In {campaign}, reduce ‘{target_label}’ {match} by 10%; keep it active "
                                 "and review total sales plus organic rank after 7 days.")
            item["priority"]=9000+item["search_volume"]
        elif not best or item["primary_orders"]==0:
            item["action"]="Do not fund yet"
            item["instruction"]="No converting matching query appears in the selected period; make no new bid until paid conversion is proven."
            item["priority"]=2000+item["search_volume"]
        elif item["rank"]<=30 and item["query_orders"]>=2:
            item["action"]="Controlled EXACT test"
            item["instruction"]=(f"Isolate ‘{item['phrase']}’ as EXACT in {campaign}; hold the source bid and "
                                 "review contribution and organic rank after 7 days.")
            item["priority"]=7000+item["search_volume"]
        else:
            item["action"]="Hold current target"
            item["instruction"]=(f"Leave ‘{target_label}’ {match} unchanged in {campaign}; the selected period "
                                 "does not support a bid change or a new EXACT target.")
            item["priority"]=3000+item["search_volume"]
        output.append(item)
    return sorted(output,key=lambda r:r["priority"],reverse=True)


def executive_actions(period_start, period_end, brand, ranked_actions):
    if not ranked_actions:
        return {"headline":"No material intervention is supported","steps":[],"evidence":""}
    top=ranked_actions[0]
    if brand == "Has10":
        metrics=overview(period_start,period_end,brand)
        products=product_diagnostics(period_start,period_end,brand)
        ppc=ppc_decisions(period_start,period_end,brand)
        from datetime import date
        days=(date.fromisoformat(period_end)-date.fromisoformat(period_start)).days+1

        def ppc_row(campaign, query):
            return next((r for r in ppc if r["campaign_name"] == campaign and
                         (r["search_term"] or "").lower() == query.lower()), None)

        def pct(value):
            return f"{value:.0%}" if value is not None else "—"

        blue_generic=ppc_row("Has10 | Blue | Historic Keywords", "cleat covers")
        orange_generic=ppc_row("Cleat_Covers_Orange", "cleat covers")
        orange_exact=ppc_row("Cleat_Covers_Orange", "orange cleat covers")
        black_generic=ppc_row("Cleat_Covers_Black", "cleat covers")
        black_football=ppc_row("Cleat_Covers_Black", "football cleat covers")

        stocked=[]
        for row in products:
            if row["units"] > 0 and row["inventory"] > 0:
                stocked.append({**row,"cover_days":row["inventory"]/(row["units"]/days)})
        stocked.sort(key=lambda r:r["cover_days"])
        urgent=[r for r in stocked if r["cover_days"] < 28][:3]
        steps=[]
        cost=cost_diagnosis(period_start,period_end,brand)
        avg_net_price=cost["net_sales"]/cost["net_units"] if cost["net_units"] else 0
        ad_allowance=max(cost["pre_ad_contribution"]/cost["net_units"]-avg_net_price*.05,0) if cost["net_units"] else 0
        steps.append({"action":f"Bring TaCoS below {cost['break_even_tacos']:.0%}; at current sales, that means removing at least ${cost['ad_reduction_to_break_even']:,.0f} of unproductive MTD-equivalent spend.",
                      "why":f"Has10 earns ${cost['pre_ad_contribution']:,.0f} before advertising, but ads consumed ${cost['ads']:,.0f}. This is the minimum modeled improvement to reach break-even; protect total sales while making the campaign changes below."})
        if urgent:
            labels=", ".join(f"{r['color']} {r['size']} ({r['cover_days']:.0f} days FBA cover)" for r in urgent)
            replenish_step={"action":f"Protect availability for {labels}.",
                            "why":"These are the shortest-cover selling variations at the current August pace. Confirm AWD/inbound quantities before choosing the transfer quantity; this view currently measures available FBA stock."}
        if orange_generic and orange_exact:
            exact_bid=ad_allowance*min(orange_exact["orders"]/orange_exact["clicks"],1) if orange_exact["clicks"] else 0
            steps.append({"action":f"Add ‘orange cleat covers’ as EXACT with a modeled CPC ceiling near ${exact_bid:.2f}; reduce Orange campaign ‘cleat covers’ BROAD by 30%.",
                          "why":f"The color-specific query produced {orange_exact['orders']:.0f} orders at {pct(orange_exact['acos'])} ACoS, while the generic broad path spent ${orange_generic['spend']:.2f} at {pct(orange_generic['acos'])} ACoS."})
        if black_generic and black_football:
            exact_bid=ad_allowance*min(black_football["orders"]/black_football["clicks"],1) if black_football["clicks"] else 0
            steps.append({"action":f"Add ‘football cleat covers’ as EXACT in Black with a modeled CPC ceiling near ${exact_bid:.2f}; reduce Black ‘cleat covers’ PHRASE by 30%.",
                          "why":f"‘Football cleat covers’ produced {black_football['orders']:.0f} orders at {pct(black_football['acos'])} ACoS. The generic query spent ${black_generic['spend']:.2f} at {pct(black_generic['acos'])} ACoS."})
        if blue_generic:
            steps.append({"action":"Reduce Blue ‘cleat covers’ PHRASE by 20%; preserve its youth queries.",
                          "why":f"The generic query is at {pct(blue_generic['acos'])} ACoS, but ‘youth cleat covers’ and ‘cleat covers youth’ are converting. Use a small cut to avoid suppressing qualified seasonal demand."})
        steps.append({"action":"Keep the $13.99 base price; do not answer the current profit pressure with a broad price cut.",
                      "why":"Has10 is already below the $15.49 direct-competitor median. Current contribution is being pressured by advertising allocation, while total August demand is accelerating versus the preceding period."})
        if urgent:
            steps.append(replenish_step)
        productive=[r for r in ppc if r["orders"]>=2 and r["acos"] is not None and r["acos"]<=.50][:5]
        contribution=metrics["contribution_after_cogs"]
        contribution_text=f"-${abs(contribution):,.0f}" if contribution < 0 else f"${contribution:,.0f}"
        return {"headline":"Protect the seasonal sales surge, but move spend from generic traffic into proven color and football queries.",
                "steps":steps,"productive_terms":productive,
                "evidence":f"August ordered sales are ${metrics['ordered_sales']:,.0f}; TaCoS is {metrics['tacos']:.1%} and estimated contribution after COGS is {contribution_text} ({metrics['contribution_margin']:.1%})."}
    if brand != "Litet":
        impact=top.get("estimated_30d_impact") or top.get("severity") or 0
        return {"headline":f"Prioritize {top['color'] or ''} {top['size'] or ''}",
                "steps":[{"action":top["next_step"],"why":top["reason"]}],
                "evidence":f"Approximately ${impact:,.0f} of measured exposure is attached to this alert."}
    trend=monthly_trend(brand)
    current=trend[-1]
    current_start,current_end=current["period_start"],current["period_end"]
    from datetime import date, timedelta
    current_start_date=date.fromisoformat(current_start)
    current_end_date=date.fromisoformat(current_end)
    prior_end=(current_start_date-timedelta(days=1)).replace(day=current_end_date.day)
    prior_start=prior_end.replace(day=1)
    ppc=ppc_decisions(current_start,current_end,brand)
    productive=[r for r in ppc if r["orders"]>=1 and r["acos"] is not None and r["acos"]<=.35]
    inefficient=[r for r in ppc if r["clicks"]>=8 and r["acos"] is not None and r["acos"]>1]
    inefficient.sort(key=lambda r:r["spend"],reverse=True)
    with connect() as conn:
        prior_sales=conn.execute("""SELECT COALESCE(SUM(CAST(o."item-price" AS REAL)-COALESCE(CAST(o."item-promotion-discount" AS REAL),0)),0)
          FROM orders o JOIN dim_product p ON p.asin=o.asin
          WHERE date(substr(o."purchase-date",1,10)) BETWEEN ? AND ? AND p.canonical_brand=?
            AND COALESCE(o."order-status",'') NOT IN ('Cancelled','Canceled')
            AND COALESCE(o."item-status",'') NOT IN ('Cancelled','Canceled')""",
          (prior_start.isoformat(),prior_end.isoformat(),brand)).fetchone()[0]
        campaigns=conn.execute("""SELECT campaign_name,SUM(spend) spend,SUM(ad_sales) ad_sales,SUM(ad_orders) orders
          FROM ppc_fact_clean WHERE brand=? AND report_date BETWEEN ? AND ?
          GROUP BY campaign_name ORDER BY spend DESC""",(brand,current_start,current_end)).fetchall()
        inventory=conn.execute("""WITH latest AS (SELECT MAX(snapshot_date) d FROM inventory_snapshots),
          inv AS (SELECT i.asin,SUM(CAST(i."Quantity Available" AS REAL)) qty FROM inventory_snapshots i,latest WHERE i.snapshot_date=latest.d GROUP BY i.asin),
          sales AS (SELECT o.asin,SUM(CAST(o.quantity AS REAL)) units FROM orders o WHERE date(substr(o."purchase-date",1,10)) BETWEEN date(?,'-29 days') AND ? AND COALESCE(o."order-status",'') NOT IN ('Cancelled','Canceled') GROUP BY o.asin)
          SELECT p.color,p.size,p.pack_type,inv.qty,30.0*sales.units/30.0 velocity,CASE WHEN sales.units>0 THEN inv.qty/(sales.units/30.0) END cover
          FROM inv JOIN dim_product p ON p.asin=inv.asin JOIN sales ON sales.asin=inv.asin
          WHERE p.canonical_brand=? ORDER BY cover LIMIT 1""",(current_end,current_end,brand)).fetchone()
    tacos=current["tacos"]
    ad_sales=sum(r["ad_sales"] or 0 for r in campaigns)
    total_acos=current["ad_spend"]/ad_sales if ad_sales else None
    bad=inefficient[0] if inefficient else None
    good=min(productive,key=lambda r:r["acos"]) if productive else None
    ppc_detail=(f" ‘{bad['search_term']}’ used ${bad['spend']:.2f} across {bad['clicks']:.0f} clicks at {bad['acos']:.0%} ACoS; reduce that path, while protecting ‘{good['search_term']}’ at {good['acos']:.0%} ACoS."
                if bad and good else " Review the highest-spend search terms before changing broad campaign budgets.")
    change=current["ordered_sales"]/prior_sales-1 if prior_sales else None
    avg_current=current["ordered_sales"]/((current_end_date-current_start_date).days+1)
    prior_full=trend[-2]
    avg_prior=prior_full["ordered_sales"]/date.fromisoformat(prior_full["period_end"]).day
    steps=[
      {"action":"ACT NOW — Stop PPC budget increases and isolate inefficient traffic.",
       "why":f"Current MTD sales are ${current['ordered_sales']:,.0f} against ${current['ad_spend']:,.0f} of ad spend: {tacos:.0%} TaCoS and {total_acos:.0%} aggregate ACoS.{ppc_detail}",
       "proposal":({"campaign_name":bad["campaign_name"],"entity_type":"target",
                    "entity_name":bad["target"],"action_type":"reduce_bid_15pct",
                    "old_value":bad["cpc"],"new_value":bad["cpc"]*.85,
                    "spend":bad["spend"],"clicks":bad["clicks"],
                    "orders":bad["orders"],"acos":bad["acos"],
                    "period_start":current_start,"period_end":current_end,
                    "objective":"Reduce inefficient target-level spend while protecting total sales."}
                   if bad and bad.get("cpc") else None)},
      {"action":"WATCH — Do not change price from four days of demand.",
       "why":f"Sales are {change:+.0%} versus the same days last month, but the ${avg_current:,.0f} current daily pace is {avg_current/avg_prior-1:+.0%} versus last month's full-period average. Reassess after 7 complete days."},
    ]
    if inventory:
        steps.append({"action":f"ACT NOW — Confirm replenishment for {inventory['color']} {inventory['size']} {inventory['pack_type']}.",
                      "why":f"Only {inventory['qty']:.0f} FBA units remain, approximately {inventory['cover']:.0f} days of cover at the trailing 30-day rate. Confirm AWD and inbound inventory before setting a transfer quantity."})
    return {"headline":f"Current account view through {current_end}: control PPC efficiency while protecting demand.",
            "steps":steps,"productive_terms":productive,
            "evidence":f"Uses daily orders and PPC through {current_end}; settlement economics and traffic are withheld where the current report crosses months."}


def executive_diagnosis(period_start, period_end, brand, ceo_action):
    """Connect performance, objective, causes, actions and safeguards."""
    from datetime import date
    import calendar
    metrics=overview(period_start,period_end,brand)
    trend=monthly_trend(brand)
    # LITET's executive priorities are an operating-now view. Keep their pace,
    # confidence and comparison anchored to the latest common daily cutoff even
    # when the selected period below is the latest settled P&L month.
    current=(trend[-1] if brand == "Litet" and trend else
             next((r for r in reversed(trend) if r["period_start"][:7]==period_start[:7]),None))
    prior=next((r for r in reversed(trend) if not r["is_partial"] and (not current or r["period_start"]<current["period_start"])),None)
    current_end=date.fromisoformat(current["period_end"]) if current else date.fromisoformat(period_end)
    current_start=date.fromisoformat(current["period_start"]) if current else date.fromisoformat(period_start)
    observed_days=(current_end-current_start).days+1
    month_days=calendar.monthrange(current_end.year,current_end.month)[1]
    factor=month_days/observed_days if current and current["is_partial"] else 1
    def change(key,pace=False):
        if not current or not prior or not prior.get(key): return None
        value=(current.get(key) or 0)*(factor if pace else 1)
        return value/prior[key]-1
    sales_change=change("ordered_sales",True); traffic_change=change("sessions",True)
    conversion_change=change("conversion")
    floor=.10 if brand=="Litet" else .05
    mode="Growth and adoption" if brand=="Litet" else "Seasonal scale and availability"
    causes=[]
    for label,value in (("Traffic",traffic_change),("Conversion",conversion_change),("Sales pace",sales_change)):
        if value is not None: causes.append({"label":label,"change":value})
    margin=metrics.get("contribution_margin")
    status=("Capacity to invest" if margin is not None and margin>=floor else "Below growth constraint")
    if brand=="Has10" and margin is not None and margin<floor: status="Seasonal scale is not covering the contribution floor"
    protections=[{"title":"Avoid broad traffic cuts","reason":"Evaluate total sales, sessions, conversion and organic rank before reducing strategic category coverage."}]
    if ceo_action.get("productive_terms"):
        protections.append({"title":"Preserve proven demand","reason":f"{len(ceo_action['productive_terms'])} productive search terms have conversion evidence in the current operating period through {current['period_end'] if current else period_end}."})
    priority_actions={p["action"] for p in ceo_action.get("steps",[])[:3]}
    for step in ceo_action.get("steps",[]):
        if (step["action"] not in priority_actions and
                step["action"].startswith(("Keep ","Hold ","Do not "))):
            protections.append({"title":step["action"],"reason":step["why"]})
    return {"brand":brand,"mode":mode,"floor":floor,"status":status,
            "sales_pace_change":sales_change,"traffic_pace_change":traffic_change,
            "conversion_change":conversion_change,"causes":causes,
            "prior_label":prior["period_start"][:7] if prior else None,
            "operating_start":current["period_start"] if current else period_start,
            "operating_end":current["period_end"] if current else period_end,
            "pnl_start":period_start,"pnl_end":period_end,
            "confidence":"Medium" if current and current["is_partial"] else "High",
            "priorities":ceo_action.get("steps",[])[:3],"protections":protections,
            "review_window":"Review interventions after 7 complete days; confirm at 14 days."}


def pricing_case(period_start, period_end, brand, asin=None):
    products=product_diagnostics(period_start,period_end,brand)
    product=next((p for p in products if p["asin"]==asin),None) if asin else None
    if product is None:
        candidates=[p for p in products if p["units"]>0 and p["net_sales"]>0]
        product=min(candidates,key=lambda p:p["conversion"] if p["conversion"] is not None else 999) if candidates else None
    if not product: return None
    with connect() as conn:
        econ=conn.execute("""SELECT asin,MIN(period_start) period_start,MAX(period_end) period_end,
          CASE WHEN COUNT(*)=1 THEN MAX(period_type) ELSE 'range' END period_type,
          CASE WHEN SUM(units_sold)>0 THEN SUM(net_sales)/SUM(units_sold) END average_sales_price,
          SUM(units_sold) units_sold,SUM(units_returned) units_returned,SUM(net_units_sold) net_units_sold,
          SUM(net_sales) net_sales,SUM(net_proceeds) net_proceeds,SUM(referral_fee) referral_fee,
          SUM(referral_fee_refunds) referral_fee_refunds,
          COALESCE((SELECT unit_cogs FROM cogs_ledger c WHERE c.asin=? AND c.effective_start<=? AND (c.effective_end IS NULL OR c.effective_end>=?) ORDER BY c.effective_start DESC LIMIT 1),0) unit_cogs
          FROM asin_economics WHERE asin=? AND period_start>=? AND period_end<=? GROUP BY asin""",
          (product["asin"],period_end,period_start,product["asin"],period_start,period_end)).fetchone()
        history=conn.execute("""SELECT substr("purchase-date",1,7) month,SUM(CAST(quantity AS REAL)) units,
          SUM(CAST("item-price" AS REAL)-COALESCE(CAST("item-promotion-discount" AS REAL),0)) sales
          FROM orders WHERE asin=? AND "order-status" NOT IN ('Cancelled','Pending') GROUP BY 1 HAVING SUM(CAST(quantity AS REAL))>0 ORDER BY 1""",(product["asin"],)).fetchall()
        settled_history=conn.execute("""SELECT period_start,period_end,average_sales_price,units_sold,units_returned,
          net_units_sold,net_sales,net_proceeds FROM asin_economics
          WHERE asin=? AND period_type='monthly' AND period_end<? ORDER BY period_end DESC LIMIT 6""",
          (product["asin"],period_start)).fetchall()
        monthly_evidence=conn.execute("""SELECT e.period_start,e.period_end,e.average_sales_price,e.units_sold,e.units_returned,
          e.net_units_sold,e.net_sales,e.net_proceeds,MAX(t.sessions_total) sessions,SUM(t.units_ordered) ordered_units
          FROM asin_economics e LEFT JOIN business_traffic t ON t.child_asin=e.asin
            AND t.period_start=e.period_start AND t.period_end=e.period_end
          WHERE e.asin=? AND e.period_type='monthly' AND e.period_end<?
          GROUP BY e.period_start,e.period_end ORDER BY e.period_end DESC LIMIT 8""",
          (product["asin"],period_start)).fetchall()
        cogs_record=conn.execute("""SELECT unit_cogs,source FROM cogs_ledger WHERE asin=?
          AND effective_start<=? AND (effective_end IS NULL OR effective_end>=?)
          ORDER BY effective_start DESC LIMIT 1""",(product["asin"],period_end,period_start)).fetchone()
    econ=dict(econ) if econ else {}; units=product["units"] or econ.get("units_sold") or 0
    current_price=product["ordered_sales"]/units if units else None; net_units=max(econ.get("net_units_sold") or units or 1,1); cogs=econ.get("unit_cogs") or 0
    current_contribution=(econ.get("net_proceeds") or product["net_proceeds"] or 0)-cogs*net_units; cpu=current_contribution/net_units
    referral=abs((econ.get("referral_fee") or 0)+(econ.get("referral_fee_refunds") or 0)); referral_rate=min(referral/(econ.get("net_sales") or product["net_sales"] or 1),.30)
    scenarios=[]
    if current_price:
        for drop in (0,1,2):
            new_cpu=cpu-drop*(1-referral_rate); needed=current_contribution/new_cpu if new_cpu>0 else None
            scenarios.append({"price":current_price-drop,"contribution_per_unit":new_cpu,"units_needed":needed,"lift_needed":needed/net_units-1 if needed else None})
    price_history=[{"month":r["month"],"units":r["units"],"price":r["sales"]/r["units"] if r["units"] else None} for r in history]
    price_levels={round(r["price"],2) for r in price_history if r["price"]}
    sold_units=econ.get("units_sold") or 0; returned=econ.get("units_returned") or 0
    return_rate=returned/sold_units if sold_units else None
    rolling={"sold_units":sum(r["units_sold"] or 0 for r in settled_history),
             "returned_units":sum(r["units_returned"] or 0 for r in settled_history),
             "net_units":sum(r["net_units_sold"] or 0 for r in settled_history),
             "net_sales":sum(r["net_sales"] or 0 for r in settled_history),
             "net_proceeds":sum(r["net_proceeds"] or 0 for r in settled_history)}
    rolling["return_rate"]=rolling["returned_units"]/rolling["sold_units"] if rolling["sold_units"] else None
    rolling["contribution"]=rolling["net_proceeds"]-rolling["net_units"]*cogs
    rolling["contribution_per_unit"]=rolling["contribution"]/rolling["net_units"] if rolling["net_units"] else None
    monthly=[]
    for r in reversed(monthly_evidence):
        d=dict(r); d["conversion"]=d["ordered_units"]/d["sessions"] if d["sessions"] else None
        d["period_label"]=d["period_start"][:7]; d["is_partial"]=False; monthly.append(d)
    if econ:
        selected_label=(f"{period_start[:7]} MTD" if econ.get("period_type")=="custom" else
                        f"{period_start} to {period_end}" if econ.get("period_type")=="range" else period_start[:7])
        current_month={"period_start":period_start,"period_end":period_end,
                       "period_label":selected_label,
                       "is_partial":econ.get("period_type") in {"custom","range"},
                       "average_sales_price":econ.get("average_sales_price"),
                       "sessions":product["sessions"],"ordered_units":product["units"],
                       "conversion":product["conversion"],"units_sold":sold_units,
                       "units_returned":returned,"net_units_sold":net_units,
                       "net_sales":econ.get("net_sales") or 0,"net_proceeds":econ.get("net_proceeds") or 0}
        monthly.append(current_month)
    bands={}
    for row in monthly:
        if row["is_partial"] or row["average_sales_price"] is None:
            continue
        level=round(row["average_sales_price"])
        band=bands.setdefault(level,{"price":level,"sessions":0,"ordered_units":0,"months":0})
        band["sessions"]+=row["sessions"] or 0; band["ordered_units"]+=row["ordered_units"] or 0; band["months"]+=1
    price_bands=[]
    for band in sorted(bands.values(),key=lambda b:b["price"]):
        band["conversion"]=band["ordered_units"]/band["sessions"] if band["sessions"] else None
        price_bands.append(band)
    historical_decision_ready=rolling["net_units"]>=30 and len(price_bands)>=2
    if historical_decision_ready and current_price:
        baseline_units=rolling["net_units"]
        baseline_cpu=rolling["contribution_per_unit"]
        baseline_contribution=rolling["contribution"]
        scenarios=[]
        for drop in (0,1,2):
            new_cpu=baseline_cpu-drop*(1-referral_rate); needed=baseline_contribution/new_cpu if new_cpu>0 else None
            scenarios.append({"price":current_price-drop,"contribution_per_unit":new_cpu,
                              "units_needed":needed,"lift_needed":needed/baseline_units-1 if needed else None})
    data_quality=[]
    if net_units<10: data_quality.append(f"Only {net_units:.0f} net settled units: unit economics are too sensitive for a confident price decision.")
    if return_rate is not None and return_rate>.15: data_quality.append(f"Return rate is {return_rate:.0%}; returns, not price, dominate current contribution.")
    if len(price_levels)<3: data_quality.append("Historical price variation is insufficient to estimate elasticity reliably.")
    candidate=scenarios[1] if len(scenarios)>1 else None
    if historical_decision_ready:
        verdict="Hold current price; historical evidence does not isolate price as the conversion cause"
    elif data_quality: verdict="Do not change price from this evidence alone"
    elif candidate and candidate.get("lift_needed") is not None and candidate["lift_needed"]>.35: verdict="Price drop is unlikely to preserve contribution"
    else: verdict="Controlled price test is financially plausible"
    market=market_context(brand); benchmark=None
    if market and product["pack_type"]=="single": benchmark={"name":"direct/value median","checkout":market["direct_price_median"],"per_unit":market["direct_price_median"]}
    elif market and brand=="Litet" and product["pack_type"]=="3-pack": benchmark={"name":"Thirty48 3-pair","checkout":24.95,"per_unit":8.32}
    price_gap=(current_price-benchmark["checkout"])/benchmark["checkout"] if current_price and benchmark and benchmark["checkout"] else None
    if historical_decision_ready:
        band_text="; ".join(f"${b['price']:.0f} months converted at {b['conversion']:.1%}" for b in price_bands)
        next_step=f"Hold ${current_price:.2f}. Completed-month evidence does not support a discount: {band_text}. Monitor MTD returns until settlement catches up."
    else:
        next_step="Do not launch this price test yet. Use a longer settled economics window or select a higher-volume SKU."
    return {"product":product,"current_price":current_price,"current_units":net_units,"ordered_units":units,
            "sold_units":sold_units,"returned_units":returned,"return_rate":return_rate,
            "current_contribution":current_contribution,"referral_rate":referral_rate,"scenarios":scenarios,
            "market":market,"price_benchmark":benchmark,"price_gap":price_gap,"price_history":price_history[-12:],"price_levels":len(price_levels),
            "data_quality":data_quality,"verdict":verdict,"rolling":rolling,"monthly_evidence":monthly,
            "price_bands":price_bands,"historical_decision_ready":historical_decision_ready,"next_step":next_step,
            "cogs_source":cogs_record["source"] if cogs_record else None,
            "cogs_is_placeholder":bool(cogs_record and "placeholder" in (cogs_record["source"] or "").lower())}
