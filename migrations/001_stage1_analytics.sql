PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_product (
    product_key TEXT PRIMARY KEY,
    asin TEXT NOT NULL UNIQUE,
    canonical_brand TEXT NOT NULL CHECK (canonical_brand IN ('Litet', 'Has10', 'Unassigned')),
    product_family TEXT NOT NULL,
    canonical_product_name TEXT NOT NULL,
    size TEXT,
    color TEXT,
    pack_type TEXT NOT NULL,
    units_per_sellable_unit INTEGER NOT NULL CHECK (units_per_sellable_unit > 0),
    first_observed_date TEXT,
    last_observed_date TEXT,
    active_status TEXT NOT NULL,
    effective_start TEXT,
    effective_end TEXT,
    is_current INTEGER NOT NULL CHECK (is_current IN (0, 1)),
    assignment_method TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bridge_product_sku (
    product_sku_key TEXT PRIMARY KEY,
    product_key TEXT NOT NULL REFERENCES dim_product(product_key),
    asin TEXT NOT NULL,
    sku TEXT NOT NULL,
    canonical_brand TEXT NOT NULL,
    effective_start TEXT,
    effective_end TEXT,
    is_current INTEGER NOT NULL CHECK (is_current IN (0, 1)),
    observed_rows INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS product_title_alias (
    title_alias_key TEXT PRIMARY KEY,
    product_key TEXT NOT NULL REFERENCES dim_product(product_key),
    asin TEXT NOT NULL,
    title_alias TEXT NOT NULL,
    canonical_brand TEXT NOT NULL,
    alias_brand_text TEXT NOT NULL,
    first_observed_date TEXT,
    last_observed_date TEXT,
    observed_rows INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign_brand_map (
    campaign_brand_key TEXT PRIMARY KEY,
    campaign_name TEXT NOT NULL UNIQUE,
    brand TEXT NOT NULL CHECK (brand IN ('Litet', 'Has10')),
    mapping_rule TEXT NOT NULL,
    is_current INTEGER NOT NULL CHECK (is_current IN (0, 1))
);

CREATE TABLE IF NOT EXISTS transaction_mart (
    transaction_mart_key TEXT PRIMARY KEY,
    economic_event_key TEXT NOT NULL,
    transaction_date TEXT,
    transaction_status TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    order_id TEXT,
    product_details TEXT,
    brand TEXT NOT NULL,
    order_matched INTEGER NOT NULL,
    is_released INTEGER NOT NULL,
    is_deferred INTEGER NOT NULL,
    product_charges REAL NOT NULL,
    promotional_rebates REAL NOT NULL,
    amazon_fees REAL NOT NULL,
    other_amount REAL NOT NULL,
    transaction_total REAL NOT NULL,
    source_file TEXT,
    imported_at TEXT,
    transaction_uid TEXT
);

CREATE TABLE IF NOT EXISTS fee_ledger (
    fee_ledger_key TEXT PRIMARY KEY,
    transaction_mart_key TEXT NOT NULL REFERENCES transaction_mart(transaction_mart_key),
    transaction_date TEXT,
    order_id TEXT,
    brand TEXT NOT NULL,
    transaction_status TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    product_details TEXT,
    fee_category TEXT NOT NULL,
    fee_subcategory TEXT NOT NULL,
    source_component TEXT NOT NULL,
    fee_amount REAL NOT NULL,
    is_exact INTEGER NOT NULL,
    allocation_method TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fee_reconciliation (
    brand TEXT PRIMARY KEY,
    resolved_transaction_rows INTEGER NOT NULL,
    matched_rows INTEGER NOT NULL,
    matched_row_coverage REAL NOT NULL,
    matched_dollar_coverage REAL NOT NULL,
    released_balance REAL NOT NULL,
    deferred_balance REAL NOT NULL,
    amazon_fees REAL NOT NULL,
    classified_fee_total REAL NOT NULL,
    unexplained_fee_variance REAL NOT NULL,
    transaction_identity_variance REAL NOT NULL,
    unassigned_fee_rows INTEGER NOT NULL,
    raw_transaction_rows INTEGER NOT NULL,
    raw_released_balance REAL NOT NULL,
    raw_deferred_balance REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dim_product_brand ON dim_product(canonical_brand);
CREATE INDEX IF NOT EXISTS idx_bridge_product_sku_asin_sku ON bridge_product_sku(asin, sku);
CREATE INDEX IF NOT EXISTS idx_transaction_mart_brand_date ON transaction_mart(brand, transaction_date);
CREATE INDEX IF NOT EXISTS idx_transaction_mart_order ON transaction_mart(order_id);
CREATE INDEX IF NOT EXISTS idx_fee_ledger_brand_date ON fee_ledger(brand, transaction_date);
