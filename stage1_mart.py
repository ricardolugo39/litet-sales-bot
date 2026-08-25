"""Stage 1 governed dimensions, transaction mart, fee ledger, and reconciliation."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


BRANDS = ("Litet", "Has10", "Unassigned")
TRANSACTION_AMOUNT_COLUMNS = (
    "Total product charges",
    "Total promotional rebates",
    "Amazon fees",
    "Other",
    "Total (USD)",
)
TRANSACTION_EVENT_COLUMNS = (
    "Date",
    "Transaction type",
    "Order ID",
    "Product Details",
    *TRANSACTION_AMOUNT_COLUMNS,
)


@dataclass
class Stage1Marts:
    dim_product: pd.DataFrame
    bridge_product_sku: pd.DataFrame
    product_title_alias: pd.DataFrame
    campaign_brand_map: pd.DataFrame
    transaction_mart: pd.DataFrame
    fee_ledger: pd.DataFrame
    reconciliation: pd.DataFrame


def _clean_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False)
        .str.strip(),
        errors="coerce",
    ).fillna(0.0)


def _hash_frame(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    def digest(row):
        payload = "\x1f".join("" if pd.isna(row[col]) else str(row[col]) for col in columns)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return df.apply(digest, axis=1)


def _first_match(text: str, values: tuple[str, ...]) -> str | None:
    lowered = str(text).lower()
    for value in values:
        if value.lower() in lowered:
            return value
    return None


def _product_family(title: str) -> str:
    lowered = title.lower()
    if "cleat cover" in lowered or "spat" in lowered:
        return "Cleat Covers"
    if "sock" in lowered:
        return "Socks"
    return "Unassigned"


def _pack_type(title: str, governed_type: str = "") -> str:
    governed = governed_type.strip().lower()
    if governed:
        return governed
    lowered = title.lower()
    if "6-pack" in lowered or "6 pack" in lowered or "6 pairs" in lowered:
        return "6-pack"
    if "3-pack" in lowered or "3 pack" in lowered or "3 pairs" in lowered:
        return "3-pack"
    return "single"


def _units_per_sellable_unit(pack_type: str) -> int:
    return {"single": 1, "3-pack": 3, "6-pack": 6}.get(pack_type, 1)


def build_product_dimensions(
    orders: pd.DataFrame,
    governed_asins: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build an ASIN product dimension and effective observed SKU/title bridges."""
    source = orders.copy()
    source.columns = source.columns.str.strip()
    source["asin"] = _clean_text(source["asin"])
    source["sku"] = _clean_text(source["sku"])
    source["product-name"] = _clean_text(source["product-name"])
    source["purchase_ts"] = pd.to_datetime(source["purchase-date"], errors="coerce", utc=True)
    source["quantity_n"] = _number(source["quantity"])
    source["item_price_n"] = _number(source["item-price"])

    eligible = source[
        source["sales-channel"].eq("Amazon.com")
        & source["quantity_n"].gt(0)
        & source["asin"].ne("")
    ].copy()

    seed = governed_asins.copy()
    seed.columns = seed.columns.str.strip()
    seed["ASIN"] = _clean_text(seed["ASIN"])
    litet_asins = set(seed["ASIN"])
    seed_by_asin = seed.drop_duplicates("ASIN").set_index("ASIN")

    title_brand_signal = eligible["product-name"].str.contains(
        r"Has10|Hasten", case=False, regex=True, na=False
    )
    has10_asins = set(eligible.loc[title_brand_signal, "asin"]) - litet_asins

    def asin_brand(asin: str) -> str:
        if asin in litet_asins:
            return "Litet"
        if asin in has10_asins:
            return "Has10"
        return "Unassigned"

    eligible["brand"] = eligible["asin"].map(asin_brand)

    aliases = (
        eligible.groupby(["asin", "product-name"], as_index=False)
        .agg(
            first_observed_date=("purchase_ts", "min"),
            last_observed_date=("purchase_ts", "max"),
            observed_rows=("amazon-order-id", "size"),
        )
    )
    aliases["canonical_brand"] = aliases["asin"].map(asin_brand)
    aliases["alias_brand_text"] = "Unassigned"
    aliases.loc[
        aliases["product-name"].str.contains("litet", case=False, na=False),
        "alias_brand_text",
    ] = "Litet"
    aliases.loc[
        aliases["product-name"].str.contains(r"has10|hasten", case=False, regex=True, na=False),
        "alias_brand_text",
    ] = "Has10"
    aliases["title_alias_key"] = _hash_frame(aliases, ["asin", "product-name"])
    aliases = aliases.rename(columns={"product-name": "title_alias"})

    bridge = (
        eligible[eligible["sku"].ne("")]
        .groupby(["asin", "sku"], as_index=False)
        .agg(
            effective_start=("purchase_ts", "min"),
            effective_end=("purchase_ts", "max"),
            observed_rows=("amazon-order-id", "size"),
        )
    )
    bridge["canonical_brand"] = bridge["asin"].map(asin_brand)
    bridge["is_current"] = True
    bridge["product_sku_key"] = _hash_frame(bridge, ["asin", "sku"])

    product_rows = []
    for asin, group in eligible.groupby("asin"):
        title_counts = group["product-name"].value_counts()
        canonical_title = title_counts.index[0] if len(title_counts) else ""
        brand = asin_brand(asin)
        governed_item = ""
        governed_type = ""
        if asin in seed_by_asin.index:
            governed_item = str(seed_by_asin.at[asin, "Item"] or "")
            governed_type = str(seed_by_asin.at[asin, "Type"] or "")
        pack_type = _pack_type(f"{canonical_title} {governed_item}", governed_type)
        product_rows.append(
            {
                "product_key": hashlib.sha256(asin.encode("utf-8")).hexdigest(),
                "asin": asin,
                "canonical_brand": brand,
                "product_family": _product_family(canonical_title),
                "canonical_product_name": governed_item or canonical_title,
                "size": _first_match(
                    f"{governed_item} {canonical_title}",
                    ("Small/Medium", "Large/X-Large", "Large", "Medium", "Youth"),
                ),
                "color": _first_match(
                    f"{governed_item} {canonical_title}",
                    ("White", "Black", "Royal Blue", "Blue", "Orange", "Red", "Gold", "Purple", "Pink"),
                ),
                "pack_type": pack_type,
                "units_per_sellable_unit": _units_per_sellable_unit(pack_type),
                "first_observed_date": group["purchase_ts"].min(),
                "last_observed_date": group["purchase_ts"].max(),
                "active_status": "Observed",
                "effective_start": group["purchase_ts"].min(),
                "effective_end": pd.NaT,
                "is_current": True,
                "assignment_method": "governed_asin" if brand == "Litet" else (
                    "title_alias_history" if brand == "Has10" else "unassigned"
                ),
            }
        )

    dim_product = pd.DataFrame(product_rows)
    product_key_map = dim_product.set_index("asin")["product_key"]
    bridge["product_key"] = bridge["asin"].map(product_key_map)
    aliases["product_key"] = aliases["asin"].map(product_key_map)

    dim_columns = [
        "product_key", "asin", "canonical_brand", "product_family",
        "canonical_product_name", "size", "color", "pack_type",
        "units_per_sellable_unit", "first_observed_date", "last_observed_date",
        "active_status", "effective_start", "effective_end", "is_current",
        "assignment_method",
    ]
    bridge_columns = [
        "product_sku_key", "product_key", "asin", "sku", "canonical_brand",
        "effective_start", "effective_end", "is_current", "observed_rows",
    ]
    alias_columns = [
        "title_alias_key", "product_key", "asin", "title_alias",
        "canonical_brand", "alias_brand_text", "first_observed_date",
        "last_observed_date", "observed_rows",
    ]
    return (
        dim_product[dim_columns].sort_values(["canonical_brand", "asin"]).reset_index(drop=True),
        bridge[bridge_columns].sort_values(["canonical_brand", "asin", "sku"]).reset_index(drop=True),
        aliases[alias_columns].sort_values(["canonical_brand", "asin", "title_alias"]).reset_index(drop=True),
    )


