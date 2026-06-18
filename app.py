import json
import os
from typing import Any

import gradio as gr
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from data import load_orders, load_asins, load_ppc

from data_prep import prepare_sales_data, prepare_ppc_data

from calculations import (
    get_sales_summary,
    get_ppc_summary,
    get_marketing_summary,
    get_top_keywords,
    get_top_products,
    get_product_mix,
    get_color_performance,
    get_sales_summary_period,
    get_sales_breakdown,
    compare_periods,
    explain_change,
    get_metric_trend,
    get_keyword_bid_recommendations,
)

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ROUTER_MODEL = "gpt-5.4-nano"
ANSWER_MODEL = "gpt-5.4-mini"


def load_all_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    orders_raw = load_orders()
    asins_raw = load_asins()
    ppc_raw = load_ppc()

    sales_df = prepare_sales_data(orders_raw, asins_raw)
    ppc_df = prepare_ppc_data(ppc_raw, campaign_filter="LITET")

    return sales_df, ppc_df


SALES_DF, PPC_DF = load_all_data()


def serialize_result(result: Any) -> Any:
    if isinstance(result, pd.DataFrame):
        return result.to_dict(orient="records")
    if isinstance(result, dict):
        return result
    return result


def build_messages_with_history(system_prompt: str, history, message: str) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for item in history[-12:]:
            if isinstance(item, dict):
                role = item.get("role")
                content = item.get("content")

                if role and content:
                    messages.append({
                        "role": role,
                        "content": str(content)
                    })

            elif isinstance(item, (list, tuple)) and len(item) == 2:
                user_msg, assistant_msg = item

                if user_msg:
                    messages.append({
                        "role": "user",
                        "content": str(user_msg)
                    })

                if assistant_msg:
                    messages.append({
                        "role": "assistant",
                        "content": str(assistant_msg)
                    })

    messages.append({
        "role": "user",
        "content": message
    })

    return messages


def run_tool(
    tool_name: str,
    days: int = 7,
    period: str = "LAST_7_DAYS",
    group_by: str | None = None,
    metric: str = "revenue"
) -> dict:
    tool_map = {
        "get_sales_summary": lambda: get_sales_summary(SALES_DF, days=days),
        "get_ppc_summary": lambda: get_ppc_summary(PPC_DF, days=days),
        "get_marketing_summary": lambda: get_marketing_summary(SALES_DF, PPC_DF, days=days),
        "get_top_keywords": lambda: get_top_keywords(PPC_DF, days=days, min_clicks=5, top_n=10),
        "get_top_products": lambda: get_top_products(SALES_DF, days=days, metric="revenue", top_n=10),
        "get_product_mix": lambda: get_product_mix(SALES_DF, days=days),
        "get_color_performance": lambda: get_color_performance(SALES_DF, days=days),
        "get_sales_summary_period": lambda: get_sales_summary_period(SALES_DF, period=period),
        "get_sales_breakdown": lambda: get_sales_breakdown(
            SALES_DF,
            period=period,
            group_by=group_by or "color",
            metric=metric,
            top_n=10,
        ),
        "compare_periods": lambda: compare_periods(
            SALES_DF,
            period=period,
            metric=metric,
            group_by=group_by,
            top_n=10,
        ),
        "explain_change": lambda: explain_change(
            SALES_DF,
            period=period,
            metric=metric,
            dimension=group_by or "asin",
            top_n=10,
        ),
        "get_metric_trend": lambda: get_metric_trend(
            SALES_DF,
            PPC_DF,
            metric=metric,
            lookback_weeks=12,
        ),
        "get_keyword_bid_recommendations": lambda: get_keyword_bid_recommendations(
            PPC_DF,
            days=30,
            target_acos=0.25,
            min_clicks=10,
            min_spend=15.0,
            pause_clicks_threshold=20,
            strong_cvr_threshold=0.12,
            top_n=50,
        ),
    }

    if tool_name not in tool_map:
        raise ValueError(f"Unknown tool: {tool_name}")

    result = tool_map[tool_name]()
    return {
        "tool_name": tool_name,
        "days": days,
        "period": period,
        "group_by": group_by,
        "metric": metric,
        "result": serialize_result(result),
    }


AVAILABLE_TOOLS = [
    "get_sales_summary",
    "get_ppc_summary",
    "get_marketing_summary",
    "get_top_keywords",
    "get_top_products",
    "get_product_mix",
    "get_color_performance",
    "get_sales_summary_period",
    "get_sales_breakdown",
    "compare_periods",
    "explain_change",
    "get_metric_trend",
    "get_keyword_bid_recommendations",
]


