"""
Product Validator — CRITICAL SAFETY LAYER (Rule-based, NO LLM).
Validates product-use-case combinations against constraint rules.
This is the guardrail that prevents invalid quotes.
"""
import logging
from typing import Tuple, Optional
from database import get_product, log_audit, search_products_by_category
from config import (
    SUBMERGED_KEYWORDS, INTERIOR_KEYWORDS, EXTERIOR_KEYWORDS,
    CUSTOM_ENGINEERING_KEYWORDS, LARGE_ORDER_THRESHOLD,
    LARGE_ORDER_QTY_THRESHOLD, VALID_REGIONS,
)

logger = logging.getLogger("sales_bot.product_validator")


class ValidationResult:
    """Encapsulates the result of a product validation check."""

    def __init__(self, is_valid: bool, product: dict = None,
                 error_message: str = None, escalation_type: str = None,
                 warning: str = None, suggested_alternatives: list = None):
        self.is_valid = is_valid
        self.product = product
        self.error_message = error_message
        self.escalation_type = escalation_type
        self.warning = warning
        self.suggested_alternatives = suggested_alternatives or []

    def __bool__(self):
        return self.is_valid


def validate_product_request(product_code: str, use_case: str = None,
                             region: str = None, quantity: int = None,
                             user_id: str = None) -> ValidationResult:
    """
    CRITICAL: Validate a product request against all business rules.

    Checks (in order):
    1. Product exists in DB
    2. Use-case doesn't violate constraints
    3. Region is valid
    4. Quantity doesn't exceed escalation threshold
    5. No custom engineering keywords

    Returns ValidationResult with is_valid=True/False.
    """

    # ── Check 1: Product Exists ──────────────────────
    if not product_code:
        return ValidationResult(
            is_valid=False,
            error_message="No product code specified. Could you tell me which product you're interested in?",
            escalation_type=None,
        )

    product = get_product(product_code)
    if product is None:
        log_audit(
            action_type="escalation_unknown_product",
            input_data=f"product_code={product_code}",
            output_data="Product not found in catalog",
            user_id=user_id,
            warnings=f"Unknown product code: {product_code}",
        )
        return ValidationResult(
            is_valid=False,
            error_message=(
                f"I don't recognize product code **{product_code}**. "
                f"Let me connect you with our sales team for assistance.\n\n"
                f"Our available product lines include WTZ (floor), WE (wall), "
                f"RE (roof), and FE (specialized floor) series."
            ),
            escalation_type="escalation_unknown_product",
        )

    # ── Check 2: Constraint Validation ───────────────
    constraints = (product.get("constraints") or "none").lower()
    use_case_lower = (use_case or "").lower()

    if use_case_lower:
        # Check: above-waterline product vs submerged use
        if "above-waterline" in constraints:
            for keyword in SUBMERGED_KEYWORDS:
                if keyword in use_case_lower:
                    # Find submersible alternatives
                    alternatives = _find_alternatives(
                        product.get("category", ""),
                        ["waterproof", "submersible"]
                    )
                    alt_text = ""
                    if alternatives:
                        alt_codes = ", ".join(
                            f"**{a['product_code']}**" for a in alternatives
                        )
                        alt_text = f"\n\nFor submerged/underwater applications, consider: {alt_codes}"

                    log_audit(
                        action_type="guardrail_triggered",
                        input_data=f"product={product_code}, use_case={use_case}",
                        output_data=f"REJECTED: constraint violation — above-waterline only product for '{keyword}' use",
                        user_id=user_id,
                        warnings=f"CONSTRAINT_VIOLATION: product={product_code}, constraint={constraints}, use_case={use_case}",
                    )
                    return ValidationResult(
                        is_valid=False,
                        product=product,
                        error_message=(
                            f"⚠️ **This product is not suitable for submerged applications.**\n\n"
                            f"**{product_code}** ({product.get('description', '')}) "
                            f"is designed for **above-waterline** expansion joints only.\n\n"
                            f"The described use-case ('{use_case}') involves a submerged/underwater "
                            f"environment which is incompatible with this product's specifications."
                            f"{alt_text}"
                        ),
                        escalation_type="guardrail_triggered",
                        warning=f"Constraint violation: {constraints} vs {use_case}",
                        suggested_alternatives=alternatives,
                    )

        # Check: interior-only product vs exterior use
        if "interior only" in constraints:
            for keyword in INTERIOR_KEYWORDS:
                if keyword in use_case_lower:
                    log_audit(
                        action_type="guardrail_triggered",
                        input_data=f"product={product_code}, use_case={use_case}",
                        output_data=f"REJECTED: interior-only product for exterior use",
                        user_id=user_id,
                        warnings=f"CONSTRAINT_VIOLATION: product={product_code}, constraint={constraints}, use_case={use_case}",
                    )
                    alternatives = _find_alternatives(
                        product.get("category", ""),
                        ["none", "all environments"]
                    )
                    return ValidationResult(
                        is_valid=False,
                        product=product,
                        error_message=(
                            f"⚠️ **{product_code}** is rated for **interior use only**.\n\n"
                            f"The described application ('{use_case}') requires exterior-rated products. "
                            f"This product is not weather-sealed for outdoor exposure."
                        ),
                        escalation_type="guardrail_triggered",
                        warning=f"Interior-only constraint violated",
                        suggested_alternatives=alternatives,
                    )

        # Check: exterior-only product vs interior use
        if "exterior only" in constraints:
            for keyword in EXTERIOR_KEYWORDS:
                if keyword in use_case_lower:
                    log_audit(
                        action_type="guardrail_triggered",
                        input_data=f"product={product_code}, use_case={use_case}",
                        output_data=f"REJECTED: exterior-only product for interior use",
                        user_id=user_id,
                        warnings=f"CONSTRAINT_VIOLATION: product={product_code}, constraint={constraints}, use_case={use_case}",
                    )
                    return ValidationResult(
                        is_valid=False,
                        product=product,
                        error_message=(
                            f"⚠️ **{product_code}** is designed for **exterior applications only**.\n\n"
                            f"The described use-case ('{use_case}') appears to be an interior application."
                        ),
                        escalation_type="guardrail_triggered",
                        warning=f"Exterior-only constraint violated",
                    )

    # ── Check 3: Custom Engineering Detection ────────
    if use_case_lower:
        for keyword in CUSTOM_ENGINEERING_KEYWORDS:
            if keyword in use_case_lower:
                log_audit(
                    action_type="escalation_custom_engineering",
                    input_data=f"product={product_code}, use_case={use_case}",
                    output_data="Custom engineering request detected",
                    user_id=user_id,
                    warnings=f"Custom keyword detected: '{keyword}'",
                )
                return ValidationResult(
                    is_valid=False,
                    product=product,
                    error_message=(
                        f"🔧 **Custom engineering requests require our technical team.**\n\n"
                        f"Your request involves custom specifications that go beyond "
                        f"our standard product range. I'll escalate this to our "
                        f"engineering department for a tailored solution."
                    ),
                    escalation_type="escalation_custom_engineering",
                )

    # ── Check 4: Region Validation ───────────────────
    if region and region not in VALID_REGIONS:
        return ValidationResult(
            is_valid=False,
            error_message=(
                f"I couldn't determine your region. We currently serve:\n"
                f"• **GCC** (Middle East)\n• **India**\n• **SEA** (Southeast Asia)\n\n"
                f"Which region is your project in?"
            ),
        )

    # ── Check 5: Large Order Escalation ──────────────
    if quantity and quantity > LARGE_ORDER_QTY_THRESHOLD:
        base = float(product.get("base_price", 0))
        estimated_total = base * quantity
        if estimated_total > LARGE_ORDER_THRESHOLD or quantity > LARGE_ORDER_QTY_THRESHOLD:
            log_audit(
                action_type="escalation_large_order",
                input_data=f"product={product_code}, qty={quantity}, est_total={estimated_total}",
                output_data="Large order — escalating to senior sales",
                user_id=user_id,
                warnings=f"Large order: {quantity} units, ~${estimated_total:,.2f}",
            )
            return ValidationResult(
                is_valid=False,
                product=product,
                error_message=(
                    f"📦 **This is a significant order** ({quantity} units of {product_code}).\n\n"
                    f"Orders of this size qualify for volume pricing and personalized service. "
                    f"I'm flagging this for our senior sales manager to provide you with "
                    f"the best possible pricing and logistics plan."
                ),
                escalation_type="escalation_large_order",
            )

    # ── All checks passed ────────────────────────────
    log_audit(
        action_type="product_validated",
        input_data=f"product={product_code}, use_case={use_case}, region={region}, qty={quantity}",
        output_data="PASSED: All validations cleared",
        user_id=user_id,
    )

    return ValidationResult(
        is_valid=True,
        product=product,
    )


def _find_alternatives(category: str, preferred_constraints: list) -> list:
    """Find alternative products in the same category that match given constraint keywords."""
    try:
        products = search_products_by_category(category)
        alternatives = []
        for p in products:
            p_constraints = (p.get("constraints") or "").lower()
            for pref in preferred_constraints:
                if pref.lower() in p_constraints:
                    alternatives.append(p)
                    break
        return alternatives
    except Exception:
        return []
