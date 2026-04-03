"""
Intent Parser — Uses LLM to extract structured intent from user messages.
Extracts: product_code, use_case, region, quantity, intent_type.
"""
import json
import logging
from typing import Optional
from llm_client import call_llm
from database import log_audit, get_all_products

logger = logging.getLogger("sales_bot.intent_parser")

# ── System prompt for intent extraction ──────────────
INTENT_SYSTEM_PROMPT = """You are an intent parser for an expansion joint covers company sales bot.

Your job is to extract structured data from user messages. ALWAYS respond with valid JSON only — no extra text.

Available products:
{product_list}

Valid regions:
- GCC (Middle East: UAE, Saudi Arabia, Qatar, Bahrain, Kuwait, Oman)
- India (all Indian cities/states)
- SEA (Southeast Asia: Singapore, Malaysia, Thailand, Indonesia, etc.)

Extract the following fields:
- intent_type: one of ["quote_request", "product_inquiry", "greeting", "follow_up", "complaint", "general_question", "unknown"]
- product_code: the product code if mentioned (e.g., "WTZ-1700"), or null
- product_category: if no specific code but a category mentioned (floor/wall/roof), or null
- use_case: the described application/use-case, or null
- region: "GCC", "India", or "SEA" — infer from city/country names, or null if unclear
- quantity: integer if mentioned, or null
- notes: any additional context

Respond ONLY with JSON. Example:
{
  "intent_type": "quote_request",
  "product_code": "WTZ-1700",
  "product_category": "floor",
  "use_case": "floor expansion joint for shopping mall",
  "region": "GCC",
  "quantity": 10,
  "notes": "Project in Dubai Marina"
}
"""


def _build_product_list() -> str:
    """Build a concise product list string for the system prompt."""
    products = get_all_products()
    if not products:
        return "No products loaded."
    lines = []
    for p in products:
        code = p.get("product_code", "?")
        cat = p.get("category", "?")
        constraints = p.get("constraints", "none")
        desc = p.get("description", "")[:80]
        lines.append(f"- {code} ({cat}): {desc} [Constraints: {constraints}]")
    return "\n".join(lines)


def parse_intent(user_message: str, user_id: str = None) -> dict:
    """
    Parse user message into structured intent using LLM.

    Returns dict with keys:
        intent_type, product_code, product_category, use_case,
        region, quantity, notes

    On failure, returns a default "unknown" intent.
    """
    product_list = _build_product_list()
    system_prompt = INTENT_SYSTEM_PROMPT.replace("{product_list}", product_list)

    response = call_llm(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=0.1,  # Very deterministic for parsing
        max_tokens=512,
        user_id=user_id,
        action_label="parse_intent",
    )

    try:
        # Try to extract JSON from response (handle markdown wrappers)
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove markdown code fences
            lines = cleaned.split("\n")
            cleaned = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        parsed = json.loads(cleaned)

        # Normalize product_code to uppercase
        if parsed.get("product_code"):
            parsed["product_code"] = parsed["product_code"].upper().strip()

        # Normalize region
        if parsed.get("region"):
            region = parsed["region"].strip().upper()
            region_map = {
                "GCC": "GCC", "MIDDLE EAST": "GCC", "UAE": "GCC",
                "DUBAI": "GCC", "SAUDI": "GCC", "QATAR": "GCC",
                "INDIA": "India", "MUMBAI": "India", "DELHI": "India",
                "BANGALORE": "India", "CHENNAI": "India",
                "SEA": "SEA", "SINGAPORE": "SEA", "MALAYSIA": "SEA",
                "THAILAND": "SEA", "INDONESIA": "SEA",
            }
            parsed["region"] = region_map.get(region, parsed["region"])

        # Ensure quantity is int or None
        if parsed.get("quantity") is not None:
            try:
                parsed["quantity"] = int(parsed["quantity"])
            except (ValueError, TypeError):
                parsed["quantity"] = None

        logger.info(f"Parsed intent: {parsed.get('intent_type')} | "
                     f"product={parsed.get('product_code')} | "
                     f"region={parsed.get('region')}")
        return parsed

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        log_audit(
            action_type="parse_intent_failed",
            input_data=user_message[:500],
            output_data=response[:500],
            user_id=user_id,
            warnings=f"JSON parse failure: {e}",
            success=False,
        )
        return {
            "intent_type": "unknown",
            "product_code": None,
            "product_category": None,
            "use_case": None,
            "region": None,
            "quantity": None,
            "notes": f"Parse error — raw response: {response[:200]}",
        }