def route_question(user_question: str) -> dict:
    system_prompt = f"""
You are a routing assistant for an internal LITET analytics chatbot.

Your job is to decide WHICH TYPE OF ANALYSIS is needed first,
and then select the correct tools.

Do NOT default to 7-day summaries unless the user is explicitly asking for a short rolling-period snapshot.

Available tools:
{AVAILABLE_TOOLS}

Supported periods:
- LAST_7_DAYS
- LAST_30_DAYS
- MTD
- YTD

Supported group_by values:
- color
- type
- item_name
- asin
- size

Supported metrics:
- revenue
- pairs_sold
- units_sold_amazon
- orders
- tacos
- acos
- roas
- ad_spend
- ad_sales
- aov
- 3_pack_share

----------------------
ANALYSIS INTENT RULES
----------------------

1. SNAPSHOT QUESTIONS
Examples:
- What are MTD sales?
- Show me YTD revenue
- What are sales this month?

Use:
- get_sales_summary_period
- get_sales_breakdown

2. COMPARISON QUESTIONS
Examples:
- What changed vs last month?
- Compare MTD vs prior MTD
- Is revenue improving?
- Is growth real?

Use:
- compare_periods

3. DRIVER ANALYSIS QUESTIONS
Examples:
- Why did revenue change?
- What is driving TACOS improvement?
- Why are sales down?
- What should I investigate first?

Use:
- compare_periods
- explain_change

4. PRODUCT MIX QUESTIONS
Examples:
- Show me MTD revenue by single vs 3-pack
- Which colors are driving growth?
- Which products are driving growth?

Use:
- get_product_mix
- get_color_performance
- get_sales_breakdown
- compare_periods
- explain_change

5. PPC / MARKETING QUESTIONS
Examples:
- How are ads performing?
- Why did TACOS worsen?
- What keywords should I cut?
- What is driving ACOS?

Use:
- get_ppc_summary
- get_marketing_summary
- get_top_keywords
- compare_periods

6. TREND QUESTIONS
Examples:
- Show me TACOS trend
- Are 3-packs gaining share over time?
- Is revenue trend improving?
- Show me ROAS trend over the last 12 weeks

Use:
- get_metric_trend

7. DECISION SUPPORT QUESTIONS
Examples:
- What should I investigate first?
- Which products are hurting performance right now?
- Which SKUs contributed most to growth?

Use:
- compare_periods
- explain_change
- get_top_products
- get_marketing_summary
- get_top_keywords

8. KEYWORD BID QUESTIONS
Examples:
- What should my CPC be per keyword?
- Which keywords should I lower bids on?
- Which keywords should I pause?
- Give me bid recommendations for my keywords

Use:
- get_keyword_bid_recommendations

----------------------
IMPORTANT RULES
----------------------

- Use only available tool names.
- You may choose 1 to 4 tools.
- Prefer comparison over snapshots when the question asks:
  compare, changed, trend, improving, worsening, growth,
  decline, increase, decrease, up, down, real, why, driving
- If the user asks:
  "Is this real?"
  NEVER use only get_sales_summary(days=7)
- For MTD / YTD:
  prefer period tools over rolling day tools
- For grouped analysis:
  use get_sales_breakdown
- For contribution / what changed most:
  use explain_change
- For product contribution:
  use get_top_products
- For keyword decisions:
  use get_top_keywords
- If the user asks about "trend", "over time", "last several weeks",
  "weekly trend", or "is this improving over time", use get_metric_trend.
- For trend questions, prefer metric values like:
  tacos, acos, roas, revenue, ad_spend, ad_sales, aov, 3_pack_share
- Do not use 3_pack_share for color questions.
- If the question is about color performance, color growth, or color decline,
  prefer revenue unless the user explicitly asks for pairs or orders.
- If the user asks for CPC recommendations, bid changes, keyword actions,
  pause / lower / raise bids, or suggested CPC by keyword,
  use get_keyword_bid_recommendations.

Return valid JSON only in this exact format:

{{
  "days": 7,
  "period": "MTD",
  "group_by": null,
  "metric": "revenue",
  "tools": ["compare_periods"]
}}
"""

    response = client.responses.create(
        model=ROUTER_MODEL,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question},
        ],
    )

    text = response.output_text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {
            "days": 7,
            "period": "MTD",
            "group_by": None,
            "metric": "revenue",
            "tools": ["compare_periods"],
        }

    days = parsed.get("days", 7)
    if days not in [7, 30]:
        days = 7

    period = parsed.get("period", "MTD")
    if period not in ["LAST_7_DAYS", "LAST_30_DAYS", "MTD", "YTD"]:
        period = "MTD"

    group_by = parsed.get("group_by", None)
    if group_by not in [None, "color", "type", "item_name", "asin", "size"]:
        group_by = None

    metric = parsed.get("metric", "revenue")
    if metric not in [
        "revenue",
        "pairs_sold",
        "units_sold_amazon",
        "orders",
        "tacos",
        "acos",
        "roas",
        "ad_spend",
        "ad_sales",
        "aov",
        "3_pack_share",
    ]:
        metric = "revenue"

    tools = parsed.get("tools", ["compare_periods"])
    tools = [t for t in tools if t in AVAILABLE_TOOLS]

    if not tools:
        tools = ["compare_periods"]

    sales_metric_only_tools = {
        "compare_periods",
        "explain_change",
        "get_sales_breakdown",
        "get_top_products",
    }

    ppc_style_metrics = {
        "tacos",
        "acos",
        "roas",
        "ad_spend",
        "ad_sales",
    }

    if metric in ppc_style_metrics and any(t in sales_metric_only_tools for t in tools):
        metric = "revenue"

    if metric == "3_pack_share" and "get_metric_trend" not in tools:
        metric = "revenue"

    if group_by in ["color", "asin", "item_name", "size"] and metric not in [
        "revenue",
        "pairs_sold",
        "units_sold_amazon",
        "orders",
    ]:
        metric = "revenue"

    if group_by == "color" and metric == "3_pack_share":
        metric = "revenue"

    if any(t == "get_keyword_bid_recommendations" for t in tools):
        metric = "revenue"
        group_by = None

    return {
        "days": days,
        "period": period,
        "group_by": group_by,
        "metric": metric,
        "tools": tools,
    }


