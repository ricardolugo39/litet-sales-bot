CREATE TABLE IF NOT EXISTS ppc_bid_change (
    bid_change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL CHECK (brand IN ('Litet', 'Has10')),
    campaign_name TEXT,
    ad_group_name TEXT,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('target', 'search_term')),
    target_value TEXT NOT NULL,
    change_date TEXT NOT NULL,
    suggested_bid REAL,
    actual_bid REAL NOT NULL CHECK (actual_bid >= 0),
    amazon_suggested_low REAL,
    amazon_suggested_high REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        amazon_suggested_low IS NULL
        OR amazon_suggested_high IS NULL
        OR amazon_suggested_low <= amazon_suggested_high
    )
);

CREATE INDEX IF NOT EXISTS idx_ppc_bid_change_scope_date
ON ppc_bid_change (brand, target_kind, target_value, change_date);
