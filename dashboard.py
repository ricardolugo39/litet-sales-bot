import base64
import streamlit as st

from dashboard_context import load_all_data, build_dashboard_context
from html_dashboard import build_html_dashboard


st.set_page_config(
    page_title="LITET Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
        max-width: 100%;
    }

    section[data-testid="stSidebar"] {
        background: #f8fafc;
        border-right: 1px solid #e5e7eb;
    }

    iframe {
        border: none !important;
        border-radius: 18px;
        width: 100%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


sales_df, ppc_df, inventory_df = load_all_data()
st.sidebar.write("Max sales date:", sales_df["purchase_date"].max())
st.sidebar.write("Sales rows:", len(sales_df))


with st.sidebar:
    st.title("LITET")
    st.caption("Internal Analytics")

    st.markdown("---")

    period = st.selectbox(
        "Period",
        ["LAST_7_DAYS", "LAST_30_DAYS", "MTD", "YTD"],
        index=2,
    )

    show_debug = st.checkbox("Show debug info", value=False)

    st.markdown("---")
    st.caption("Amazon · PPC · Inventory")

campaign_col = None

for col in ["campaign_name", "campaign", "campaignName", "Campaign Name", "campaign-name"]:
    if col in ppc_df.columns:
        campaign_col = col
        break

if campaign_col:
    campaign_list = sorted(ppc_df[campaign_col].dropna().unique().tolist())
else:
    campaign_list = []

selected_campaign = st.selectbox(
    "PPC Campaign",
    ["All Campaigns"] + campaign_list,
)

selected_campaign_col = campaign_col

context = build_dashboard_context(
    sales_df=sales_df,
    ppc_df=ppc_df,
    inventory_df=inventory_df,
    period=period,
    selected_campaign=selected_campaign,
    selected_campaign_col=selected_campaign_col,
)

html = build_html_dashboard(context)




if show_debug:
    st.subheader("Debug Info")
    st.write("Sales rows:", len(sales_df))
    st.write("PPC rows:", len(ppc_df))
    st.write("Inventory rows:", len(inventory_df))
    st.code(html[:500], language="html")


encoded_html = base64.b64encode(html.encode("utf-8")).decode("utf-8")
html_src = f"data:text/html;base64,{encoded_html}"

st.iframe(
    src=html_src,
    height=3600,
)

if st.sidebar.button("Clear All Cache"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()