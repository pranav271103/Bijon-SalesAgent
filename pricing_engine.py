"""
Pricing Engine — DETERMINISTIC, RULE-BASED (NO LLM).
Calculates final prices based on region-specific pricing formulas.
This module NEVER uses LLM — all calculations are pure Python arithmetic.
"""
import logging
from typing import Optional
from database import log_audit
from config import REGION_CURRENCIES

logger = logging.getLogger("sales_bot.pricing_engine")


class PricingResult:
    """Structured pricing output with full breakdown."""

    def __init__(self, final_price: float, currency: str,
                 breakdown: dict, region: str, quantity: int,
                 unit_price: float):
        self.final_price = final_price
        self.currency = currency
        self.breakdown = breakdown
        self.region = region
        self.quantity = quantity
        self.unit_price = unit_price

    def to_dict(self) -> dict:
        return {
            "final_price": round(self.final_price, 2),
            "unit_price": round(self.unit_price, 2),
            "currency": self.currency,
            "region": self.region,
            "quantity": self.quantity,
            "breakdown": self.breakdown,
        }


def calculate_price(product: dict, region: str, quantity: int = 1,
                    user_id: str = None) -> Optional[PricingResult]:
    """
    Calculate price using DETERMINISTIC regional pricing formulas.

    Formulas:
        GCC:   final = (base_price × 2.0) + (shipping_cost × 1.5)  [per unit]
        India: final = base_price + installation(25%) + pidilite(10%)  [per unit]
        SEA:   final = base_price × 2.5  (Ankara multiplier)  [per unit]

    All results multiplied by quantity for total.
    """
    base_price = float(product.get("base_price", 0))
    shipping_cost = float(product.get("shipping_cost", 50))
    product_code = product.get("product_code", "UNKNOWN")
    currency = REGION_CURRENCIES.get(region, "USD")

    if quantity < 1:
        quantity = 1

    try:
        if region == "GCC":
            # GCC: Material markup ×2 + Shipping markup ×1.5
            material_cost = base_price * 2.0
            shipping_total = shipping_cost * 1.5
            unit_price = material_cost + shipping_total
            breakdown = {
                "formula": "GCC: (base_price × 2.0) + (shipping × 1.5)",
                "base_price_usd": base_price,
                "material_markup": "×2.0",
                "material_cost": round(material_cost, 2),
                "shipping_base": shipping_cost,
                "shipping_markup": "×1.5",
                "shipping_total": round(shipping_total, 2),
                "unit_price": round(unit_price, 2),
                "quantity": quantity,
                "total_price": round(unit_price * quantity, 2),
                "currency": currency,
                "notes": "Material markup ×2, Shipping markup ×1.5. Prices in AED.",
            }

        elif region == "India":
            # India: Base + Installation (25%) + Pidilite (10%)
            installation_cost = base_price * 0.25
            pidilite_cost = base_price * 0.10
            unit_price = base_price + installation_cost + pidilite_cost
            breakdown = {
                "formula": "India: base_price + installation(25%) + pidilite(10%)",
                "base_price_usd": base_price,
                "installation_cost": round(installation_cost, 2),
                "installation_rate": "25% of base",
                "pidilite_adhesive_cost": round(pidilite_cost, 2),
                "pidilite_rate": "10% of base",
                "unit_price": round(unit_price, 2),
                "quantity": quantity,
                "total_price": round(unit_price * quantity, 2),
                "currency": currency,
                "notes": "Includes Pidilite adhesive/sealant + on-site installation. Prices in INR.",
            }

        elif region == "SEA":
            # SEA: Ankara multiplier ×2.5
            unit_price = base_price * 2.5
            breakdown = {
                "formula": "SEA: base_price × 2.5 (Ankara multiplier)",
                "base_price_usd": base_price,
                "ankara_multiplier": "×2.5",
                "unit_price": round(unit_price, 2),
                "quantity": quantity,
                "total_price": round(unit_price * quantity, 2),
                "currency": currency,
                "notes": "Ankara manufacturing + regional logistics ×2.5. Prices in SGD.",
            }

        else:
            logger.error(f"Invalid region: {region}")
            log_audit(
                action_type="pricing_error",
                input_data=f"product={product_code}, region={region}",
                output_data=f"Invalid region: {region}",
                user_id=user_id,
                warnings=f"Pricing attempted for unsupported region: {region}",
                success=False,
            )
            return None

        total_price = round(unit_price * quantity, 2)

        # Log successful pricing calculation
        log_audit(
            action_type="pricing_calculated",
            input_data=f"product={product_code}, region={region}, qty={quantity}, base={base_price}",
            output_data=f"unit_price={unit_price:.2f} {currency}, total={total_price:.2f} {currency}",
            user_id=user_id,
            metadata=breakdown,
        )

        return PricingResult(
            final_price=total_price,
            currency=currency,
            breakdown=breakdown,
            region=region,
            quantity=quantity,
            unit_price=round(unit_price, 2),
        )

    except Exception as e:
        logger.error(f"Pricing calculation error: {e}")
        log_audit(
            action_type="pricing_error",
            input_data=f"product={product_code}, region={region}, qty={quantity}",
            output_data=f"Calculation error: {e}",
            user_id=user_id,
            warnings=str(e),
            success=False,
        )
        return None


def format_price_display(amount: float, currency: str) -> str:
    """Format a price for human-friendly display."""
    currency_symbols = {
        "AED": "AED",
        "INR": "₹",
        "SGD": "S$",
        "USD": "$",
    }
    symbol = currency_symbols.get(currency, currency)
    return f"{symbol} {amount:,.2f}"
