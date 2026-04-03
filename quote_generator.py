"""
Quote Generator — Produces formatted quotation text.
Uses LLM for natural language formatting + structured pricing data.
"""
import logging
from typing import Optional
from llm_client import call_llm
from pricing_engine import PricingResult, format_price_display, calculate_price
from product_validator import validate_product_request, ValidationResult
from database import save_quote, log_audit
from memory_layer import get_user_region

logger = logging.getLogger("sales_bot.quote_generator")

# ── Quote formatting prompt ──────────────────────────
QUOTE_FORMAT_PROMPT = """You are a professional quotation formatter for an expansion joint covers company.

Format the following quote data into a clean, professional quotation message for a customer on Discord.

Use markdown formatting. Be concise, professional, and clear.
Include all breakdown details.
DO NOT change any numbers — use the exact values provided.
DO NOT add any made-up specifications or features.
Keep it under 400 words.

Structure:
1. Quote header with reference number
2. Product details
3. Pricing breakdown (tabular)
4. Total
5. Validity period (30 days)
6. Standard terms footer
"""


def generate_quote(user_id: str, intent: dict,
                   username: str = None) -> str:
    """
    Full quote generation pipeline:
    1. Determine region
    2. Validate product
    3. Calculate price (deterministic)
    4. Format quote (LLM)
    5. Save to DB
    6. Return formatted quote

    Returns the final quote message string.
    """
    product_code = intent.get("product_code")
    use_case = intent.get("use_case")
    quantity = intent.get("quantity") or 1
    region = get_user_region(user_id, intent)

    # ── Step 1: Check region ─────────────────────────
    if not region:
        return (
            "I'd love to prepare a quote for you! "
            "Could you please tell me which region your project is in?\n\n"
            "• **GCC** (Middle East — UAE, Saudi Arabia, Qatar, etc.)\n"
            "• **India**\n"
            "• **SEA** (Southeast Asia — Singapore, Malaysia, etc.)"
        )

    # ── Step 2: Validate product ─────────────────────
    validation = validate_product_request(
        product_code=product_code,
        use_case=use_case,
        region=region,
        quantity=quantity,
        user_id=user_id,
    )

    if not validation.is_valid:
        return validation.error_message

    product = validation.product

    # ── Step 3: Calculate price (DETERMINISTIC) ──────
    pricing = calculate_price(
        product=product,
        region=region,
        quantity=quantity,
        user_id=user_id,
    )

    if pricing is None:
        return "I encountered an error calculating the price. Please try again or contact support."

    # ── Step 4: Format quote text via LLM ────────────
    quote_data = (
        f"Product: {product.get('product_code')} — {product.get('description')}\n"
        f"Category: {product.get('category')}\n"
        f"Region: {region}\n"
        f"Quantity: {quantity}\n"
        f"Currency: {pricing.currency}\n"
        f"\nPricing Breakdown:\n"
    )

    for key, value in pricing.breakdown.items():
        quote_data += f"  {key}: {value}\n"

    quote_data += (
        f"\nUnit Price: {format_price_display(pricing.unit_price, pricing.currency)}\n"
        f"Total Price: {format_price_display(pricing.final_price, pricing.currency)}\n"
    )

    formatted_quote = call_llm(
        system_prompt=QUOTE_FORMAT_PROMPT,
        user_message=quote_data,
        temperature=0.4,
        max_tokens=800,
        user_id=user_id,
        action_label="generate_quote",
    )

    # ── Step 5: Save quote to DB ─────────────────────
    quote_id = save_quote(
        user_id=user_id,
        product_code=product.get("product_code", ""),
        product_name=product.get("description", ""),
        region=region,
        quantity=quantity,
        base_price=float(product.get("base_price", 0)),
        final_price=pricing.final_price,
        currency=pricing.currency,
        breakdown=pricing.breakdown,
    )

    # ── Step 6: Log and return ───────────────────────
    log_audit(
        action_type="quote_generated",
        input_data=f"product={product_code}, region={region}, qty={quantity}",
        output_data=f"quote_id={quote_id}, total={pricing.final_price} {pricing.currency}",
        user_id=user_id,
        metadata=pricing.to_dict(),
    )

    if quote_id:
        formatted_quote += f"\n\n📋 **Quote Reference:** `{quote_id}`"

    return formatted_quote


def handle_product_inquiry(user_id: str, intent: dict) -> str:
    """
    Handle product information requests (not quotes).
    Provides product details from DB, not hallucinated.
    """
    product_code = intent.get("product_code")
    category = intent.get("product_category")

    if product_code:
        from database import get_product
        product = get_product(product_code)
        if product:
            return (
                f"📦 **{product['product_code']}** — {product.get('category', '').title()} Joint Cover\n\n"
                f"**Description:** {product.get('description', 'N/A')}\n"
                f"**Category:** {product.get('category', 'N/A').title()}\n"
                f"**Base Price:** ${float(product.get('base_price', 0)):,.2f} USD\n"
                f"**Constraints:** {product.get('constraints', 'None')}\n\n"
                f"Would you like a quote for a specific region? (GCC / India / SEA)"
            )
        else:
            return (
                f"I couldn't find product **{product_code}** in our catalog. "
                f"Could you double-check the code? Our product lines include:\n"
                f"• **WTZ** series (floor joints)\n"
                f"• **WE** series (wall joints)\n"
                f"• **RE** series (roof joints)\n"
                f"• **FE** series (specialized floor joints)"
            )

    if category:
        from database import search_products_by_category
        products = search_products_by_category(category)
        if products:
            lines = [f"📋 **{category.title()} Expansion Joint Covers:**\n"]
            for p in products:
                price = float(p.get("base_price", 0))
                lines.append(
                    f"• **{p['product_code']}** — {p.get('description', '')[:60]}... "
                    f"(Base: ${price:,.2f})"
                )
            lines.append("\nWould you like a detailed quote for any of these?")
            return "\n".join(lines)

    return (
        "I can help you find the right expansion joint cover! We have:\n\n"
        "• **Floor joints** (WTZ / FE series) — for commercial & industrial floors\n"
        "• **Wall joints** (WE series) — for interior & exterior walls\n"
        "• **Roof joints** (RE series) — for roofing systems\n\n"
        "Which category interests you, or do you have a specific product code?"
    )