def build_campaign_brand_map(ppc: pd.DataFrame) -> pd.DataFrame:
    """Map every exact campaign name using the owner-approved exhaustive rule."""
    campaigns = _clean_text(ppc["Campaign Name"]).drop_duplicates().sort_values()
    out = pd.DataFrame({"campaign_name": campaigns})
    is_litet = out["campaign_name"].str.contains("litet", case=False, na=False)
    out["brand"] = is_litet.map({True: "Litet", False: "Has10"})
    out["mapping_rule"] = is_litet.map(
        {True: "campaign_name_contains_litet", False: "campaign_name_does_not_contain_litet"}
    )
    out["is_current"] = True
    out["campaign_brand_key"] = _hash_frame(out, ["campaign_name"])
    return out[
        ["campaign_brand_key", "campaign_name", "brand", "mapping_rule", "is_current"]
    ].reset_index(drop=True)


def _build_order_brand_bridge(
    orders: pd.DataFrame,
    dim_product: pd.DataFrame,
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    source = orders.copy()
    source["asin"] = _clean_text(source["asin"])
    source["product-name"] = _clean_text(source["product-name"])
    source["amazon-order-id"] = _clean_text(source["amazon-order-id"])
    asin_brand = dim_product.set_index("asin")["canonical_brand"].to_dict()
    source["brand"] = source["asin"].map(asin_brand).fillna("Unassigned")

    order_brand_sets = source.groupby("amazon-order-id")["brand"].agg(
        lambda values: sorted({x for x in values if x != "Unassigned"})
    )
    order_brand = {}
    for order_id, brands in order_brand_sets.items():
        if len(brands) == 1:
            order_brand[order_id] = brands[0]
        elif len(brands) > 1:
            order_brand[order_id] = "Mixed"
        else:
            order_brand[order_id] = "Unassigned"

    title_brand = (
        source[source["product-name"].ne("")]
        .drop_duplicates(["amazon-order-id", "product-name"])
        .set_index(["amazon-order-id", "product-name"])["brand"]
        .to_dict()
    )
    return order_brand, title_brand


def build_transaction_mart(
    transactions: pd.DataFrame,
    orders: pd.DataFrame,
    dim_product: pd.DataFrame,
) -> pd.DataFrame:
    """Normalize transactions, collapse duplicate imports, and resolve lifecycle state."""
    raw = transactions.copy()
    for col in TRANSACTION_EVENT_COLUMNS:
        raw[col] = _clean_text(raw[col])
    raw["transaction_date"] = pd.to_datetime(raw["Date"], errors="coerce")
    raw["imported_ts"] = pd.to_datetime(raw.get("imported_at"), errors="coerce", utc=True)
    for col in TRANSACTION_AMOUNT_COLUMNS:
        raw[f"{col}_amount"] = _number(raw[col])

    raw["economic_event_key"] = _hash_frame(raw, list(TRANSACTION_EVENT_COLUMNS))
    raw["status_rank"] = raw["Transaction Status"].map({"Released": 2, "Deferred": 1}).fillna(0)
    raw = raw.sort_values(
        ["economic_event_key", "status_rank", "imported_ts"],
        ascending=[True, False, False],
        na_position="last",
    )
    resolved = raw.drop_duplicates("economic_event_key", keep="first").copy()

    order_brand, title_brand = _build_order_brand_bridge(orders, dim_product)
    resolved["order_matched"] = resolved["Order ID"].isin(order_brand)
    resolved["brand"] = resolved["Order ID"].map(order_brand).fillna("Unassigned")

    mixed = resolved["brand"].eq("Mixed")
    if mixed.any():
        detail_keys = list(zip(resolved.loc[mixed, "Order ID"], resolved.loc[mixed, "Product Details"]))
        resolved.loc[mixed, "brand"] = [
            title_brand.get(key, "Unassigned") for key in detail_keys
        ]

    resolved["is_released"] = resolved["Transaction Status"].eq("Released")
    resolved["is_deferred"] = resolved["Transaction Status"].eq("Deferred")
    resolved["transaction_mart_key"] = resolved["economic_event_key"]

    columns = [
        "transaction_mart_key", "economic_event_key", "transaction_date",
        "Transaction Status", "Transaction type", "Order ID", "Product Details",
        "brand", "order_matched", "is_released", "is_deferred",
        *[f"{col}_amount" for col in TRANSACTION_AMOUNT_COLUMNS],
        "source_file", "imported_at", "transaction_uid",
    ]
    return resolved[columns].rename(
        columns={
            "Transaction Status": "transaction_status",
            "Transaction type": "transaction_type",
            "Order ID": "order_id",
            "Product Details": "product_details",
            "Total product charges_amount": "product_charges",
            "Total promotional rebates_amount": "promotional_rebates",
            "Amazon fees_amount": "amazon_fees",
            "Other_amount": "other_amount",
            "Total (USD)_amount": "transaction_total",
        }
    ).reset_index(drop=True)


def _classify_fee(transaction_type: str, product_details: str, component: str) -> tuple[str, str]:
    detail = product_details.lower()
    if "customer returns" in detail or "returns processing" in detail:
        return "All other fees", "FBA returns processing"
    if "long-term storage" in detail or "aged inventory" in detail:
        return "All other fees", "Long-term/aged inventory storage"
    if "inventory storage" in detail:
        return "All other fees", "FBA inventory storage"
    if "awd storage" in detail:
        return "All other fees", "AWD storage"
    if "advertis" in detail:
        return "All other fees", "Advertising invoice"
    if transaction_type == "Refund":
        return "All other fees", "Refund fee/reversal"
    if transaction_type == "Order Payment" and component == "amazon_fees":
        return "Combined order fee", "Referral + FBA (not separable)"
    if transaction_type == "Liquidations":
        return "All other fees", "Liquidation fee"
    if transaction_type == "Service Fees":
        return "All other fees", "Other service fee"
    return "All other fees", "Other/uncategorized"


def build_fee_ledger(transaction_mart: pd.DataFrame) -> pd.DataFrame:
    """Emit normalized fee components while preserving exact source amounts."""
    rows = []
    for row in transaction_mart.itertuples(index=False):
        components = [("amazon_fees", float(row.amazon_fees))]
        if row.transaction_type == "Service Fees" and float(row.other_amount) != 0:
            components.append(("other_amount", float(row.other_amount)))
        for component, amount in components:
            if amount == 0:
                continue
            category, subcategory = _classify_fee(
                row.transaction_type, row.product_details, component
            )
            fee_key = hashlib.sha256(
                f"{row.transaction_mart_key}\x1f{component}".encode("utf-8")
            ).hexdigest()
            rows.append(
                {
                    "fee_ledger_key": fee_key,
                    "transaction_mart_key": row.transaction_mart_key,
                    "transaction_date": row.transaction_date,
                    "order_id": row.order_id,
                    "brand": row.brand,
                    "transaction_status": row.transaction_status,
                    "transaction_type": row.transaction_type,
                    "product_details": row.product_details,
                    "fee_category": category,
                    "fee_subcategory": subcategory,
                    "source_component": component,
                    "fee_amount": amount,
                    "is_exact": True,
                    "allocation_method": "direct_order_brand" if row.order_matched else "unassigned",
                }
            )
    return pd.DataFrame(rows)


def build_reconciliation(
    raw_transactions: pd.DataFrame,
    transaction_mart: pd.DataFrame,
    fee_ledger: pd.DataFrame,
) -> pd.DataFrame:
    """Return per-brand and All reconciliation/control metrics."""
    raw = raw_transactions.copy()
    for col in TRANSACTION_AMOUNT_COLUMNS:
        raw[f"{col}_amount"] = _number(raw[col])
    raw["raw_status"] = _clean_text(raw["Transaction Status"])

    records = []
    for brand in ["Litet", "Has10", "Unassigned", "All"]:
        mart = transaction_mart if brand == "All" else transaction_mart[transaction_mart["brand"].eq(brand)]
        fees = fee_ledger if brand == "All" else fee_ledger[fee_ledger["brand"].eq(brand)]
        matched = mart[mart["order_matched"]]
        component_total = (
            mart["product_charges"]
            + mart["promotional_rebates"]
            + mart["amazon_fees"]
            + mart["other_amount"]
        )
        source_fee_total = mart["amazon_fees"].sum() + mart.loc[
            mart["transaction_type"].eq("Service Fees"), "other_amount"
        ].sum()
        fee_variance = fees["fee_amount"].sum() - source_fee_total
        records.append(
            {
                "brand": brand,
                "resolved_transaction_rows": len(mart),
                "matched_rows": len(matched),
                "matched_row_coverage": len(matched) / len(mart) if len(mart) else 0.0,
                "matched_dollar_coverage": (
                    matched["transaction_total"].abs().sum() / mart["transaction_total"].abs().sum()
                    if mart["transaction_total"].abs().sum() else 0.0
                ),
                "released_balance": mart.loc[mart["is_released"], "transaction_total"].sum(),
                "deferred_balance": mart.loc[mart["is_deferred"], "transaction_total"].sum(),
                "amazon_fees": mart["amazon_fees"].sum(),
                "classified_fee_total": fees["fee_amount"].sum(),
                "unexplained_fee_variance": fee_variance,
                "transaction_identity_variance": (mart["transaction_total"] - component_total).sum(),
                "unassigned_fee_rows": len(fees[fees["brand"].eq("Unassigned")]),
            }
        )

    result = pd.DataFrame(records)
    result["raw_transaction_rows"] = len(raw)
    result["raw_released_balance"] = raw.loc[
        raw["raw_status"].eq("Released"), "Total (USD)_amount"
    ].sum()
    result["raw_deferred_balance"] = raw.loc[
        raw["raw_status"].eq("Deferred"), "Total (USD)_amount"
    ].sum()
    return result


def build_stage1_marts(
    orders: pd.DataFrame,
    governed_asins: pd.DataFrame,
    ppc: pd.DataFrame,
    transactions: pd.DataFrame,
) -> Stage1Marts:
    dim, bridge, aliases = build_product_dimensions(orders, governed_asins)
    campaigns = build_campaign_brand_map(ppc)
    transaction_mart = build_transaction_mart(transactions, orders, dim)
    fees = build_fee_ledger(transaction_mart)
    reconciliation = build_reconciliation(transactions, transaction_mart, fees)
    return Stage1Marts(dim, bridge, aliases, campaigns, transaction_mart, fees, reconciliation)


def _sqlite_ready(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].astype(str).replace("NaT", None)
        elif str(out[col].dtype) == "bool":
            out[col] = out[col].astype(int)
    return out


def materialize_stage1(conn: sqlite3.Connection, marts: Stage1Marts) -> None:
    """Apply the schema and atomically replace all Stage 1 table contents."""
    migration = Path(__file__).with_name("migrations") / "001_stage1_analytics.sql"
    conn.executescript(migration.read_text())
    tables = {
        "dim_product": marts.dim_product,
        "bridge_product_sku": marts.bridge_product_sku,
        "product_title_alias": marts.product_title_alias,
        "campaign_brand_map": marts.campaign_brand_map,
        "transaction_mart": marts.transaction_mart,
        "fee_ledger": marts.fee_ledger,
        "fee_reconciliation": marts.reconciliation,
    }
    with conn:
        for table in reversed(tables):
            conn.execute(f'DELETE FROM "{table}"')
        for table, df in tables.items():
            _sqlite_ready(df).to_sql(table, conn, if_exists="append", index=False)