def generate_answer(user_question: str, tool_outputs: list[dict], history: list) -> str:
    system_prompt = """
You are LITET Analyst, an internal business analyst for LITET.

You answer questions about:
- sales
- PPC
- TACOS / ACOS / ROAS
- top keywords
- top products
- product mix
- color performance
- period-over-period change
- weekly trends over time

Important rules:
- Use ONLY the tool outputs provided.
- Do not invent numbers.
- Be concise, analytical, and practical.
- Focus on what changed, what is driving it, and what action matters.
- If period comparison data is provided, explain the main drivers.
- If explain_change data is provided, identify the top contributors and tell the user what to investigate first.
- If trend data is provided, clearly state whether the metric is improving, worsening, stable, or improving but still unstable.
- Prefer business interpretation over repeating raw rows.
- When strong anomalies exist, explicitly identify the anomaly and explain the likely cause using only the supporting values provided.
- If keyword bid recommendation data is provided, present a table with:
  Keyword | Match Type | Current CPC | Suggested CPC | ACOS | CVR | Action | Reason

Always include:
1. what changed
2. why it likely happened
3. what should be checked first

Do not:
- make long-term conclusions from a single short comparison
- use raw ASINs when product names are available
- mention internal tool names in the final answer

FORMAT RULES:

1. Always show the evaluated period clearly

Examples:
Current MTD: April 1 – April 18, 2026
Prior MTD: March 1 – March 18, 2026

or

Trend period: Jan 25 – Apr 18, 2026

2. Prefer markdown tables over bullet points

3. For comparison analysis use:

| Metric | Current | Prior | Change % |

4. For driver analysis use:

| Driver | Current | Prior | Change | Why it matters |

5. For trend analysis use this exact structure:

First:
Short interpretation sentence like:

"TACOS trend is improving, but it is not yet stable."

Then:

| Week | Metric | Supporting context |

Then:

| Focus area | Why |

Use the Focus Area table instead of long paragraphs whenever possible.

6. Keep supporting context concise and non-repetitive.
Avoid repeating "spend increased" in every row unless it is truly important.

7. Keep answers operator-focused and decision-oriented.

8. End with a short executive summary (2–4 sentences max).

Avoid bullet points unless explicitly requested.
"""

    user_payload = {
        "question": user_question,
        "tool_outputs": tool_outputs,
    }

    response = client.responses.create(
        model=ANSWER_MODEL,
        input=build_messages_with_history(
            system_prompt,
            history,
            json.dumps(user_payload, default=str),
        ),
    )

    return response.output_text.strip()


def chat_fn(message: str, history: list) -> str:
    try:
        routing = route_question(message)

        days = routing["days"]
        period = routing["period"]
        group_by = routing["group_by"]
        metric = routing["metric"]
        tools = routing["tools"]

        tool_outputs = [
            run_tool(
                tool_name,
                days=days,
                period=period,
                group_by=group_by,
                metric=metric,
            )
            for tool_name in tools
        ]

        answer = generate_answer(message, tool_outputs, history)
        return answer

    except Exception as e:
        return f"Error: {str(e)}"


demo = gr.ChatInterface(
    fn=chat_fn,
    title="LITET Analyst",
    description="Ask a business question about sales, PPC, products, mix, color performance, period-over-period change, or trends over time.",
    examples=[
        "What changed in MTD sales vs prior MTD?",
        "Compare YTD revenue vs prior YTD",
        "What is driving MTD revenue growth?",
        "Show me MTD revenue by single vs 3-pack",
        "Compare MTD revenue by color vs prior MTD",
        "How are ads performing vs the prior 30 days?",
        "Why did TACOS improve or worsen?",
        "Is revenue growth real or just short-term noise?",
        "Show me TACOS trend over the last 12 weeks",
        "Show me revenue trend over the last 12 weeks",
        "Are 3-packs gaining share over time?",
        "Which products are driving the decline this month?",
        "Which SKUs contributed most to MTD growth?",
        "What should I investigate first in declining sales?",
    ],
)

if __name__ == "__main__":
    demo.launch()