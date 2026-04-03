"""Quick validation test for pricing engine + product validator guardrails."""
import sys
sys.path.insert(0, ".")

from pricing_engine import calculate_price, format_price_display
from product_validator import validate_product_request
from database import get_product

print("=" * 60)
print("  PRICING ENGINE TESTS")
print("=" * 60)

product = get_product("WTZ-1700")
code = product["product_code"]
base = product["base_price"]
ship = product["shipping_cost"]
print(f"\nProduct: {code} (base: ${base}, shipping: ${ship})")

# GCC
result = calculate_price(product, "GCC", 10)
print(f"\nGCC (10 units):")
print(f"  Unit: {format_price_display(result.unit_price, result.currency)}")
print(f"  Total: {format_price_display(result.final_price, result.currency)}")
expected = (450 * 2) + (55 * 1.5)
print(f"  Expected unit: {expected}")
assert result.unit_price == expected, f"GCC unit price mismatch: {result.unit_price} != {expected}"

# India
result = calculate_price(product, "India", 5)
print(f"\nIndia (5 units):")
print(f"  Unit: {format_price_display(result.unit_price, result.currency)}")
print(f"  Total: {format_price_display(result.final_price, result.currency)}")
expected_india = 450 + (450 * 0.25) + (450 * 0.10)
print(f"  Expected unit: {expected_india}")
assert result.unit_price == expected_india, f"India mismatch"

# SEA
result = calculate_price(product, "SEA", 20)
print(f"\nSEA (20 units):")
print(f"  Unit: {format_price_display(result.unit_price, result.currency)}")
print(f"  Total: {format_price_display(result.final_price, result.currency)}")
expected_sea = 450 * 2.5
assert result.unit_price == expected_sea, f"SEA mismatch"

print("\n" + "=" * 60)
print("  GUARDRAIL TESTS")
print("=" * 60)

# MANDATORY TEST: WTZ-1800 + submerged swimming pool = REJECT
r = validate_product_request("WTZ-1800", "submerged swimming pool", "GCC", 5)
print(f"\nTest T4: WTZ-1800 for submerged swimming pool")
print(f"  Valid: {r.is_valid}")
print(f"  Escalation: {r.escalation_type}")
assert not r.is_valid, "CRITICAL: Submerged guardrail failed!"
assert r.escalation_type == "guardrail_triggered", "Escalation type wrong!"
print("  ✅ PASSED — Correctly rejected")

# Valid product+use case
r = validate_product_request("WTZ-1700", "floor joints for mall lobby", "GCC", 5)
print(f"\nTest: WTZ-1700 for mall lobby")
print(f"  Valid: {r.is_valid}")
assert r.is_valid, "Valid request was rejected!"
print("  ✅ PASSED")

# Unknown product
r = validate_product_request("XYZ-9999", "floor joints", "GCC", 5)
print(f"\nTest T5: XYZ-9999 (unknown product)")
print(f"  Valid: {r.is_valid}")
print(f"  Escalation: {r.escalation_type}")
assert not r.is_valid, "Unknown product was accepted!"
assert r.escalation_type == "escalation_unknown_product"
print("  ✅ PASSED — Correctly escalated")

# Large order
r = validate_product_request("WTZ-1700", "warehouse floor", "GCC", 1000)
print(f"\nTest T6: 1000 units (large order)")
print(f"  Valid: {r.is_valid}")
print(f"  Escalation: {r.escalation_type}")
assert not r.is_valid, "Large order was not escalated!"
assert r.escalation_type == "escalation_large_order"
print("  ✅ PASSED — Correctly escalated")

# Custom engineering
r = validate_product_request("WTZ-1700", "custom dimensions 3m wide", "GCC", 5)
print(f"\nTest T7: Custom engineering request")
print(f"  Valid: {r.is_valid}")
print(f"  Escalation: {r.escalation_type}")
assert not r.is_valid
assert r.escalation_type == "escalation_custom_engineering"
print("  ✅ PASSED — Correctly escalated")

# Submersible product for submerged use (SHOULD PASS)
r = validate_product_request("FE-75", "submerged swimming pool", "GCC", 5)
print(f"\nTest: FE-75 (submersible) for swimming pool")
print(f"  Valid: {r.is_valid}")
assert r.is_valid, "Submersible product was incorrectly rejected for submerged use!"
print("  ✅ PASSED — Submersible product correctly accepted")

print("\n" + "=" * 60)
print("  ✅ ALL TESTS PASSED!")
print("=" * 60)
