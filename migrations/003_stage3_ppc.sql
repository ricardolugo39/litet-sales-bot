PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ppc_fact_clean (
    ppc_fact_key TEXT PRIMARY KEY,
    report_date TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    target TEXT NOT NULL,
    match_type TEXT NOT NULL,
    search_term TEXT NOT NULL,
    brand TEXT NOT NULL CHECK (brand IN ('Litet', 'Has10')),
    impressions REAL NOT NULL,
    clicks REAL NOT NULL,
    spend REAL NOT NULL,
    ad_sales REAL NOT NULL,
    ad_orders REAL NOT NULL,
    ad_units REAL NOT NULL,
    advertised_sku_units REAL NOT NULL,
    other_sku_units REAL NOT NULL,
    advertised_sku_sales REAL NOT NULL,
    other_sku_sales REAL NOT NULL,
    ctr REAL,
    cpc REAL,
    cvr REAL,
    acos REAL,
    roas REAL,
    dedup_group_size INTEGER NOT NULL,
    dedup_rule TEXT NOT NULL,
    selected_source_id TEXT,
    selected_source_id1 TEXT,
    source_file TEXT,
    imported_at TEXT,
    original_ppc_uid TEXT
);

CREATE INDEX IF NOT EXISTS idx_ppc_fact_brand_date
ON ppc_fact_clean(brand, report_date);
CREATE INDEX IF NOT EXISTS idx_ppc_fact_campaign
ON ppc_fact_clean(campaign_name, report_date);
CREATE INDEX IF NOT EXISTS idx_ppc_fact_search_term
ON ppc_fact_clean(search_term, report_date);

CREATE TABLE IF NOT EXISTS ppc_campaign_metrics (
    scope TEXT NOT NULL,
    brand TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    impressions REAL NOT NULL,
    clicks REAL NOT NULL,
    spend REAL NOT NULL,
    ad_sales REAL NOT NULL,
    ad_orders REAL NOT NULL,
    ctr REAL,
    cpc REAL,
    cvr REAL,
    acos REAL,
    roas REAL,
    tacos REAL,
    PRIMARY KEY (scope, brand, campaign_name)
);

CREATE TABLE IF NOT EXISTS ppc_ad_group_metrics (
    scope TEXT NOT NULL,
    brand TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    impressions REAL NOT NULL,
    clicks REAL NOT NULL,
    spend REAL NOT NULL,
    ad_sales REAL NOT NULL,
    ad_orders REAL NOT NULL,
    ctr REAL,
    cpc REAL,
    cvr REAL,
    acos REAL,
    roas REAL,
    tacos REAL,
    PRIMARY KEY (scope, brand, campaign_name, ad_group_name)
);

CREATE TABLE IF NOT EXISTS ppc_target_metrics (
    scope TEXT NOT NULL,
    brand TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    target TEXT NOT NULL,
    match_type TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    impressions REAL NOT NULL,
    clicks REAL NOT NULL,
    spend REAL NOT NULL,
    ad_sales REAL NOT NULL,
    ad_orders REAL NOT NULL,
    ctr REAL,
    cpc REAL,
    cvr REAL,
    acos REAL,
    roas REAL,
    tacos REAL,
    PRIMARY KEY (scope, brand, campaign_name, ad_group_name, target, match_type)
);

CREATE TABLE IF NOT EXISTS ppc_search_term_metrics (
    scope TEXT NOT NULL,
    brand TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    target TEXT NOT NULL,
    match_type TEXT NOT NULL,
    search_term TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    impressions REAL NOT NULL,
    clicks REAL NOT NULL,
    spend REAL NOT NULL,
    ad_sales REAL NOT NULL,
    ad_orders REAL NOT NULL,
    ctr REAL,
    cpc REAL,
    cvr REAL,
    acos REAL,
    roas REAL,
    tacos REAL,
    PRIMARY KEY (
        scope, brand, campaign_name, ad_group_name,
        target, match_type, search_term
    )
);

CREATE TABLE IF NOT EXISTS contribution_margin_benchmark (
    benchmark_key TEXT PRIMARY KEY,
    brand TEXT NOT NULL,
    product_family TEXT NOT NULL,
    complete_sale_lines INTEGER NOT NULL,
    complete_orders INTEGER NOT NULL,
    revenue REAL NOT NULL,
    contribution_profit_before_ads REAL NOT NULL,
    break_even_acos REAL,
    average_order_revenue REAL,
    coverage_note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ppc_negative_keyword_candidates (
    candidate_key TEXT PRIMARY KEY,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    brand TEXT NOT NULL,
    campaign_name TEXT NOT NULL,
    ad_group_name TEXT NOT NULL,
    target TEXT NOT NULL,
    match_type TEXT NOT NULL,
    search_term TEXT NOT NULL,
    normalized_term TEXT NOT NULL,
    near_duplicate_count INTEGER NOT NULL,
    impressions REAL NOT NULL,
    clicks REAL NOT NULL,
    spend REAL NOT NULL,
    ad_sales REAL NOT NULL,
    ad_orders REAL NOT NULL,
    cvr REAL,
    acos REAL,
    break_even_acos REAL,
    break_even_spend_allowance REAL,
    margin_level TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ppc_profit_after_ads (
    row_key TEXT PRIMARY KEY,
    scope_level TEXT NOT NULL,
    brand TEXT NOT NULL,
    campaign_name TEXT,
    period_start TEXT,
    period_end TEXT,
    profit_before_ads REAL,
    profit_coverage_revenue REAL,
    total_item_price_revenue REAL,
    profit_coverage_pct REAL,
    ad_sales REAL,
    ad_spend REAL NOT NULL,
    break_even_acos REAL,
    estimated_ad_contribution_after_spend REAL,
    profit_after_ads REAL,
    calculation_status TEXT NOT NULL
);
