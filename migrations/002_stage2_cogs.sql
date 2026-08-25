PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cogs_ledger (
    cogs_ledger_key TEXT PRIMARY KEY,
    asin TEXT NOT NULL,
    unit_cogs REAL NOT NULL CHECK (unit_cogs >= 0),
    effective_start TEXT NOT NULL,
    effective_end TEXT,
    is_current INTEGER NOT NULL CHECK (is_current IN (0, 1)),
    source TEXT NOT NULL,
    source_reference TEXT,
    prior_on_hand_qty REAL,
    receipt_quantity REAL,
    receipt_unit_cost REAL,
    inventory_snapshot_date TEXT,
    inventory_qty_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cogs_one_current_per_asin
ON cogs_ledger(asin) WHERE is_current = 1;

CREATE INDEX IF NOT EXISTS idx_cogs_asin_dates
ON cogs_ledger(asin, effective_start, effective_end);

CREATE TABLE IF NOT EXISTS vendor_receipts (
    receipt_id TEXT PRIMARY KEY,
    asin TEXT NOT NULL,
    received_date TEXT NOT NULL,
    quantity_received REAL NOT NULL CHECK (quantity_received > 0),
    total_cost_paid REAL,
    unit_cost REAL,
    source TEXT NOT NULL DEFAULT 'manual_entry',
    notes TEXT,
    entered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT,
    resulting_ledger_key TEXT,
    inventory_snapshot_date TEXT,
    on_hand_qty_used REAL,
    inventory_qty_status TEXT,
    CHECK (
        (unit_cost IS NOT NULL AND unit_cost >= 0)
        OR (total_cost_paid IS NOT NULL AND total_cost_paid >= 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_vendor_receipts_asin_date
ON vendor_receipts(asin, received_date);

CREATE TABLE IF NOT EXISTS sales_profitability (
    sale_line_key TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    sale_date TEXT,
    asin TEXT NOT NULL,
    sku TEXT,
    brand TEXT NOT NULL,
    product_name TEXT,
    quantity REAL NOT NULL,
    item_price_revenue REAL NOT NULL,
    unit_cogs REAL,
    cogs_amount REAL,
    cogs_status TEXT NOT NULL,
    cogs_ledger_key TEXT,
    amazon_fees REAL,
    fee_status TEXT NOT NULL,
    contribution_profit_before_ads REAL,
    contribution_margin_before_ads REAL
);

CREATE INDEX IF NOT EXISTS idx_sales_profitability_brand_date
ON sales_profitability(brand, sale_date);
