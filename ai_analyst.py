import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


def _df_records(df, max_rows=10):
    if df is None or df.empty:
        return []

    d = df.copy().head(max_rows)

    for col in d.columns:
        d[col] = d[col].apply(
            lambda x: str(x)
            if not isinstance(x, (int, float, str, bool, type(None)))
            else x
        )

    return d.to_dict(orient="records")


def build_ai_input(context):
    return {
        "period": context.get("period"),
        "sales_summary": context.get("sales_summary", {}),
        "marketing_summary": context.get("marketing_summary", {}),
        "comparison": _df_records(context.get("comparison_view"), max_rows=10),
        "product_mix": _df_records(context.get("product_mix"), max_rows=10),
        "keyword_actions": _df_records(context.get("keyword_actions"), max_rows=15),
        "bid_recommendations": _df_records(context.get("bid_recs"), max_rows=15),
        "inventory_risk": _df_records(context.get("inventory_risk"), max_rows=10),
    }


def _empty_ai_summary(message="AI summary not available."):
    return {
        "summary": message,
        "sales": "",
        "ppc": "",
        "inventory": "",
        "actions": [],
    }


def _extract_json(text):
    if not text or not text.strip():
        return None

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None

    return None


def build_ai_summary(context):
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return _empty_ai_summary("OpenAI API key not found.")

    client = OpenAI(api_key=api_key)

    ai_input = build_ai_input(context)

    prompt = f"""
You are an executive analyst for LITET, a cycling socks brand selling on Amazon.

Analyze the following dashboard data and return valid JSON only.

Rules:
- Do not calculate new metrics unless already provided.
- Do not invent data.
- Be direct and decision-oriented.
- Use TACOS as the primary overall PPC efficiency KPI.
- Use ACOS only for keyword-level bid decisions.
- For PPC overall behavior, discuss TACOS, ad spend, ad sales, and revenue relationship.
- For keyword actions, discuss ACOS, CVR, ROAS, spend, and orders.
- For inventory, only summarize what appears in the inventory_risk data.
- If inventory data seems incomplete or needs review, say that clearly.
- Keep it concise.
- Do not use markdown.
- Do not wrap the JSON in code fences.
- Output JSON only.

Required JSON structure:
{{
  "summary": "short executive summary",
  "sales": "sales performance interpretation",
  "ppc": "PPC performance interpretation using TACOS as the leading overall KPI",
  "inventory": "inventory risk interpretation based only on inventory_risk table",
  "actions": [
    "action 1",
    "action 2",
    "action 3"
  ]
}}

Dashboard data:
{json.dumps(ai_input, indent=2, default=str)}
"""

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            temperature=0.2,
        )

        text = getattr(response, "output_text", "")

        parsed = _extract_json(text)

        if not parsed:
            return _empty_ai_summary(
                "AI summary could not be generated because the model returned an invalid response."
            )

        return {
            "summary": parsed.get("summary", ""),
            "sales": parsed.get("sales", ""),
            "ppc": parsed.get("ppc", ""),
            "inventory": parsed.get("inventory", ""),
            "actions": parsed.get("actions", []),
        }

    except Exception as e:
        return _empty_ai_summary(f"AI summary could not be generated: {e}")