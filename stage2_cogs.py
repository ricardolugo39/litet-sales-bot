"""Weighted-average COGS ledger, vendor receipt posting, and as-of-sale profit."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from pathlib import Path

import pandas as pd


EXCLUDED_ASINS = {"XXXXXXXXX"}


def apply_stage2_schema(conn: sqlite3.Connection) -> None:
    migration = Path(__file__).with_name("migrations") / "002_stage2_cogs.sql"
    conn.executescript(migration.read_text())


def _seed_key(asin: str, effective_start: str) -> str:
    return hashlib.sha256(f"placeholder_seed\x1f{asin}\x1f{effective_start}".encode()).hexdigest()


def seed_cogs_ledger(
    conn: sqlite3.Connection,
    seed_path: str | Path,
    effective_start: str,
) -> int:
    """Idempotently seed current placeholder COGS rows keyed by ASIN."""
    apply_stage2_schema(conn)
    seed = pd.read_csv(seed_path, dtype={"asin": str, "sku": str})
    seed["asin"] = seed["asin"].fillna("").str.strip()
    seed = seed[seed["asin"].ne("") & ~seed["asin"].isin(EXCLUDED_ASINS)].copy()
    if seed["asin"].duplicated().any():
        duplicates = sorted(seed.loc[seed["asin"].duplicated(keep=False), "asin"].unique())
        raise ValueError(f"Duplicate ASINs in COGS seed: {duplicates}")
    seed["cogs"] = pd.to_numeric(seed["cogs"], errors="raise")

    inserted = 0
    with conn:
        for row in seed.itertuples(index=False):
            key = _seed_key(row.asin, effective_start)
            existing = conn.execute(
                "SELECT 1 FROM cogs_ledger WHERE cogs_ledger_key = ?", (key,)
            ).fetchone()
            if existing:
                continue
            current = conn.execute(
                "SELECT source FROM cogs_ledger WHERE asin = ? AND is_current = 1", (row.asin,)
            ).fetchone()
            if current:
                continue
            conn.execute(
                """
                INSERT INTO cogs_ledger (
                    cogs_ledger_key, asin, unit_cogs, effective_start,
                    effective_end, is_current, source, source_reference,
                    inventory_qty_status
                ) VALUES (?, ?, ?, ?, NULL, 1, 'placeholder_seed', ?, 'seed_not_applicable')
                """,
                (key, row.asin, float(row.cogs), effective_start, str(seed_path)),
            )
            inserted += 1
    return inserted


def backdate_placeholder_seeds(
    conn: sqlite3.Connection,
    effective_start: str,
) -> int:
    """Extend only the initial placeholder rows backward without changing receipts."""
    apply_stage2_schema(conn)
    target = pd.to_datetime(effective_start, errors="raise").date().isoformat()
    with conn:
        cursor = conn.execute(
            """
            UPDATE cogs_ledger
            SET effective_start = ?
            WHERE source = 'placeholder_seed'
              AND date(effective_start) > date(?)
            """,
            (target, target),
        )
    return cursor.rowcount


def latest_inventory_quantity(
    conn: sqlite3.Connection,
    asin: str,
) -> tuple[float, str | None, str]:
    """Return latest snapshot quantity, date, and an explicit reliability status."""
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_snapshots'"
    ).fetchone()
    if not table:
        return 0.0, None, "missing_inventory_table_default_zero"
    snapshot = conn.execute(
        """
        SELECT snapshot_date,
               SUM(CASE
                   WHEN TRIM(COALESCE("Quantity Available", '')) = '' THEN 0
                   ELSE CAST("Quantity Available" AS REAL)
               END)
        FROM inventory_snapshots
        WHERE asin = ?
          AND snapshot_date = (SELECT MAX(snapshot_date) FROM inventory_snapshots)
        GROUP BY snapshot_date
        """,
        (asin,),
    ).fetchone()
    if not snapshot:
        return 0.0, None, "missing_asin_snapshot_default_zero"
    quantity = float(snapshot[1] or 0)
    status = "latest_snapshot" if quantity >= 0 else "invalid_negative_default_zero"
    return (quantity if quantity >= 0 else 0.0), snapshot[0], status


def record_vendor_receipt(
    conn: sqlite3.Connection,
    *,
    asin: str,
    received_date: str,
    quantity_received: float,
    total_cost_paid: float | None = None,
    unit_cost: float | None = None,
    source: str = "manual_entry",
    notes: str = "",
    receipt_id: str | None = None,
) -> dict:
    """Insert and process one receipt atomically, creating a new moving-average row."""
    apply_stage2_schema(conn)
    asin = str(asin).strip()
    if not asin or asin in EXCLUDED_ASINS:
        raise ValueError("A real, non-excluded ASIN is required")
    quantity_received = float(quantity_received)
    if quantity_received <= 0:
        raise ValueError("quantity_received must be greater than zero")
    if unit_cost is None:
        if total_cost_paid is None:
            raise ValueError("Provide unit_cost or total_cost_paid")
        unit_cost = float(total_cost_paid) / quantity_received
    else:
        unit_cost = float(unit_cost)
    if unit_cost < 0:
        raise ValueError("unit cost cannot be negative")
    if total_cost_paid is None:
        total_cost_paid = unit_cost * quantity_received

    current = conn.execute(
        """
        SELECT cogs_ledger_key, unit_cogs, effective_start
        FROM cogs_ledger
        WHERE asin = ? AND is_current = 1
        """,
        (asin,),
    ).fetchone()
    current_avg = float(current[1]) if current else unit_cost
    on_hand, snapshot_date, inventory_status = latest_inventory_quantity(conn, asin)
    denominator = on_hand + quantity_received
    new_avg = (
        (on_hand * current_avg + quantity_received * unit_cost) / denominator
        if denominator > 0
        else unit_cost
    )
    if not current:
        inventory_status = f"{inventory_status};missing_prior_cogs_batch_cost_used"

    receipt_id = receipt_id or str(uuid.uuid4())
    ledger_key = hashlib.sha256(f"vendor_receipt\x1f{receipt_id}".encode()).hexdigest()
    with conn:
        conn.execute(
            """
            INSERT INTO vendor_receipts (
                receipt_id, asin, received_date, quantity_received,
                total_cost_paid, unit_cost, source, notes,
                processed_at, resulting_ledger_key, inventory_snapshot_date,
                on_hand_qty_used, inventory_qty_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
            """,
            (
                receipt_id, asin, received_date, quantity_received,
                float(total_cost_paid), unit_cost, source, notes, ledger_key,
                snapshot_date, on_hand, inventory_status,
            ),
        )
        if current:
            if str(received_date) < str(current[2]):
                raise ValueError("received_date cannot precede the current COGS effective_start")
            conn.execute(
                """
                UPDATE cogs_ledger
                SET effective_end = ?, is_current = 0
                WHERE cogs_ledger_key = ?
                """,
                (received_date, current[0]),
            )
        conn.execute(
            """
            INSERT INTO cogs_ledger (
                cogs_ledger_key, asin, unit_cogs, effective_start,
                effective_end, is_current, source, source_reference,
                prior_on_hand_qty, receipt_quantity, receipt_unit_cost,
                inventory_snapshot_date, inventory_qty_status
            ) VALUES (?, ?, ?, ?, NULL, 1, 'vendor_receipt', ?, ?, ?, ?, ?, ?)
            """,
            (
                ledger_key, asin, new_avg, received_date, receipt_id,
                on_hand, quantity_received, unit_cost, snapshot_date, inventory_status,
            ),
        )
    return {
        "receipt_id": receipt_id,
        "asin": asin,
        "prior_on_hand_qty": on_hand,
        "prior_avg_cost": current_avg,
        "receipt_quantity": quantity_received,
        "receipt_unit_cost": unit_cost,
        "new_avg_cost": new_avg,
        "inventory_snapshot_date": snapshot_date,
        "inventory_qty_status": inventory_status,
        "cogs_ledger_key": ledger_key,
    }


def enrich_sales_with_asof_cogs(
    sales: pd.DataFrame,
    cogs_ledger: pd.DataFrame,
    *,
    sale_date_col: str = "purchase-date",
) -> pd.DataFrame:
    """Attach the COGS row effective on each sale date and preserve missing rows."""
    source = sales.copy().reset_index(drop=True)
    source["_sale_row"] = range(len(source))
    source["asin"] = source["asin"].fillna("").astype(str).str.strip()
    source["sale_date"] = pd.to_datetime(source[sale_date_col], errors="coerce", utc=True)
    source["quantity_n"] = pd.to_numeric(source["quantity"], errors="coerce")
    source["item_price_revenue"] = pd.to_numeric(source["item-price"], errors="coerce")

    ledger = cogs_ledger.copy()
    if ledger.empty:
        source["unit_cogs"] = pd.NA
        source["cogs_ledger_key"] = pd.NA
        source["cogs_status"] = "missing"
        source["cogs_amount"] = pd.NA
        return source
    ledger["effective_start_ts"] = pd.to_datetime(
        ledger["effective_start"], errors="coerce", utc=True
    )
    ledger["effective_end_ts"] = pd.to_datetime(
        ledger["effective_end"], errors="coerce", utc=True
    )
    candidates = source[["_sale_row", "asin", "sale_date"]].merge(ledger, on="asin", how="left")
    valid = candidates[
        candidates["effective_start_ts"].le(candidates["sale_date"])
        & (
            candidates["effective_end_ts"].isna()
            | candidates["sale_date"].lt(candidates["effective_end_ts"])
        )
    ].copy()
    valid = valid.sort_values("effective_start_ts").drop_duplicates("_sale_row", keep="last")
    attach = valid[["_sale_row", "cogs_ledger_key", "unit_cogs"]]
    source = source.merge(attach, on="_sale_row", how="left")
    source["cogs_status"] = source["unit_cogs"].notna().map({True: "available", False: "missing"})
    source["cogs_amount"] = source["unit_cogs"] * source["quantity_n"]
    source.loc[source["cogs_status"].eq("missing"), "cogs_amount"] = pd.NA
    return source


def build_sales_profitability(
    orders: pd.DataFrame,
    dim_product: pd.DataFrame,
    cogs_ledger: pd.DataFrame,
    transaction_mart: pd.DataFrame,
) -> pd.DataFrame:
    """Build item-price profitability with as-of COGS and allocated exact order fees."""
    sales = orders.copy()
    sales["quantity_n"] = pd.to_numeric(sales["quantity"], errors="coerce").fillna(0)
    sales = sales[
        sales["sales-channel"].eq("Amazon.com")
        & sales["quantity_n"].gt(0)
        & ~sales["asin"].fillna("").isin(EXCLUDED_ASINS)
    ].copy()
    sales = enrich_sales_with_asof_cogs(sales, cogs_ledger)
    brand_map = dim_product.set_index("asin")["canonical_brand"].to_dict()
    sales["brand"] = sales["asin"].map(brand_map).fillna("Unassigned")

    order_fees = (
        transaction_mart[transaction_mart["order_matched"].astype(bool)]
        .groupby("order_id", as_index=False)
        .agg(amazon_fees=("amazon_fees", "sum"))
    )
    sales = sales.merge(
        order_fees, left_on="amazon-order-id", right_on="order_id", how="left"
    )
    order_revenue = sales.groupby("amazon-order-id")["item_price_revenue"].transform("sum")
    sales["amazon_fees_allocated"] = sales["amazon_fees"] * (
        sales["item_price_revenue"] / order_revenue.where(order_revenue.ne(0))
    )
    sales["fee_status"] = sales["amazon_fees"].notna().map(
        {True: "exact_order_fee_allocated", False: "missing"}
    )
    sales["contribution_profit_before_ads"] = (
        sales["item_price_revenue"] - sales["cogs_amount"] + sales["amazon_fees_allocated"]
    )
    sales.loc[
        sales["cogs_status"].eq("missing") | sales["amazon_fees_allocated"].isna(),
        "contribution_profit_before_ads",
    ] = pd.NA
    sales["contribution_margin_before_ads"] = (
        sales["contribution_profit_before_ads"] / sales["item_price_revenue"]
    )
    sales["sale_line_key"] = sales.apply(
        lambda row: hashlib.sha256(
            f"{row['amazon-order-id']}\x1f{row['asin']}\x1f{row['_sale_row']}".encode()
        ).hexdigest(),
        axis=1,
    )
    return sales.rename(
        columns={
            "amazon-order-id": "order_id_value",
            "product-name": "product_name_value",
            "sku": "sku_value",
        }
    )[
        [
            "sale_line_key", "order_id_value", "sale_date", "asin", "sku_value",
            "brand", "product_name_value", "quantity_n", "item_price_revenue",
            "unit_cogs", "cogs_amount", "cogs_status", "cogs_ledger_key",
            "amazon_fees_allocated", "fee_status", "contribution_profit_before_ads",
            "contribution_margin_before_ads",
        ]
    ].rename(
        columns={
            "order_id_value": "order_id",
            "sku_value": "sku",
            "product_name_value": "product_name",
            "quantity_n": "quantity",
            "amazon_fees_allocated": "amazon_fees",
        }
    )


def materialize_sales_profitability(
    conn: sqlite3.Connection,
    profitability: pd.DataFrame,
) -> None:
    apply_stage2_schema(conn)
    out = profitability.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].astype(str).replace("NaT", None)
    with conn:
        conn.execute("DELETE FROM sales_profitability")
        out.to_sql("sales_profitability", conn, if_exists="append", index=False)
