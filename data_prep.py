import pandas as pd


def prepare_sales_data(orders_raw: pd.DataFrame, asins_raw: pd.DataFrame) -> pd.DataFrame:
    orders = orders_raw.copy()
    asins = asins_raw.copy()

    orders.columns = orders.columns.str.strip().str.lower()
    asins.columns = asins.columns.str.strip().str.lower()

    orders = orders.rename(columns={
        "purchase-date": "purchase_date",
        "sales-channel": "sales_channel",
        "item-price": "item_price",
        "product-name": "product_name"
    })

    asins = asins.rename(columns={
        "item": "item_name"
    })

    valid_asins = asins["asin"].dropna().unique()

    orders_amazon = orders.loc[
        orders["asin"].isin(valid_asins) &
        (orders["sales_channel"] == "Amazon.com")
    ].copy()

    orders_amazon["purchase_date"] = pd.to_datetime(
        orders_amazon["purchase_date"],
        errors="coerce"
    )

    sales_enriched = orders_amazon.merge(
        asins,
        on="asin",
        how="left",
        suffixes=("", "_asin")
    )

    sales_enriched["color"] = sales_enriched["item_name"].str.extract(
        r"(White|Black|Blue)",
        expand=False
    )

    sales_enriched["size"] = sales_enriched["item_name"].str.extract(
        r"(Small/Medium|Large/X-Large|Large)",
        expand=False
    )

    numeric_cols = [
        "quantity",
        "item_price",
        "item-tax",
        "shipping-price",
        "shipping-tax",
        "gift-wrap-price",
        "gift-wrap-tax",
        "item-promotion-discount",
        "ship-promotion-discount"
    ]

    for col in numeric_cols:
        if col in sales_enriched.columns:
            sales_enriched[col] = pd.to_numeric(sales_enriched[col], errors="coerce")

    if "quantity" in sales_enriched.columns:
        sales_enriched["quantity"] = sales_enriched["quantity"].astype("Int64")

    price_cols = [col for col in numeric_cols if col != "quantity" and col in sales_enriched.columns]
    sales_enriched[price_cols] = sales_enriched[price_cols].astype(float)

    sales_enriched = sales_enriched.loc[sales_enriched["quantity"] > 0].copy()

    sales_enriched["revenue"] = sales_enriched["item_price"]
    sales_enriched["unit_price"] = sales_enriched["item_price"] / sales_enriched["quantity"]

    pack_size_map = {
        "single": 1,
        "3-pack": 3,
        "6-pack": 6
    }

    sales_enriched["pack_size"] = sales_enriched["type"].map(pack_size_map).fillna(1).astype(int)
    sales_enriched["units_sold_amazon"] = sales_enriched["quantity"]
    sales_enriched["pairs_sold"] = sales_enriched["quantity"] * sales_enriched["pack_size"]

    sales_enriched["date"] = sales_enriched["purchase_date"].dt.date

    return sales_enriched


def prepare_ppc_data(ppc_raw: pd.DataFrame, campaign_filter: str = "LITET") -> pd.DataFrame:
    ppc = ppc_raw.copy()

    ppc.columns = ppc.columns.str.strip().str.lower()

    ppc = ppc.rename(columns={
        "campaign name": "campaign",
        "ad group name": "ad_group",
        "targeting": "keyword",
        "match type": "match_type",
        "customer search term": "search_term",
        "click-thru rate (ctr)": "ctr",
        "cost per click (cpc)": "cpc",
        "7 day total sales": "sales",
        "total advertising cost of sales (acos)": "acos",
        "total return on advertising spend (roas)": "roas",
        "7 day total orders (#)": "orders",
        "7 day total units (#)": "units",
        "7 day conversion rate": "cvr"
    })

    ppc = ppc[
        ppc["campaign"].astype(str).str.contains(campaign_filter, case=False, na=False)
    ].copy()

    def clean_number(series, is_percent=False):
        cleaned = (
            series.astype(str)
            .str.replace("$", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip()
            .replace(["", "nan", "None"], None)
        )

        cleaned = pd.to_numeric(cleaned, errors="coerce")

        if is_percent:
            cleaned = cleaned / 100

        return cleaned

    numeric_cols = [
        "impressions",
        "clicks",
        "cpc",
        "spend",
        "sales",
        "roas",
        "orders",
        "units",
    ]

    percent_cols = [
        "ctr",
        "acos",
        "cvr",
    ]

    for col in numeric_cols:
        if col in ppc.columns:
            ppc[col] = clean_number(ppc[col], is_percent=False)

    for col in percent_cols:
        if col in ppc.columns:
            ppc[col] = clean_number(ppc[col], is_percent=True)

    ppc["date"] = pd.to_datetime(
        ppc["date"],
        errors="coerce"
    )

    ppc = ppc.dropna(subset=["date"]).copy()

    ppc["ctr_calc"] = ppc["clicks"] / ppc["impressions"]
    ppc["cvr_calc"] = ppc["orders"] / ppc["clicks"]
    ppc["acos_calc"] = ppc["spend"] / ppc["sales"]
    ppc["roas_calc"] = ppc["sales"] / ppc["spend"]

    ppc.loc[ppc["impressions"] == 0, "ctr_calc"] = None
    ppc.loc[ppc["clicks"] == 0, "cvr_calc"] = None
    ppc.loc[ppc["sales"] == 0, "acos_calc"] = None
    ppc.loc[ppc["spend"] == 0, "roas_calc"] = None

    ppc["date"] = ppc["date"].dt.date

    return ppc